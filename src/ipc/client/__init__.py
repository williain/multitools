#!/usr/bin/env python
from __future__ import print_function

import sys
import multiprocessing
import traceback
import collections
try:
    import queue
except ImportError:
    import Queue as queue
import multitools.ipc 
import threading

class ClientException(Exception):
    pass

class Process(object):
    '''
    Interface for your own classes specially designed for use with ProcessList
    helping you pass messages between processes.  Ducktyped as a
    multiprocessing.Process, so you can also just use it as one of those.

    Derive from this class and implement op() with whatever arguments you
    deem fit.  Then instantiate it, passing in the values for those arguments
    and pass the object to ProcessList.add() or add_list().

    To implement message passing, write messages using self.send_message() and
    get them by implementing handle_message() in the targetted process.
    '''
    # M_NAME = "Set this to give your thing a name"
    LISTEN_TYPE=[]
    RESIDENT=False

    def __init__(self, *args, **kwargs):
        if type(self) is Process:
            raise NotImplementedError("Don't instantiate the multitools.Process interface directly")
        else:
            self.queries=collections.deque()
            self.ids={}
            self.pipe=None
            self.set_poll()
            self.process=None
            self.stopped=multiprocessing.Event()
            self.inptactive=False
            self.inptresponse=None
            self.setup(*args, **kwargs)

    def set_pipe(self, pipe):
        '''
        Setter for this process's input/output Pipe.  Mostly for use by
        ProcessList, so it can poll for messages
        '''
        self.pipe=pipe

    def set_poll(self, time=0.1):
        '''
        Set the poll loop time for the thread checking for incoming messages
        (provided you're using this with a supervisor, rather than starting
        it manually).

        Set the poll time to a longer time to reduce the performance penalty
        of it checking for messages, at the cost of it taking potentially
        longer to respond to new messages, and longer to terminate after your
        op() function completes.  Set it to less for the converse, to make
        your process more responsive.

        Arguments:
        - time - The poll time in seconds (default: 0.1s)
        '''
        self.poll_time=time

    def start(self):
        '''
        Start the process.
        '''
        self.process=multiprocessing.Process(target=self.__wrap_op)
        def stopperThread(self):
            while not self.stopped.is_set():
                time.sleep(self.poll_time*2)
            if self.process.is_alive():
                self.process.terminate()

        self.thread=threading.Thread(target=stopperThread,args=[self],name='Stopper')
        self.inptlock=threading.Lock()
        self.idslock=threading.Lock()
        self.process.start()
        self.thread.start()

    def join(self, timeout=None):
        '''
        Wait for the process to terminate
        '''
        assert self.process is not None, 'can only join a started process'
        self.process.join(timeout)
        if not self.process.is_alive():
            self.stopped.set()

    def is_alive(self):
        '''
        Return true if the process is running; false otherwise
        '''
        return True if self.process and self.process.is_alive() else False

    def terminate(self):
        '''
        Stop the process
        '''
        if self.thread.is_alive():
            self.stopped.set()

    def send_object(self, object):
        '''
        Send an object to the supervisor, to be picked up by the object
        handler.  See send_message() for sending message objects to other
        processes.

        Arguments:
        object - The object to send.
        '''
        self.pipe.send(object)

    def send_message(self, target_ids, m_type, *args):
        '''
        Message object sender. Arguments:
        target_ids - The recipient ids of the message e.g. the results of a
                     call to get_ids(), 0 for all ids
        m_type     - the type of the message object to send e.g, EmptyMessage
        other args - further positional arguments are sent as arguments to the
                     message constructor
        Examples:
            # Send a DemoMessage instance to the process with M_NAME=='target'
            self.send_message(self.get_ids('target'),DemoMessage,"DemoVal")
            # Send a DemoMessage to all registered processes
            self.send_message(0,DemoMessage,"DemoVal")
            # Send a DemoMessage only to no processess except those listening
            # for the type DemoMessage.
            self.send_message(1,DemoMessage,"DemoVal")
        '''
        if hasattr(target_ids, "rfind"):
            # If a single string, put it in a list
            target_ids=[target_ids,]

        if target_ids in [0,1]:
            target_ids=[target_ids,]

        for t in target_ids:
            try:
                m=m_type(t, *args)
            except TypeError:
                print("Instantiation error; {0}{1}".format(m_type.__name__,(t,)+args))
                raise
            self.send_object(m)

        if len(target_ids)==0:
            raise IndexError("{0} not sent to no targets! Args:{1}".format(m_type.__name__, str(args)))

    def get_lock(self):
        '''
        Get a threading lock you can use in your handle_message()
        implementation and your op() to make sure you don't write data at
        the same time as you're trying to read it.

        In your setup() implementation, use this and save the lock returned
        for later, e.g. ::
            def setup(self):
                self.lock=self.get_lock()

            def op(self):
                with self.lock:
                    ...get data...
                ...use data...

            def handle_message(self,message):
                if isinstance(message, MyMessageType):
                    with self.lock:
                        ...set data...
        '''
        return threading.Lock()

    def prnt(self, *args):
        '''
        Replacement for the print operator that causes messages to be
        sent though the configured output, as a StringMessage object.

        Unless supervise() is called with a prntHandler argument, it will
        pick up these messages and print them itself, so this function can be
        used as a drop-in replacement for print.
        '''
        self.send_object(multitools.ipc.PrntMessage(self.sup_id,
          " ".join([str(arg) for arg in args])
        ))

    def inpt(self, prompt=None):
        '''
        Replacement for the raw_input function when using host.Supervisor;
        blocks and waits for input.  Also triggers the supervisor to block
        on input in the parent process.
        '''
        if not hasattr(self, 'p_id'):
            raise ClientException('Must set M_NAME and be added to a supervisor before calling inpt()')
        with self.inptlock:
            self.inptactive=True
        self.send_object(
          multitools.ipc.InputMessage(self.sup_id,self.p_id,prompt)
        )
        while True:
            with self.inptlock:
                waiting=self.inptactive
            if waiting:
                time.sleep(self.poll_time)
            else:
                break
        with self.inptlock:
            r=self.inptresponse
            self.inptresponse=None
        return r

    def get_ids(self, name, block=True):
        '''
        Get the set of ids from the supervisor which correspond to the
        process name supplied.

        Note this function blocks by default, waiting for a response from the
        supervisor, if it hasn't already cached the result (in which case
        it will return the result immediately)

        A non-blocking get_ids() call will only return a set of ids if it's
        already cached them, else it will message the supervisor and not wait
        for the reply. The reply, when it comes, will be processed provided
        you call receive() periodicaly.

        It it's sensible for your task, you can make a non-blocking call
        first of all then get on with some work (discarding the result of
        that call), before later getting them using a blocking call to
        get_ids when you actually need the id, which will use the cached
        value if it's already got it, or process the messages containing
        the answer you need which was triggered by your first call.

        If an invalid name is given, you will receive back the empty set.
        Unless you block, you cannot distinguish between the supervisor not
        having replied yet, and the name not being valid.
        '''
        if not hasattr(self, 'p_id'):
            raise ClientException('Must set M_NAME and be added to a supervisor to use get_ids()')
        with self.idslock:
            gotname=name in self.ids
        if not gotname:
            self.send_object(
                multitools.ipc.GetIdsMessage(self.sup_id, self.p_id, name)
            )
            with self.idslock:
                self.queries.append(name)
            if block==False:
                return set()
            else:
                while not gotname:
                    time.sleep(self.poll_time)
                    with self.idslock:
                        gotname=name in self.ids

        with self.idslock:
            ids=self.ids[name]
        return ids

    def __wrap_op(self):
        if not hasattr(self,'p_id'):
            # Not running under a supervisor
            self.op()
        else:
            # Preassigned exception message in case of truly exceptional
            # circumstances (e.g. MemoryError)
            crash=multitools.ipc.ExceptionMessage(self.sup_id, self.p_id,
              RuntimeError("Unable to process exception; aborting!")
            )
            try:
                def receiverThread():
                    while (not self.stopped.is_set()) or self.pipe.poll():
                        if self.pipe.poll():
                            m=self.pipe.recv()
                            if not self.__handle_message(m):
                                self.stopped.set()
                        else:
                            time.sleep(self.poll_time)

                rec=threading.Thread(target=receiverThread, name='Receiver')
                rec.start()
                self.op()
                self.stopped.set()
                rec.join()
            except Exception as e:
                # Preserve the original traceback in the exception message
                try:
                    (_, _, tb) = sys.exc_info()
                    e.args=(e.args[:-1])+(str(e.args[-1])+
                      "\nOriginal traceback:\n"+"".join(
                        traceback.format_tb(tb)
                      ),
                    )
                    self.send_object(multitools.ipc.ExceptionMessage(
                      self.sup_id, self.p_id, e
                    ))
                except Exception as e:
                    try:
                        self.send_object(multitools.ipc.ExceptionMessage(
                          self.sup_id, self.p_id, e
                        ))
                    except Exception:
                        self.send_object(crash)
        if self.pipe:
            self.pipe.close()

    def __handle_message(self, m):
        if isinstance(m, multitools.ipc.IdsReplyMessage):
            try:
                with self.idslock:
                    name=self.queries.popleft()
                    self.ids[name]=m.ids
            except IndexError:
                raise ClientException(
                  "{0}: IdsReplyMessage received for no query".format(
                    self.p_id
                  )
                )
        elif isinstance(m, multitools.ipc.InputResponseMessage):
            with self.inptlock:
                if self.inptactive:
                    self.inptresponse=m.message
                    self.inptactive=False
                else:
                    raise ClientException(
                      '{0}: InputResponse received unexpectedly: '+
                      "message '{1}'".format(self.p_id, m.message)
                    )
        elif isinstance(m, multitools.ipc.ResidentTermMessage) and hasattr(self,'RESIDENT') and self.RESIDENT:
            # We're out of here!
            return False
        else:
            self.__pre_handle_message()
            r=self.handle_message(m)
            self.__post_handle_message(r)
            return r

    def setup(self):
        '''
        Override this to handle initialisation arguments passed to your
        process.

        This method is guaranteed to be called before handle_method is, so you
        can use it to initialise instance variables using the initialisation
        arguments.

        e.g.
        def setup(self, foo):
            self.foo=foo
        '''
        pass

    def op(self):
        '''
        The main method for users of this class to override.

        Subclass this class and implement your own op() method.  Then, to
        instantiate this object, pass in args and kwargs arguments to match
        with the interface for this method.  For example:
        You implement:
        : class MyProcess(multitools.Process):
        :     def op(self, foo, bar, baz=None):
        To instantiate this object, call:
        : MyProcess('fooarg','bararg',baz='bazarg')
        '''
        pass

    def __pre_handle_message(self):
        pass

    def __post_handle_message(self, rc):
        pass

    def handle_message(self, message):
        '''
        The method to respond to messages sent to this process.  It's called
        by get_ids(),receive() and inpt() so if you use any of those you need
        to redefine this and implement your message handling here.
        '''
        raise NotImplementedError( 'Someone has sent you a message ({0}).  You must override this method to handle it.'.format(str(message)) )

