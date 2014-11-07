#!/usr/bin/python2

'''
Multitools

A utility class providing you tools to work with multiple multiprocessing
Process objects and to pass messages between them.
'''
# TODO: Use collections.deque for query list in Process?
# TODO: Investigate using a duplex Pipe rather that two Queues

import multiprocessing, pickle, Queue, sys, traceback, copy
#import pdb # For debugging

class SupervisorException(Exception):
    pass

class EmptyMessage(object):
    '''
    An empty message passed from source to target within the ProcessList.
    This is the base class for all messages.
    '''
    def __init__(self, target):
        self.target=target

    def __str__(self):
        return "{0} to {1}".format(type(self).__name__, self.target)

class StringMessage(EmptyMessage):
    '''
    A message containing a string argument
    '''
    def __init__(self, target, message):
        self.message=message
        super(StringMessage, self).__init__(target)

    def __repr__(self):
        return "{0}:{1}".format(super(StringMessage,self).__str__(), self.message)

    def __str__(self):
        return self.message

class FileMessage(EmptyMessage):
    '''
    Base class for all messages informing listeners about a file being generated
    '''
    def __init__(self, target, filename):
        self.filename=filename
        super(FileMessage, self).__init__(target)

    def __str__(self):
        return "{0}:{1}".format(super(FileMessage, self).__str__(), self.filename)

class QueryMessage(EmptyMessage):
    '''A message representing a query'''
    def __init__(self, target, source):
        self.source=source
        super(QueryMessage, self).__init__(target)

    def __str__(self):
        return "{0} from {1} to {2}".format(
          type(self).__name__, self.source, self.target
        )

class InputMessage(QueryMessage):
    '''
    A message signifying we want user input
    '''
    def __init__(self, target, source, prompt=None):
        self.prompt=prompt
        super(InputMessage, self).__init__(target, source)

    def __str__(self):
        return "{0}: {1}".format(
          super(InputMessage, self).__str__(), self.prompt
        )

class InputResponseMessage(StringMessage):
    '''
    A response to an InputMessage
    '''
    pass

class GetIdsMessage(QueryMessage):
    '''
    A message requesting the ids of concurrent processess
    '''
    def __init__(self, target, source, name):
        self.name=name
        super(GetIdsMessage, self).__init__(target, source)

    def __str__(self):
        return "{0} about {1}".format(
          super(GetIdsMessage, self).__str__(), self.name
        )

class IdsReplyMessage(EmptyMessage):
    '''
    A message replying to an id query with the ids requested
    '''
    def __init__(self, target, ids):
        self.ids=ids
        super(IdsReplyMessage, self).__init__(target)

    def __str__(self):
        return "{0}: {1}".format(
          super(IdsReplyMessage, self).__str__(), self.ids
        )

class ExceptionMessage(EmptyMessage):
    '''
    A system message passed when an exception is trapped
    '''
    def __init__(self, target, source, e):
        self.source=source
        self.pickled_e=pickle.dumps(e,pickle.HIGHEST_PROTOCOL)
        super(ExceptionMessage, self).__init__(target)

    def rais(self):
        raise pickle.loads(self.pickled_e) # Passing on exception from sub process

    def __repr__(self):
        return "From {0}:{1}".format(self.source, str(super(ExceptionMessage, self)))

    def __str__(self):
        return str(pickle.loads(self.pickled_e))

