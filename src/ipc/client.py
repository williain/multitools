#!/usr/bin/env python2

import sys, multiprocessing, traceback, collections, Queue
import multitools.ipc 

class Process(multiprocessing.Process):
    '''
    Interface for your own classes specially designed for use with ProcessList
    helping you pass messages between processes.

    Derive from this class and implement op() with whatever arguments you
    deem fit.  Then instantiate it, passing in the values for those arguments
    and pass the object to ProcessList.add() or add_list().

    To implement message passing, write messages using self.send() and
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
            if not hasattr(self, 'M_NAME'):
                print "WARNING: Must set a string 'M_NAME' for your Process"
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

    def send(self, target_ids, m_type, *args):
        '''
        Message object sender. Arguments:
        target_ids - The recipient ids of the message e.g. the results of a
                     call to get_ids(), 0 for all ids
        m_type     - the type of the message object to send e.g, EmptyMessage
        other args - further positional arguments are sent as arguments to the
                     message constructor
        Examples:
            # Send a DemoMessage instance to the process with M_NAME=='target'
            self.send(self.get_ids('target'),DemoMessage,"DemoVal")
            # Send a DemoMessage to all registered processes
            self.send(0,DemoMessage,"DemoVal")
            # Send a DemoMessage only to no processess except those listening
            # for the type DemoMessage.
            self.send(1,DemoMessage,"DemoVal")
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
                print "Instantiation error; {0}{1}".format(m_type.__name__,(t,)+args)
                raise
            self.pipe.send(m)

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
        self.send(self.sup_id, multitools.ipc.StringMessage,
          " ".join([str(arg) for arg in args])
        )

    def inpt(self, prompt=None):
        '''
        Replacement for the raw_input function.  Triggers
        ProcessList.supervise() to block and wait for input in the parent
        process, and blocks this function call too (although handle_message
        will be invoked for any messages received while blocking).
        '''
        self.pipe.send(multitools.ipc.InputMessage(self.sup_id,self.m_id,prompt))
        while True:
            m=self.pipe.recv()
            if isinstance(m,multitools.ipc.InputResponseMessage):
                return str(m)
            else:
                self.__handle_message(m)

    def get_ids(self, name, block=True, sleep=0.5):
        '''
        Get the set of ids which correspond to the process name supplied.

        Note this function blocks by default, waiting for a response from the
        supervisor.

        A non-blocking get_ids() call will only return a set of ids if it's
        already cached them.  It it's sensible for your task, you can make a
        non-blocking call first of all then get on with some work (discarding
        the result of that call), before later getting them using a blocking
        call to get_ids when you actually need the id, which will use the
        cached value if it's already got it, or process the messages
        containing the answer you need which was triggered by your first call.

        You can set this to a non-blocking call by passing block=False as an
        argument.  If you don't do that, you can tune the maximum latency for
        receiving messages versus CPU load by reducing or increasing the sleep
        value respectively.

        If an invalid name is given, you will receive back the empty set
        '''
        if not name in self.ids:
            self.receive_all()
            if not name in self.ids:
                self.send(self.sup_id, multitools.ipc.GetIdsMessage, self.m_id, name)
                self.queries.append(name)
                if block==False:
                    return set()
                else:
                    while not name in self.ids:
                        self.receive(sleep=sleep)

        return self.ids[name]

    def __wrap_op(self, *args, **kwargs):
        # Preassigned exception message in case of truly exceptional
        # circumstances (e.g. MemoryError)
        crash=multitools.ipc.ExceptionMessage(self.sup_id, self.m_id,
          RuntimeError("Unable to process exception; aborting!")
        )
        try:
            self.op(*args, **kwargs)
        except Exception as e:
            # Hack to preserve the original traceback in the exception message
            if self.pipe:
                try:
                    (_, _, tb) = sys.exc_info()
                    e.args=(e.args[:-1])+(str(e.args[-1])+"\nOriginal traceback:\n"+"".join(traceback.format_tb(tb)),)
                    self.pipe.send(multitools.ipc.ExceptionMessage(
                      self.sup_id, self.m_id, e
                    ))
                except Exception as e:
                    try:
                        self.pipe.send(multitools.ipc.ExceptionMessage(
                          self.sup_id, self.m_id, e
                        ))
                    except Exception:
                        self.pipe.send(crash)
            else:
                raise
        if self.pipe:
            self.pipe.close()

    def receive(self, block=True, sleep=0.5):
        '''
        Call this to check for messages and respond to them.  Note you need to
        have implemented handle_messages() to use this.

        Args:
          block - If False, check only for the first message already queued up.
                  If True, check periodically for messages until one is
                  received.
          sleep - If blocking, the time to wait between checking for any
                  messages to turn up.

        Raises:
          Queue.Empty - If not blocking, and no messages are queued.
        '''
        if block:
            while not self.pipe.poll():
                time.sleep(sleep)
            self.__handle_message(self.pipe.recv())
        else:
            if self.pipe.poll():
                self.__handle_message(self.pipe.recv())
            else:
                raise Queue.Empty()

    def receive_all(self):
        '''
        Receive all the messages in the queue.  If the queue is empty when
        called, this simply returns immediately
        '''
        try:
            while True:
                self.receive(block=False)
        except Queue.Empty:
            pass

    def __handle_message(self, m):
        if isinstance(m, multitools.ipc.IdsReplyMessage):
            try:
                name=self.queries.popleft()
                self.ids[name]=m.ids
            except IndexError:
                raise multitools.ipc.SupervisorException(
                  "{0}: IdsReplyMessage received for no query".format(
                    self.m_id
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

class TestProcess(unittest.TestCase):
    def testInit(self):
        self.assertRaises(NotImplementedError,Process)

    def testOp(self):
        class badP(Process):
            M_NAME="BadP"
            sup_id='supervisor'
            m_id='process_1'
            def op(self):
                super(badP,self).op() # Uh-oh!

        tp=badP()
        (this,that)=multiprocessing.Pipe()
        tp.set_pipe(that)
        tp.start()
        tp.join()
        m=this.recv()
        self.assertIsInstance(m,multitools.ipc.ExceptionMessage)
        self.assertRaises(NotImplementedError, m.rais)

        class testP(Process):
            M_NAME="TestP"
            sup_id='supervisor'
            m_id='process_2'
            def op(self):
                time.sleep(1)

        tp=testP()
        start=time.time()
        tp.start()
        tp.join()
        self.assertGreaterEqual(time.time()+1, start)

    def testPrnt(self):
        class testProcess(Process):
            M_NAME='testProcess'
            sup_id='supervisor'
            m_id='process_testprnt'
            def op(self):
                self.prnt('Test prnt')

        tp=testProcess()
        (this, that)=multiprocessing.Pipe()
        tp.set_pipe(that)
        tp.start()
        tp.join()
        m=this.recv()
        self.assertEqual(str(m), 'Test prnt')
        self.assertIsInstance(m,multitools.ipc.StringMessage)
        self.assertFalse(this.poll())

    def testInpt(self):
        # Can't be easily tested automatically since it blocks on user input
        # Thankfully it's a two liner, and should be pretty obvious if it
        # doesn't work.
        pass

if __name__=='__main__':
    unittest.main()