class Resident(Process):
    '''
    Prototype for a multitools.Process class that only implements
    handle_message(), and doesn't have an op() (note it may still
    implement a setup() method for class arguments)

    It will stay alive until all other processes have finished.
    '''
    RESIDENT=True # Enable ResidentTermMessages
    INTERVAL=1 # Seconds

    def op(self):
        while not self.stopped.is_set():
            time.sleep(self.INTERVAL)

### Test code ############################################################

import unittest
import time
import multiprocessing.sharedctypes

class FakeMessage(object):
    def __init__(self, target, val):
        self.target=target
        self.val=val

class TestProcess(unittest.TestCase):
    class TestP(Process):
        pass

    def setUp(self):
        start=time.time()
        self.p=TestProcess.TestP()
        self.tick=(time.time()-start)*5

    def test_init(self):
        self.assertRaises(NotImplementedError,Process)

    def test_set_pipe(self):
        a=object()
        self.p.set_pipe(a)
        self.assertIs(self.p.pipe, a)

    def test_set_poll(self):
        self.p.set_poll(4)
        self.assertEqual(self.p.poll_time,4)
        self.p.set_poll(time = 1.5)
        self.assertEqual(self.p.poll_time,1.5)

    def test_send_object(self):
        class TestP(Process):
            def op(self):
                self.send_object(int(1))

        p=TestP()
        (this, that)=multiprocessing.Pipe()
        p.set_pipe(that)
        p.start()
        p.join()
        m=this.recv()
        self.assertTrue(isinstance(m,int))
        self.assertEqual(m, 1)

    def test_send_message(self):
        class TestP(Process):
            def op(self_):
                self_.send_message([1234], FakeMessage, "value")

        p=TestP()
        (this, that)=multiprocessing.Pipe()
        p.set_pipe(that)
        p.start()
        p.join()
        m=this.recv()
        self.assertTrue(isinstance(m,FakeMessage))
        self.assertEqual(m.target, 1234)
        self.assertEqual(m.val,"value")

    '''
    def test_get_lock(self):
        class TestP(Process):
            p_id=None
            sup_id=None
            def setup(self, failed, count):
                self.lock=self.get_lock()
                self.failed=failed
                self.count=count

            def op(self_):
                with self_.lock:
                    if self_.count.value!=0:
                        print("ERROR: Op lock not gained first!")
                        self_.failed.set()
                    else:
                        self_.count.value+=1
                        time.sleep(self.tick*4)

            def handle_message(self, m):
                with self.lock:
                    if self.count.value!=1:
                        print("ERROR: Handle message lock not gained after op lock!")
                        self.failed.set()
                    else:
                        self.count.value+=1
                pass

        failed=multiprocessing.Event()
        count=multiprocessing.sharedctypes.Value('b')
        count.value=0
        tp=TestP(failed,count)
        tp.set_poll(self.tick)
        (this, that)=multiprocessing.Pipe()
        tp.set_pipe(that)
        tp.start()
        this.send("message")
        tp.join()
        with tp.lock:
            self.assertFalse(failed.is_set())
            self.assertEqual(count.value, 2, "Test did not complete")
''' # Disabled due to segfaulting, in about 4/5 runs!

    def test_prnt(self):
        class TestP(Process):
            sup_id='supervisor'
            def op(self):
                self.prnt('Test prnt')

        tp=TestP()
        (this, that)=multiprocessing.Pipe()
        tp.set_pipe(that)
        tp.start()
        tp.join()
        m=this.recv()
        self.assertEqual(str(m), 'Test prnt')
        self.assertIs(type(m),multitools.ipc.PrntMessage)
        self.assertFalse(this.poll())

    def test_inpt(self):
        class TestP(Process):
            sup_id='supervisor'
            p_id='process_testprnt'
            def op(self_):
                self.assertEqual(self_.inpt('Test prompt'),'Test response')

        tp=TestP()
        tp.set_poll(self.tick)
        (this, that)=multiprocessing.Pipe()
        tp.set_pipe(that)
        tp.start()
        m=this.recv()
        self.assertIs(type(m),multitools.ipc.InputMessage,str(m))
        self.assertEqual(m.prompt, 'Test prompt')
        this.send(multitools.ipc.InputResponseMessage(m.source,'Test response'))
        tp.join(self.tick*5)
        while this.poll():
            self.assertFalse(True, this.recv())
        self.assertFalse(tp.is_alive())

        class NoIdP(Process):
            def op(self_):
                self.assertRaises(ClientException, self_.inpt)

        tp=NoIdP()
        tp.start()
        tp.join(self.tick*5)
        self.assertFalse(tp.is_alive())

    def test_get_ids(self):
        class TestP(Process):
            sup_id=None
            p_id=None
            def op(self_):
                self.assertEqual(self_.get_ids("Test name",block=False),set())
                while not 'Test name' in self_.ids.keys():
                    time.sleep(self_.poll_time)
                ids=self_.get_ids("Test name")
                self.assertEqual(len(ids),1)
                self.assertEqual(ids.pop(),"1234")
                self_.prnt("Test finished")

        tp=TestP()
        tp.set_poll(self.tick)
        (this, that)=multiprocessing.Pipe()
        tp.set_pipe(that)
        tp.start()
        self.assertEqual(this.recv().name,"Test name")
        this.send(multitools.ipc.IdsReplyMessage("test id",set(["1234"]) ))
        tp.join(self.tick)
        time.sleep(self.tick*3)
        self.assertFalse(tp.is_alive())
        self.assertTrue(this.poll())
        m=this.recv()
        self.assertIsInstance(m, multitools.ipc.PrntMessage, str(m))
        while this.poll():
            self.assertTrue(False, "Unexpected in the message queue:"+str(this.recv()))

        class BadP(Process):
            def op(self_):
                #TODO Convert all process assertions to use a flag
                self.assertRaises(ClientException, self_.get_ids, 'foo')

        tp=BadP()
        tp.start()
        tp.join(self.tick*2)

    def test_join(self):
        class TestP(Process):
            def op(self_):
                time.sleep(self.tick*20)

        p=TestP()
        self.assertRaises(AssertionError, p.join)
        p.start()
        start=time.time()
        p.join(timeout=self.tick*10)
        self.assertAlmostEqual(time.time()-start,self.tick*10,delta=self.tick*4)
        self.assertTrue(p.is_alive())
        p.terminate()
        p=TestP()
        start=time.time()
        p.start()
        p.join(self.tick*15)
        self.assertAlmostEqual(time.time()-start,self.tick*15,delta=self.tick*4)
        self.assertTrue(p.is_alive())
        p.terminate()
        p=TestP()
        p.start()
        start=time.time()
        p.join()
        self.assertAlmostEqual(time.time()-start,self.tick*20,delta=self.tick*4)

    def test_start(self):
        class TestP(Process):
            sup_id=None
            def op(self_):
                self_.prnt('Started')
                time.sleep(self.tick*10)

        p=TestP()
        (this, that)=multiprocessing.Pipe()
        p.set_pipe(that)
        # Test process starts
        p.start()
        self.assertEqual(this.recv().message,'Started')
        p.terminate()
        start=time.time()
        while p.is_alive() and time.time()-start<self.tick*20:
            time.sleep(self.tick)
        self.assertLessEqual(time.time()-start,self.tick*15)

        # TODO
        # # Test process can be restarted
        # (this, that)=multiprocessing.Pipe()
        # p.set_pipe(that)
        # p.start()
        # self.assertTrue(this.poll())
        # self.assertEqual(this.recv().message,'Started')
        # p.terminate()

    def test_handle_message(self):
        messages=[1,"string",FakeMessage("foo","var")]
        class TestP(Process):
            p_id=None # Needed to make handle_message get called
            sup_id=None
            INTERVAL=0.1
            def setup(self,finished,failed):
                self.index=0
                self.finished=finished
                self.failed=failed

            def op(self):
                while not self.finished:
                    time.sleep(self.poll_time)

            def handle_message(self, m):
                if self.index >= len(messages):
                    print("ERROR: Received too many messages; expected {0}, got {1}".format(len(messages),self.index+1))
                    self.failed.set()
                else:
                    expected=messages[self.index]
                    if isinstance(m, FakeMessage):
                        if expected.target!=m.target or expected.val!=m.val:
                            print("ERROR: Unexpected message; expected '{0}' to {1}, got '{2}' to {3}".format(expected.val, expected.target, m.val, m.target))
                            self.failed.set()
                    else:
                        if expected != m:
                            print("ERROR: Unexpected message; expected '{0}' got '{1}'".format(str(expected),str(m)))
                            self.failed.set()
                    self.index += 1
                    if self.index == len(messages):
                        self.finished.set()
                        return False

        finished=multiprocessing.Event()
        failed=multiprocessing.Event()
        tp=TestP(finished,failed)
        tp.set_poll(self.tick)
        (this,that)=multiprocessing.Pipe()
        tp.set_pipe(that)
        tp.start()
        for m in messages:
            this.send(m)
        tp.join(self.tick*10)
        self.assertFalse(tp.is_alive())
        if tp.is_alive():
            tp.terminate()
        self.assertTrue(finished.is_set())
        if this.poll():
            # Sent an exception?
            self.assertTrue(False,str(this.recv()))
        self.assertFalse(failed.is_set())

    def test_op(self):
        class badP(Process):
            def op(self):
                self.val.set()

        tp=badP()
        tp.val=multiprocessing.Event()
        tp.start()
        tp.join()
        self.assertTrue(tp.val.is_set())

        class testP(Process):
            def op(self_):
                time.sleep(self.tick*2)

        tp=testP()
        start=time.time()
        tp.start()
        tp.join()
        self.assertGreaterEqual(time.time()-start,self.tick)

class TestResident(unittest.TestCase):
    def test_handle_message(self):
        class TestP(Resident):
            p_id=None # Needed to make handle_message get called
            sup_id=None

        start=time.time()
        tp=TestP()
        (this,that)=multiprocessing.Pipe()
        tp.set_pipe(that)
        tp.INTERVAL=time.time()-start
        tp.start()
        self.assertTrue(tp.is_alive())
        this.send(multitools.ipc.ResidentTermMessage(None))
        time.sleep(tp.poll_time*4)
        self.assertFalse(tp.is_alive())
        tp.join()
        if this.poll():
            print(this.recv())
            self.assertTrue(False, 'Process sent a message (maybe an exception?')

if __name__=='__main__':
    unittest.main()