class ProcessList(object):
    '''
    A wrapper class to collect together a bunch of multiprocessing.Process
    objects and apply functions like start(), join() to them all, as well as
    supervisor functions to automate passing messages between processes
    '''
    def __init__(self):
        self.m_id=hex(id(self))
        self.processes=[]

    def add(self, process):
        '''
        Add a Process to be later start()ed or supervise()d

        Process subclasses which have set_input() and set_output() functions
        will have their inputs and outputs configured for use by the supervisor
        '''
        process.m_id="{0}_{1}".format(self.m_id, str(len(self.processes)+1))
        process.sup_id=self.m_id
        record=[process,None,None]
        if hasattr(process, 'set_output'):
            record[1]=multiprocessing.Queue()
            process.set_output(record[1])
        if hasattr(process, 'set_input'):
            record[2]=multiprocessing.Queue()
            process.set_input(record[2])
        self.processes.append(tuple(record))
        return record[2]

    def add_list(self, processes):
        '''
        Add a list of Processes to be later start()ed
        '''
        inputs=[]
        for p in processes:
            inputs.append(self.add(p))
        return inputs

    def start(self):
        '''
        Start all Processes
        '''
        for p in self.processes:
            p[0].start()

    def is_alive(self):
        '''
        Return True if any Processes are still running
        '''
        alive=False
        for p in self.processes:
            if p[0].is_alive(): alive=True
        return alive

    def join(self,timeout=None):
        '''
        Join all Processes.  Block until all Procesesses have terminated, or
        until the timeout is over

        Options:
        timeout - Number of seconds (may be fractional) to block for per process
        '''
        for p in self.processes:
            p[0].join(timeout)

    def terminate(self):
        '''
        Terminate all Processes, for an emergency shutdown.  See the
        multiprocessing docs for warnings about Process.terminate().
        '''
        for p in self.processes:
            p[0].terminate()

    # Supervisor-type functions - Inter-process communication

    def __get_all(self, block, timeout=None):
        for p in self.processes:
            try:
                out=p[1]
                if out!=None:
                    return out.get(block=block,timeout=timeout)
            except Queue.Empty:
                pass
        raise Queue.Empty("No processes produced an output")

    def get_message(self, block=True, timeout=None):
        '''
        Scan the processes for output.
        Options:
            block - Block until output is given.  If False, raises Queue.Empty
                    if no processes have raised output, and disregard timeout.
            timeout - If block is True, wait per timeout, and raise Queue.Empty
                      only if all processes provided no output during this time.
        Raises:
            Queue.Empty - If non-blocking or timeout was exceeded and no
                          messages were received.
        Returns:
            The message sent (normally expected to be a Message object)
        '''
        if block:
            if timeout:
                poll_time=timeout/len(self.processes)/10.0
                for i in range(1,10):
                    try:
                        return self.__get_all(block, poll_time)
                    except Queue.Empty:
                        pass
                raise Queue.Empty("No processes returned an output")
            else:
                while True:
                    try:
                        return self.__get_all(block, 0.1)
                    except Queue.Empty:
                        pass
        else:
            # Block is false
            return self.__get_all(block)

    def __get_inpt(self, m_source):
        '''
        Get the one input queue from the process which matches the
        specified id, or get all input queues if m_source==0
        Raises:
            ValueError - If the requested id was not found
        '''
        i=[]
        for p in self.processes:
            if p[2] and (p[0].m_id == m_source or m_source==0):
                i.append(p[2])
        if len(i)==0:
            raise ValueError("No process found with id '{0}'".format(m_source))
        return i

    def __get_listeners(self, m_type):
        '''
        Return the list of input queues for the processes which listen
        to the specified message type
        '''
        try:
            parent_listeners=self.__get_listeners(m_type.mro()[1])
        except IndexError:
            parent_listeners=[]
        try:
            this_listeners=self.listening[m_type]
        except KeyError:
            this_listeners=[]
        return parent_listeners+this_listeners

    def send_object(self, target_id, message):
        '''
        Send a Message object to the targetted process, or a broadcast message
        if target_id==0, for processes that are managed by this supervisor
        Raises:
            SupervisorException - If the target_id doesn't match any of the
                                  running processes
        '''
        try:
            if target_id != 1:
                inpts = self.__get_inpt(target_id)
            else:
                inpts = self.__get_listeners(type(message))
            for i in inpts:
                if i:
                    i.put(message)
        except ValueError as e:
            raise SupervisorException("Not able to send message to process; unknown id '{0}'; message was '{1}'".format(target_id, message))

    def send(self, message):
        '''
        Helper function for sending message objects
        '''
        self.send_object(message.target, message)

    def get_ids(self, name):
        '''
        Get the ids for the processes where M_NAME matches the supplied name

        Returns the empty list if no processes match the name
        '''
        ids=[]
        for p in self.processes:
            if hasattr(p[0],'M_NAME') and p[0].M_NAME == name:
                ids.append(p[0].m_id)
        return ids

    def __handle_message(self, m, prntHandler, objHandler):
        '''
        Handle a message received by the supervisor.

        Raises:
            SupervisorException - If an invalid message is received
        '''
        if isinstance(m, EmptyMessage):
            if m.target==self.m_id:
                if isinstance(m, ExceptionMessage):
                    self.terminate()
                    m.rais()
                elif isinstance(m, QueryMessage):
                    if isinstance(m, InputMessage):
                        if m.prompt: print m.prompt
                        s = raw_input() # Blocks til user hits enter
                        self.send(InputResponseMessage(m.source, s))
                    elif isinstance(m, GetIdsMessage):
                        ids = self.get_ids(m.name)
                        # ids may be empty list if no matches
                        self.send(IdsReplyMessage(m.source, ids))
                    else:
                        raise SupervisorException("Unknown query message type {0}".format(type(m)))
                elif isinstance(m, StringMessage):
                    if prntHandler:
                        prntHandler(str(m))
                    else:
                        print m
                else:
                    # Some other Message type
                    raise SupervisorException("Unknown message type {0}".format(type(m)))
            else:
                # Message targetted at some other Process
                self.send(m)
        else:
            # Not a Message type
            if objHandler:
                objHandler(m)
            else:
                raise SupervisorException("Unknown object sent to supervisor: {0}".format(m))
        return 1

    def supervise(self, interval=0.1, prntHandler=None, finishHandler=None, objHandler=None, warn=True):
        '''
        Supervisor function to handle running the processes in parallel.
        Automates starting processes, handling messsages, and waiting
        for all to finish.  Blocks until all processes have terminated

        Options:
        interval      - How often to check for messages; default 0.1s
        finishHandler - Optional callable that gets called once everything has
                        terminated
        prntHandler   - Optional callable that gets called whenever a
                        StringMessage is received from one of the subprocesses
                        (via Process.prnt) instead of allowing it to be printed
                        to screen
        objHandler    - Optional callable to be called when a non-message
                        object gets sent, so you can use this framework for
                        your own message types (not derived from EmptyMessage)
                        if you want.
        warn - By default, the method will warn you if your processes don't
               derive from MultiProcess, thus messages from it can't be
               received.  Set this to False to use it with standard
               multiprocessing.Process objects, bearing in mind your
               msgHandler won't be called for messages from those objects.

        Raises:
        SupervisorException - raised in case of an invalid message or if no
                              msgHandler is supplied, anything other than an
                              ExceptionMessage (from raise), QueryMessage
                              (either a GetIdsMessage or from Process.inpt) or
                              a StringMessage (from Process.prnt) is received
        '''
        if warn:
            warning=False
            for p in self.processes:
                if not hasattr(p[0], 'set_output'):
                    warning=True
            if warning:
                print """
WARNING: Messages from standard multiprocessing.Process objects that don't use
this class's output Queue will not be received.
"""
        self.listening=dict()
        for p in self.processes:
            for type_ in p[0].LISTEN_TO:
                try:
                    self.listening[type_].append(p[2])
                except KeyError:
                    self.listening[type_]=[p[2]]

        self.start()
        while self.__sup_is_alive():
            self.join(interval)
            try:
                while True:
                    m=self.get_message(block=False)
                    try:
                        if not self.__handle_message(
                          m, prntHandler, objHandler
                        ):
                            self.stop()
                            loggerid=None
                    except SupervisorException as e:
                        print "ERROR: Supervisor; Invalid message received; {0}:\n{1}".format(str(m),str(e))
            except Queue.Empty:
                pass
        for p in self.processes:
            if p[0].RESIDENT:
                self.send(ResidentTermMessage(p[0].m_id))
        if finishHandler != None:
            finishHandler()

    def __sup_is_alive(self):
        '''
        Superviser method to see if all processes (except the logger) have
        finished naturally (either through error or just finishing their op
        method).

        This method also releases queues for finsihed processes, so that
        messages can no longer be sent to them.
        '''
        alive=False
        for p in self.processes:
            if p[0].is_alive():
                if p[0].RESIDENT == False:
                    alive=True
            else:
                p=(p[0],None,None)
        return alive

