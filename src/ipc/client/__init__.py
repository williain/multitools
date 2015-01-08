#!/usr/bin/env python
from __future__ import print_function

import sys, multiprocessing, traceback, collections
try:
    import queue
except ImportError:
    import Queue as queue
import multitools.ipc 

class Process(multiprocessing.Process):
    '''
    Interface for your own classes specially designed for use with ProcessList
    helping you pass messages between processes.

    Derive from this class and implement op() with whatever arguments you
    deem fit.  Then instantiate it, passing in the values for those arguments
    and pass the object to ProcessList.add() or add_list().

    To implement message passing, write messages using self.send_message() and
    get them by implementing handle_message() in the targetted process and
    calling self.receive() periodically in your op() there.
    '''
    # M_NAME = "Set this to give your thing a name"
    LISTEN_TO=[]
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
            super(Process, self).__init__(target=self.__wrap_op,args=args,kwargs=kwargs)

    def set_pipe(self, pipe):
        '''
        Setter for this process's input/output Pipe.  Mostly for use by
        ProcessList, so it can poll for messages
        '''
        self.pipe=pipe

    def send_object(self, object):
        '''
        Send an object to the supervisor, to be picked up by the object
        handler.  See send_message for sending message objects to other
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

    def get(self, timeout=None, sleep=None):
        '''
        Call this to check for messages and respond to them.  Note you need to
        have implemented handle_messages() to use this.

        Args:
          timeout - Block if set to None (the default), else block until the
                    timeout is expired.
          sleep   - If a timeout is set, the time to wait between checking
                    whether the timeout is exceeded.  Default is to check ten
                    times (i.e. sleep=timeout/10)

        Raises:
          queue.Empty - If timed out, and no messages are queued.
        '''

        if timeout==None:
            #Blocking invocation
            return self.pipe.recv()
        else:
            start=time.time()
            if sleep==None:
                sleep=timeout/10
            while time.time()<start+timeout:
                if self.pipe.poll():
                    return self.pipe.recv()
                else:
                    time.sleep(sleep)
            if self.pipe.poll():
                return self.pipe.recv()
            else:
                raise queue.Empty("get() did not receive any input in the timeout specified")

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
            self.receive_all()
            if not name in self.ids:
                self.send_object(
                    multitools.ipc.GetIdsMessage(self.sup_id, self.p_id, name)
                )
                self.queries.append(name)
                if block==False:
                    return set()
                else:
                    while not name in self.ids:
                        self.receive()

        return self.ids[name]

    def __wrap_op(self, *args, **kwargs):
        if not hasattr(self,'p_id'):
            # Not a communicative process
            self.op(*args,**kwargs)
        else:
            # Preassigned exception message in case of truly exceptional
            # circumstances (e.g. MemoryError)
            crash=multitools.ipc.ExceptionMessage(self.sup_id, self.p_id,
              RuntimeError("Unable to process exception; aborting!")
            )
            try:
                self.op(*args, **kwargs)
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

    def receive(self, timeout=None, sleep=None):
        '''
        Call this to check for messages and respond to them.  Note you need to
        have implemented handle_messages() to use this.

        Args:
          timeout - Block if set to None (the default), else block until the
                    timeout is expired.
          sleep   - If not blocking, the time to wait between checking if the
                    timeout has expired

        Raises:
          queue.Empty - If not blocking, and no messages are queued.
        '''
        return self.__handle_message(self.get(timeout=timeout, sleep=sleep))

    def receive_all(self):
        '''
        Receive all the messages in the queue.  If the queue is empty when
        called, this simply returns immediately
        '''
        try:
            while True:
                self.receive(timeout=0)
        except queue.Empty:
            pass

    def __handle_message(self, m):
        if isinstance(m, multitools.ipc.IdsReplyMessage):
            try:
                name=self.queries.popleft()
                self.ids[name]=m.ids
            except IndexError:
                raise multitools.ipc.SupervisorException(
                  "{0}: IdsReplyMessage received for no query".format(
                    self.p_id
                  )
                )
        else:
            return self.handle_message(m)

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
        raise NotImplementedError('This method is an example that should be completely overridden (don\'t call super().op())')

    def handle_message(self, message):
        '''
        The method to respond to messages sent to this process.  It's called
        by get_ids(),receive() and inpt() so if you use any of those you need
        to redefine this and implement your message handling here.

        Your op() needs to call receive() periodically to be able to respond
        to new messages (including any replies to get_ids()
        '''
        raise NotImplementedError('This method is an example that should be overridden')

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

    def testInit(self):
        self.assertRaises(NotImplementedError,Process)
        p=self.TestP() # Subclasses don't error


    def test_set_pipe(self):
        p=self.TestP()
        a=object()
        p.set_pipe(a)
        self.assertIs(p.pipe, a)

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

    def test_get(self):
        class TestP(Process):
            M_NAME=None
            def op(self_):
                self.assertEqual(self_.get().val,"Test message")
                self.assertRaises(queue.Empty,self_.get,timeout=0)
                start=time.time()
                timeout=1.5
                self.assertRaises(queue.Empty,self_.get,timeout=timeout)
                dur=time.time()-start
                self.assertGreaterEqual(dur,timeout)
                self.assertLess(dur-timeout,timeout/5.0)

        tp=TestP()
        (this,that)=multiprocessing.Pipe()
        tp.set_pipe(that)
        tp.start()
        this.send(FakeMessage(1234,"Test message"))
        tp.join()

    def testPrnt(self):
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

    def testInpt(self):
        # Can't be easily tested automatically since it blocks on user input
        # Thankfully it's a two liner, and should be pretty obvious if it
        # doesn't work.
        pass

    def test_get_ids(self):
        class TestP(Process):
            M_NAME=None
            sup_id=None
            p_id=None
            def op(self_):
                self.assertEqual(self_.get_ids("Test name",block=False),None)
                ids=self_.get_ids("Test name 2")
                self.assertEqual(len(ids),1)
                self.assertEqual(ids.pop(),"1234")

        tp=TestP()
        (this, that)=multiprocessing.Pipe()
        tp.set_pipe(that)
        tp.start()
        self.assertEqual(this.recv().name,"Test name")
        this.send(multitools.ipc.IdsReplyMessage(set("1234"),"test id"))

    def test_receive(self):
        class TestP(Process):
            M_NAME=None
            def op(self_,terminated):
                self_.terminated=terminated
                self_.messages=0
                while self_.receive():
                    pass

            def handle_message(self_,m):
                self.assertTrue(isinstance(m,FakeMessage))
                if self_.messages==0:
                    self.assertEqual(m.val,"Test message")
                    self_.messages+=1
                if m.val=='quit':
                    if self_.messages == 1:
                        self_.terminated.value=True
                        return False
                return True

        terminated=multiprocessing.Value('b',False)
        p=TestP(terminated)
        (this,that)=multiprocessing.Pipe()
        p.set_pipe(that)
        p.start()
        this.send(FakeMessage("1234","Test message"))
        this.send(FakeMessage("quit","quit"))
        p.join()
        self.assertEqual(terminated.value,True)

    def test_receive_all(self):
        total=200
        class TestP(Process):
            M_NAME=None
            def op(self_,finished):
                self_.messages=0
                self_.finished=finished
                while self_.receive():
                    pass

            def handle_message(self_,m):
                self.assertTrue(isinstance(m,FakeMessage))
                if self_.messages==total:
                    self.assertEqual(m.val,"Test message "+str(total))
                    self_.finished.value=True
                    return False
                else:
                    self.assertEqual(m.val,"Test message "+str(self_.messages))
                self_.messages+=1
                return True

        finished=multiprocessing.Value('b',False)
        p=TestP(finished)
        (this,that)=multiprocessing.Pipe()
        p.set_pipe(that)
        p.start()
        for i in range(total+1):
            this.send(FakeMessage("1234","Test message "+str(i)))
        p.join()
        self.assertEqual(finished.value,True)

    def testOp(self):
        class badP(Process):
            M_NAME="BadP"
            sup_id='supervisor'
            p_id='process_1'
            def op(self):
                super(badP,self).op() # Uh-oh!

        tp=badP()
        (this,that)=multiprocessing.Pipe()
        tp.set_pipe(that)
        tp.start()
        tp.join()
        m=this.recv()
        self.assertTrue(isinstance(m,multitools.ipc.ExceptionMessage))
        self.assertRaises(NotImplementedError, m.rais)

        class testP(Process):
            M_NAME="TestP"
            sup_id='supervisor'
            p_id='process_2'
            def op(self):
                time.sleep(1)

        tp=testP()
        start=time.time()
        tp.start()
        tp.join()
        self.assertGreaterEqual(time.time()+1, start)

if __name__=='__main__':
    unittest.main()
