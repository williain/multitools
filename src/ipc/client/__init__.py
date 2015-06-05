#!/usr/bin/env python
from __future__ import print_function

import sys, multiprocessing, traceback, collections
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
            # TODO Move this check to the supervisor, and guard for non-set p_ids etc. before every use
            if not hasattr(self, 'M_NAME'):
                print("WARNING: Must set a string 'M_NAME' for your Process")
            self.queries=collections.deque()
            self.ids={}
            self.pipe=None
            self.set_poll()
            self.process=None
            self.stopped=multiprocessing.Event()
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
        self.process.start()
        self.thread.start()

    def join(self, timeout=None):
        '''
        Wait for the process to terminate
        '''
        #TODO Handle timeout
        if self.process:
            while self.process.is_alive():
                time.sleep(self.poll_time*2)
            self.stopped.set()
        else:
            # TODO:Throw exception?
            print("DEBUG: No process to join!")
            pass

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
        Replacement for the raw_input function.  Triggers
        ProcessList.supervise() to block and wait for input in the parent
        process, and blocks this function call too (although handle_message
        will be invoked for any messages received while blocking).
        '''
        self.send_object(
          multitools.ipc.InputMessage(self.sup_id,self.p_id,prompt)
        )
        while True:
            m=self.pipe.recv()
            if isinstance(m,multitools.ipc.InputResponseMessage):
                return m.message
            else:
                self.__handle_message(m)

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
        if not name in self.ids:
            while self.pipe.poll():
                self.__handle_message(self.pipe.recv()) # TODO Test for false?

            if not name in self.ids:
                self.send_object(
                    multitools.ipc.GetIdsMessage(self.sup_id, self.p_id, name)
                )
                self.queries.append(name)
                if block==False:
                    return set()
                else:
                    while not name in self.ids:
                        self.__handle_message(self.pipe.recv())

        return self.ids[name]

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
                name=self.queries.popleft()
                self.ids[name]=m.ids
            except IndexError:
                raise ClientException(
                  "{0}: IdsReplyMessage received for no query".format(
                    self.p_id
                  )
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

import unittest, time

class FakeMessage(object):
    def __init__(self, target, val):
        self.target=target
        self.val=val

class TestProcess(unittest.TestCase):
    class TestP(Process):
        M_NAME=None
        pass

    def test_init(self):
        self.assertRaises(NotImplementedError,Process)
        p=self.TestP() # Subclasses don't error

    def test_set_pipe(self):
        p=self.TestP()
        a=object()
        p.set_pipe(a)
        self.assertIs(p.pipe, a)

    def test_set_poll(self):
        p=self.TestP()
        p.set_poll(4)
        self.assertEqual(p.poll_time,4)
        p.set_poll(time = 1.5)
        self.assertEqual(p.poll_time,1.5)

    def test_send_object(self):
        class TestP(Process):
            M_NAME=None
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
            M_NAME=None
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

    def test_prnt(self):
        class TestP(Process):
            M_NAME='testProcess'
            sup_id='supervisor'
            p_id='process_testprnt'
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
        # Can't be easily tested automatically since it blocks on user input
        # Thankfully it's a two liner, and should be pretty obvious if it
        # doesn't work.
        #TODO Can be tested with a fake supervisor
        pass

    def test_get_ids(self):
        class TestP(Process):
            M_NAME=None
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
        (this, that)=multiprocessing.Pipe()
        tp.set_pipe(that)
        tp.start()
        self.assertEqual(this.recv().name,"Test name")
        this.send(multitools.ipc.IdsReplyMessage("test id",set(["1234"]) ))
        tp.join()
        time.sleep(tp.poll_time)
        self.assertTrue(this.poll())
        m=this.recv()
        self.assertIsInstance(m, multitools.ipc.PrntMessage, str(m))
        while this.poll():
            self.assertTrue(False, "Unexpected in the message queue:"+str(this.recv()))

    def test_handle_message(self):
        class TestP(Process):
            M_NAME=None
            p_id=None
            sup_id=None

            def setup(self_,terminated):
                self_.terminated=terminated
                self_.messages=0

            def op(self_):
                while not self_.terminated.is_set():
                    pass

            def handle_message(self_,m):
                self.assertTrue(isinstance(m,FakeMessage))
                if self_.messages==0:
                    self.assertEqual(m.val,"Test message")
                    self_.messages+=1
                    self.assertTrue(self_.messages<=1)
                if m.val=='quit':
                    self.assertEqual(self_.messages,1)
                    self_.terminated.set()

        terminated=multiprocessing.Event()
        p=TestP(terminated)
        (this,that)=multiprocessing.Pipe()
        p.set_pipe(that)
        p.start()
        this.send(FakeMessage("1234","Test message"))
        this.send(FakeMessage("1234","quit"))
        p.join()
        self.assertTrue(terminated.is_set())
        if this.poll():
            # Sent an exception?
            self.assertTrue(False,str(this.recv()))

        # Test handle_message returning False
        class TestFalseFinish(Process):
            M_NAME=None
            p_id=None
            sup_id=None

            def op(self):
                while True:
                    pass

            def handle_message(self,m):
                return False

        p=TestFalseFinish()
        (this,that)=multiprocessing.Pipe()
        p.set_pipe(that)
        p.start()
        this.send(FakeMessage("1234","quit"))
        start=time.time()
        while p.is_alive() and time.time()-start<2:
            time.sleep(0.1)
        self.assertFalse(p.is_alive())

    def test_op(self):
        class badP(Process):
            M_NAME="BadP"
            def op(self):
                self.val.set()

        tp=badP()
        tp.val=multiprocessing.Event()
        tp.start()
        tp.join()
        self.assertTrue(tp.val.is_set())

        class testP(Process):
            M_NAME="TestP"
            def op(self):
                time.sleep(0.25)

        tp=testP()
        start=time.time()
        tp.start()
        tp.join()
        self.assertGreaterEqual(time.time()+0.25, start)

class TestResident(unittest.TestCase):
    def test_handle_message(self):
        messages=[1,"string",FakeMessage("foo","var")]
        class TestP(Resident):
            M_NAME="TestP"
            p_id=None
            sup_id=None
            INTERVAL=0.1
            def setup(self_,finished):
                self_.index=0
                self_.finished=finished

            def handle_message(self_, m):
                self.assertLess(self_.index,len(messages))
                if isinstance(m, FakeMessage):
                    self.assertEqual(messages[self_.index].target,m.target)
                    self.assertEqual(messages[self_.index].val,m.val)
                else:
                    self.assertEqual(messages[self_.index],m)
                self_.index+=1
                if self_.index>=len(messages):
                    self_.finished.set()
                    return False

        finished=multiprocessing.Event()
        tp=TestP(finished)
        (this,that)=multiprocessing.Pipe()
        tp.set_pipe(that)
        tp.start()
        for m in messages:
            this.send(m)
        tp.join()
        if this.poll():
            print(this.recv())
            self.assertTrue(False, 'Process sent a message (maybe an exception?')
        self.assertTrue(finished.is_set())

if __name__=='__main__':
    unittest.main()