class Process(multiprocessing.Process):
    '''
    Interface for your own classes specially designed for use with ProcessList
    helping you pass messages between processes.

    Derive from this class and implement op() with whatever arguments you
    deem fit.  Then instantiate it, passing in the values for those arguments
    and pass the object to ProcessList.add() or add_list().

    To implement message passing, write messages using self.output.put() and
    get them back in the originating process by using a message handler passed
    to ProcessList.supervise(messageHandler=lambda:pass)
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
            self.queries=[]
            self.ids={}
            super(Process, self).__init__(target=self.wrap_op,args=args,kwargs=kwargs)

    def set_output(self, output):
        '''
        Setter for this process's output Queue.  Mostly for use by
        ProcessList, so it can poll for messages
        '''
        self.output=output

    def set_input(self, inpt):
        '''
        Setter for this process's input Queue.  Only used by ProcessList
        for various supervisor replies.
        '''
        self.input=inpt

    def send(self, target_ids, m_type, *args):
        '''
        Message object sender helper. Arguments:
        target_ids - The recipient ids of the message e.g. self.sup_id for the
                     supervisor, 0 for all ids
        m_type     - the type of the message object to send e.g, EmptyMessage
        other args - further positional arguments are sent as arguments to the
                     message constructor
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
            self.output.put(m)

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
        self.send(self.sup_id, StringMessage,
          " ".join([str(arg) for arg in args])
        )

    def inpt(self, prompt=None):
        '''
        Replacement for the raw_input function.  Triggers
        ProcessList.supervise() to block and wait for input in the parent
        process, and blocks this function call too (although handle_message
        will be invoked for any messages received while blocking).
        '''
        self.output.put(InputMessage(self.sup_id,self.m_id,prompt))
        while True:
            m=self.input.get()
            if isinstance(m,InputResponseMessage):
                return str(m)
            else:
                self.__handle_message(m)

    def get_ids(self, name, block=True, sleep=0.5):
        '''
        Get the list of ids which correspond to the process name supplied.

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

        If an invalid name is given, you will receive back the empty list '[]'
        '''
        if not name in self.ids:
            self.receive_all()
            if not name in self.ids:
                self.send(self.sup_id, GetIdsMessage, self.m_id, name)
                self.queries.append(name)
                if block==False:
                    return []
                else:
                    while not name in self.ids:
                        self.receive(sleep=sleep)

        return self.ids[name]

    def wrap_op(self, *args, **kwargs):
        # Preassigned exception message in case of truly exceptional
        # circumstances (e.g. MemoryError)
        crash=ExceptionMessage(self.sup_id, self.m_id,
          RuntimeError("Unable to process exception; aborting!")
        )
        try:
            self.op(*args, **kwargs)
        except Exception as e:
            # Hack to preserve the original traceback in the exception message
            try:
                (_, _, tb) = sys.exc_info()
                e.args=(e.args[:-1])+(str(e.args[-1])+"\nOriginal traceback:\n"+"".join(traceback.format_tb(tb)),)
                self.output.put(ExceptionMessage(self.sup_id, self.m_id, e))
            except Exception:
                self.output.put(crash)
        self.output.close()
        self.output.join_thread()

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
        while True:
            m=None
            try:
                m=self.input.get(block=False)
                self.__handle_message(m)
                break
            except Queue.Empty:
                if block:
                    time.sleep(sleep)
                else:
                    raise

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
        if isinstance(m, IdsReplyMessage):
            try:
                name=self.queries.pop(0)
                self.ids[name]=m.ids
            except IndexError:
                raise SupervisorException(
                  "{0}: IdsReplyMessage received for no query".format(
                    self.m_id
                  )
                )
        else:
            self.handle_message(m)

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

class ResidentTermMessage(EmptyMessage):
    pass

class Logger(Process):
    RESIDENT=True

    def op(self):
        while True:
            m=self.input.get(block=True)
            if isinstance(m, ResidentTermMessage):
                break
            else:
                self.log(m)

        def show_names(self, processmap):
            pass

        def log(self, m):
            raise NotImplementedError('This log() method is an example that should be overridden')

class DebugLogger(Logger):
    M_NAME="Debug Logger"
    def log(self, m):
        print m

### Test code ############################################################
# TODO: Use multiprocessing.Value (or possibly Array) to share state between test code and parent

import unittest, time

class Test_Messages(unittest.TestCase):
    def test_all(self):
        m = EmptyMessage("target")
        self.assertEqual(str(m),'EmptyMessage to target')
        m = StringMessage("target", "testmessage")
        self.assertEqual(str(m),'testmessage')
        m = FileMessage("target","filename")
        self.assertEqual(m.filename, "filename")
        self.assertEqual(str(m),'FileMessage to target:filename')
        m = QueryMessage("target", "source")
        self.assertEqual(m.source, "source")
        self.assertEqual(str(m),'QueryMessage from source to target')
        m = InputMessage("target","source", "prompt")
        self.assertEqual(m.source, "source")
        self.assertEqual(m.prompt,"prompt")
        self.assertEqual(str(m),'InputMessage from source to target: prompt')
        m = GetIdsMessage("target", "source", "name")
        self.assertEqual(m.source, "source")
        self.assertEqual(m.name,"name")
        self.assertEqual(str(m),'GetIdsMessage from source to target about name')
        m = IdsReplyMessage("target", "response")
        self.assertEqual(m.ids,"response")
        self.assertEqual(str(m),'IdsReplyMessage to target: response')
        e = Exception("testmessage")
        m = ExceptionMessage("target", "source", e)
        self.assertEqual(m.source, "source")
        self.assertEqual(str(m), "testmessage")


class Test_Handshake_init(QueryMessage):
    pass

class Test_Handshake_reply(EmptyMessage):
    pass

class TestProcessList(unittest.TestCase):
    tick=0.2

    class job_one(Process):
        '''
        Simple job demostrating sending StringMessages
        '''
        M_NAME="Job 1"

        def op(self):
            self.receive() # Only expecting one message, so no loop needed

        def handle_message(self,m):
            # Start on first message
            self.send(self.sup_id,StringMessage,'Starting job one') # Helper for sending message objects
            time.sleep(2*TestProcessList.tick)
            self.prnt('Finished job one') # Shortcut for sending objects

    def job_two(self,inpt,output):
        '''
        Non-Process derived demo of non-supervisable messages that can still communicate (provided you generate and provide Queue objects for that purpose)
        '''
        inpt.get(block=True)
        time.sleep(TestProcessList.tick)
        output.put('Starting job two')
        output.close()
        output.join_thread()

    class job_foo(Process):
        M_NAME="Job foo"

        def op(self,num):
            self.num=num
            self.receive()

        def handle_message(self,m):
            time.sleep((self.num*2-5)*TestProcessList.tick) # 3=1 tick,4=3 ticks
            self.prnt('Starting job '+str(self.num)) # Shortcut for sending a StringMessage
            time.sleep((12-self.num*3)*TestProcessList.tick) # 3=1+3 ticks,4=3+0
            self.prnt('Finished job '+str(self.num))

    class job_starter(Process):
        M_NAME="Job starter"

        def op(self):
            time.sleep(TestProcessList.tick)
            self.send(0,StringMessage,"Go go go!")

    # Schedule reference:
    # -1 ticks - job_starter starts
    # 0 ticks - job_starter signals other jobs to start; 'Starting job one'
    # 1 ticks - 'Starting job two'; 'Starting job 3'
    # 2 ticks - 'Finished job one'
    # 3 ticks - 'Starting job 4'; 'Finished job 4'
    # ...
    # 5 ticks - 'Finished job 3'
    def setUp(self):
        self.p=ProcessList()
        # No arguments
        self.j1=self.job_one()
        # Non-multitools.Process (old style)
        self.j2i=multiprocessing.Queue() # Input queue
        self.j2o=multiprocessing.Queue() # Output queue
        self.j2=multiprocessing.Process(target=self.job_two,args=(self.j2i,self.j2o))
        # Named argument
        self.j3=self.job_foo(num=3)
        # Ordered argument
        self.j4=self.job_foo(4)
        # NOTE Not testing warning if M_NAME not set

    def test_init(self):
        self.assertEqual(self.p.processes,[])

    def test_add(self):
        self.assertTrue(isinstance(self.p.add(self.j1), type(multiprocessing.Queue())))
        self.assertTrue(isinstance(self.p.add(self.j2), type(None)))
        self.assertEqual(len(self.p.processes),2)
        self.assertEqual(self.p.processes[0][0], self.j1)
        self.assertTrue(isinstance(self.p.processes[0][1], type(multiprocessing.Queue())))
        self.assertTrue(isinstance(self.p.processes[0][2], type(multiprocessing.Queue())))
        self.assertEqual(self.p.processes[1][0], self.j2)
        self.assertEqual(self.p.processes[1][1], None)
        self.assertEqual(self.p.processes[1][2], None)

    def test_add_list(self):
        l=self.p.add_list([self.j2, self.j1])
        self.assertEqual(len(l),2)
        self.assertTrue(isinstance(l[0], type(None)))
        self.assertTrue(isinstance(l[1], type(multiprocessing.Queue())))
        self.assertEqual(len(self.p.processes),2)
        self.assertEqual(self.p.processes[0][0], self.j2)
        self.assertEqual(self.p.processes[1][0], self.j1)
        self.assertTrue(isinstance(self.p.processes[1][1], type(multiprocessing.Queue())))

    def test_send_object(self):
        self.p.add_list([self.j1, self.j3])
        self.p.start()
        self.p.send_object(0, StringMessage(None, "Ok, go!"))
        self.assertEqual(str(self.p.get_message()),"Starting job one")
        self.assertEqual(str(self.p.get_message(timeout=2)),"Starting job 3")
        self.assertEqual(str(self.p.get_message()),"Finished job one")
        time.sleep(4*TestProcessList.tick)
        self.assertEqual(str(self.p.get_message(block=False)),"Finished job 3")

    def test_start(self):
        self.p.add_list([self.j1, self.j2])
        self.p.start()
        j1=self.p.get_ids('Job 1')[0]
        self.p.send_object(j1, StringMessage(None, "Ok, go!"))
        self.j2i.put("Right, you too!")
        self.assertEqual(str(self.p.get_message()),"Starting job one")
        self.assertEqual(self.j2o.get(),"Starting job two")
        self.assertEqual(str(self.p.get_message()),"Finished job one")
        self.j1.terminate()
        self.j2.terminate()

    def test_join(self):
        self.p.add_list([self.j2, self.j1])
        self.p.start()
        self.p.send_object(0, StringMessage(None, "Ok, go!"))
        self.j2i.put("Right, you too!")
        self.p.join()
        self.assertEqual(str(self.p.get_message()),"Starting job one")
        self.assertEqual(str(self.p.get_message()),"Finished job one")
        self.assertRaises(Queue.Empty, self.p.get_message, block=False)
        self.assertEqual(self.j2o.get(),"Starting job two")

    def test_is_alive(self):
        self.p.add_list([self.j1, self.j2])
        self.p.start()
        self.assertTrue(self.p.is_alive())
        if self.j1.is_alive(): self.j1.terminate()
        if self.j2.is_alive(): self.j2.terminate()
        time.sleep(0.5) # Hack: Needs a little time to terminate stuff
        self.assertFalse(self.p.is_alive())

    def test_terminate(self):
        self.p.add_list([self.j1, self.j2])
        self.p.start()
        self.p.terminate()
        time.sleep(0.5)
        self.assertFalse(self.j1.is_alive())
        self.assertFalse(self.j2.is_alive())

    def test_supervise(self):
        class objJob(Process):
            M_NAME="objJob"

            def op(self):
                self.output.put("Str object")

        self.p.add_list([self.j1,self.j3,self.j4,objJob()])
        self.p.add(self.job_starter())

        class handlers(object):
            '''
            Class to encapsulate the checking of messages.  In your own code
            you can just use lambda functions or locally scoped named
            functions as well, your choice.
            '''
            messages=(
                'Starting job one',
                'Starting job 3',
                'Finished job one',
                'Starting job 4',
                'Finished job 4',
                'Finished job 3'
            )
            objects=("Str object",)
            def __init__(self):
                self.order=0
                self.obj=0
                self.passed=True

            def prntHandler(self,m):
                if self.order >= len(self.messages):
                    self.passed=False
                    print "MESSAGE FAIL: Expected {0} messages, got {1} (extra message was '{2}')".format(len(self.messages),self.order,str(m))
                elif self.messages[self.order] != str(m):
                    self.passed=False
                    print "MESSAGE FAIL: Expected '{0}' got '{1}'".format(self.messages[self.order],str(m))
                self.order+=1

            def finishedHandler(self):
                if self.order!=len(self.messages):
                    self.passed=False
                    print "MESSAGE FAIL: Expected {0} messages, got {1}".format(len(self.messages), self.order)
                if self.obj!=len(self.objects):
                    self.passed=False
                    print "OBJ FAIL: Expected {0} objects, got {1}".format(len(self.objects), self.obj)

            def objHandler(self,m):
                if self.obj > len(self.objects):
                    self.passed=False
                    print "OBJ FAIL: Expected {0} objects, got {1} (extra object str was '{2}')".format(len(self.objects),self.obj,str(m))
                elif m != self.objects[self.obj]:
                    self.passed=False
                    print "OBJ FAIL: Expected object '{0}' got '{1}'".format(self.objects[self.obj])
                self.obj+=1

        handler=handlers()
        prntProxy = lambda m: handler.prntHandler(m)
        finishedProxy = lambda: handler.finishedHandler()
        objProxy = lambda m: handler.objHandler(m)
        self.p.supervise(TestProcessList.tick/4.0,prntProxy,finishedProxy,objProxy,warn=False)
        self.assertTrue(handler.passed)
        # Note: Not testing warner automatically
        # Note transparent exception raising is tested in TestProcess.testOP()

    def test_get_ids(self):
        # TODO Belongs in TestProcess
        class agent(Process):
            M_NAME="Agent"
            def op(opself):
                self.assertEqual(opself.get_ids('Agent', block=True), [opself.m_id,])
                # We've now got the Agent id cached, so we can ask for it again without blocking
                self.assertEqual(opself.get_ids('Agent', block=False), [opself.m_id,])
                # Note in practice, you'd probably do this the other way round
                # if you do it at all - non-blocking first to give the
                # supervisor time to process your request, then blocking when
                # you actually need it.

                # Finally, a negative test
                self.assertEqual(opself.get_ids('Non existent name'), [])

        pl=ProcessList()
        pl.add(agent())
        pl.supervise()

    # IPC tests

    def testGetIdsMessage(self):
        class agent(Process):
            M_NAME="Agent"
            def op(opself):
                opself.send(opself.sup_id, GetIdsMessage, opself.m_id, 'Agent')
                ids = opself.input.get(block=True).ids
                # Safe to assume the next message is a IdsReplyMessage only
                # because we're the only process here.  If anything else it
                # liable to talk to you, the suggested API is to use
                # self.get_ids()
                self.assertEqual(len(ids), 1)
                self.assertEqual(ids[0],opself.m_id)
        pl=ProcessList()
        pl.add(agent())
        pl.supervise()

    def test_listening(self):
        class TestL1(Process):
            M_NAME='Test Listener 1'
            LISTEN_TO=[Test_Handshake_reply]

            def handle_message(self_, m):
                if type(m) == Test_Handshake_reply:
                    self.assertFalse(self_.messaged)
                    self_.messaged=True # Ensure this is only messaged once
                elif type(m) == ResidentTermMessage:
                    # Finish
                    self.assertTrue(self_.messaged)
                    self_.running=False
                else:
                    self.assertTrue(False)

            def op(self):
                self.messaged=False
                self.running=True
                while self.running:
                    self.receive()

        class TestL2(Process):
            M_NAME='Test Listener 2'
            LISTEN_TO=[StringMessage]

            def handle_message(self_, m):
                if isinstance(m, StringMessage):
                    self.assertEqual(m.message,'Test message')
                    self_.messaged=True
                elif isinstance(m, ResidentTermMessage):
                    self.assertTrue(self_.messaged)
                    self_.running=False

            def op(self):
                self.messaged=False
                self.running=True
                while self.running:
                    self.receive()

        class TestS(Process):
            M_NAME='Test Server'

            def op(self):
                self.send(1, Test_Handshake_reply)
                self.send(1, InputResponseMessage, "Test message")
                self.send(1, EmptyMessage) # Should get sent to no one
                self.send(0, ResidentTermMessage)

        pl=ProcessList()
        pl.add(TestL1())
        pl.add(TestL2())
        pl.add(TestS())
        pl.supervise()

    def testIPC(self):
        class agent_one(Process):
            M_NAME="Agent 1"
            def op(self):
                # NOTE: Note not testing non-blocking prequerying
                ids=self.get_ids('Agent 2')
                if len(ids) == 1:
                    self.send(ids[0], Test_Handshake_init, self.m_id)
                else:
                    if len(ids) == 0:
                        self.prnt("ERROR: No id got")
                    else:
                        self.prnt("ERROR: Too many ids got")
                m=self.input.get(block=True)
                if isinstance(m, Test_Handshake_reply):
                    self.prnt("Test OK!")
                else:
                    self.prnt("ERROR: Bad test reply for agent one")

        class agent_two(Process):
            M_NAME="Agent 2"
            def op(self):
                m=self.input.get(block=True)
                if isinstance(m, Test_Handshake_init):
                    # Send a reply back to the source of the handshake
                    self.send(m.source,Test_Handshake_reply)
                else:
                    self.prnt("ERROR: Unexpected message to agent two")

        class logger(Process):
            M_NAME="Logger"
            LISTEN_TO=[EmptyMessage]
            RESIDENT=True
            def op(self):
                self.messagetypes=[Test_Handshake_init, Test_Handshake_reply]
                self.messageindex=0
                while self.messageindex<len(self.messagetypes):
                    self.receive(block=True)

            def handle_message(self_, m):
                self.assertLess(self_.messageindex, len(self_.messagetypes))
                self.assertEqual(type(m),self_.messagetypes[self_.messageindex])
                self_.messageindex=self_.messageindex+1

        message={'val':None}
        def testHandler(m):
            if m.startswith('ERROR:'):
                print m
            else:
                message['val']=m

        pl=ProcessList()
        pl.add(agent_one())
        pl.add(agent_two())
        pl.add(logger())
        #pdb.set_trace()
        pl.supervise(prntHandler=testHandler)
        self.assertEqual(message['val'],"Test OK!")

class TestProcess(unittest.TestCase):
    def testInit(self):
        self.assertRaises(NotImplementedError,Process)

    def testOp(self):
        class testP(Process):
            M_NAME="TestP"
            def op(self):
                self.prnt('Calling testP.op')
                super(testP,self).op() # Uh-oh!

        # Alternative way to store test states outside the test handlers
        messaged={'val':0}

        def testHandler(m):
            if m == 'Calling testP.op':
                messaged['val']+=1
            else:
                print "ERROR: Received via prnt unexpected message:",m

        tp=testP()
        pl=ProcessList()
        pl.add(tp)
        self.assertRaises(NotImplementedError, pl.supervise, prntHandler=testHandler)
        self.assertEqual(messaged['val'],1)

    def testPrnt(self):
        messaged={'val':False}
        def testHandler(m):
            expected='Test prnt'
            if m==expected:
                messaged['val']=True
            self.assertEqual(m, expected)

        class testProcess(Process):
            M_NAME='testProcess'
            def op(self):
                self.prnt('Test prnt')

        tp=testProcess()
        pl=ProcessList()
        pl.add(tp)
        pl.supervise(prntHandler=testHandler)
        self.assertTrue(messaged['val'])

    def testInpt(self):
        # Can't be easily tested automatically since it blocks on user input
        # Thankfully it's a two liner, and should be pretty obvious if it
        # doesn't work.
        pass

if __name__=='__main__':
    unittest.main()
