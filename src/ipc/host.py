#!/usr/bin/env python
from __future__ import print_function
import multiprocessing, time
try:
    import queue
except ImportError:
    import Queue as queue
import multitools

# Constants for non-specific target ids
BROADCAST=0 #: Send to all processes
LISTENERS=1 #: Send to none except those listeneing for this message type

class SupervisorException(Exception):
    pass

class Supervisor(multitools.ProcessList):
    '''
    Functions as a ProcessList as well as a supervisor to automate
    passing messages between processes
    '''

    def __init__(self):
        self.p_id=hex(id(self))
        self.init_supervisor()

    def init_supervisor(self):
        self.connections=[]
        self.listening=dict()
        super(Supervisor, self).__init__()

    def add(self, process):
        '''
        Process subclasses which has the set_pipe() function will have their
        pipe configured for use by the supervisor
        '''
        process.p_id="{0}_{1}".format(self.p_id, str(len(self.processes)+1))
        process.sup_id=self.p_id
        super(Supervisor, self).add(process)

        conn=None
        if hasattr(process, 'set_pipe'):
            (local_,remote)=multiprocessing.Pipe()
            process.set_pipe(remote)
            conn=local_
            if hasattr(process, 'LISTEN_TYPE'):
                for type_ in process.LISTEN_TYPE:
                    try:
                        self.listening[type_].add(conn)
                    except KeyError:
                        self.listening[type_]=set([conn])
        elif hasattr(process, 'LISTEN_TYPE'):
            if len(process.LISTEN_TYPE) > 0:
                raise RuntimeError('Process defines LISTEN_TYPE, but not '+
                  'set_pipe(); can\'t send listened to messages without '+
                  'a pipe')
        self.connections.append(conn)

    def poll_message(self):
        '''
        Check if any messages have sent output.
        If they have, return the connection, else return False
        '''
        for c in self.connections:
            if c:
                if c.poll():
                    return c
        return False

    def get_message(self, block=True, timeout=None, tick=None):
        '''
        Scan the processes for output.
        Options:
            block   - Block until output is given.  If False, raises
                      queue.Empty if no processes have raised output, and
                      disregards timeout.
            timeout - If block is True, wait per timeout, and raise
                      queue.Empty only if all processes provided no output
                      during this time.
            tick -    If blocking with a timeout, how long to wait between
                      checks.  Defaults to 1/10th of the timeout.
        Raises:
            queue.Empty - If non-blocking or timeout was exceeded and no
                          messages were received.
        Returns:
            The message sent (normally expected to be a Message object)
        '''
        if block and timeout:
            if tick==None:
                tick=timeout/10.0
            time_s=time.time()
            while time.time()<time_s+timeout:
                c=self.poll_message()
                if c:
                    return c.recv()
                else:
                    time.sleep(tick)
            raise queue.Empty("No processes sent a message")
        elif block:
            while True:
                c=self.poll_message()
                if c:
                    return c.recv()
        else:
            # Block is false
            c=self.poll_message()
            if c:
                return c.recv()
            raise queue.Empty("No processes sent a message")

    def __get_conn(self, target):
        '''
        Get the one input queue from the process which matches the
        specified id, or get all input queues if target==BROADCAST (or none
        if target==LISTENERS, as that's a message only to listeners)
        Raises:
            ValueError - If the requested id was not found
        '''
        if target==LISTENERS:
            return set()
        elif target==BROADCAST:
            return {c for c in self.connections if c}
        else:
            c = { self.connections[n] for n in range(len(self.processes))
              if self.processes[n].p_id==target
            }
            if len(c)==0:
                raise ValueError(
                  "No process found with id '{0}'".format(target)
                )
            c={conn for conn in c if conn}
            if len(c)==0:
                raise ValueError(
                  "All processes with id '{0}' have terminated, or were not valid".format(target)
                )
            return c

    def __get_listeners(self, m_type):
        '''
        Return the list of input queues for the processes which listen
        to the specified message type
        '''
        if m_type == multitools.ipc.IdsReplyMessage:
            # Don't send IdsReplyMessage to listeners that didn't ask for it
            return set()
        try:
            parent_listeners=self.__get_listeners(m_type.mro()[1])
        except IndexError:
            parent_listeners=set()
        try:
            this_listeners=self.listening[m_type]
        except KeyError:
            this_listeners=set()
        return parent_listeners | this_listeners

    def send_object(self, target_id, message):
        '''
        Send a Message object to the targetted process, for processes that
        are managed by this supervisor
        Raises:
            SupervisorException - If the target_id doesn't match any of the
                                  running processes
        '''
        try:
            conns = self.__get_conn(target_id) | self.__get_listeners(
              type(message)
            )
            for c in conns:
                if c:
                    c.send(message)
        except ValueError as e:
            raise SupervisorException(str(e))

    def send(self, message):
        '''
        Helper function for sending message objects
        '''
        self.send_object(message.target, message)

    def get_ids(self, name):
        '''
        Get the ids for the processes where M_NAME matches the supplied name

        Returns the empty set if no processes match the name
        '''
        ids=set()
        for p in self.processes:
            if hasattr(p,'M_NAME') and p.M_NAME == name:
                ids.add(p.p_id)
        return ids

    def handle_message(self, m, prntHandler, objHandler):
        '''
        Handle a message received by the supervisor.

        Raises:
            SupervisorException - If an invalid message is received
        '''
        if isinstance(m, multitools.ipc.EmptyMessage):
            if m.target==self.p_id:
                if isinstance(m, multitools.ipc.ExceptionMessage):
                    self.terminate()
                    m.rais()
                elif isinstance(m, multitools.ipc.QueryMessage):
                    if isinstance(m, multitools.ipc.InputMessage):
                        if m.prompt: print(m.prompt)
                        s = raw_input() # Blocks til user hits enter
                        self.send(multitools.ipc.InputResponseMessage(
                          m.source, s)
                        )
                    elif isinstance(m, multitools.ipc.GetIdsMessage):
                        ids = self.get_ids(m.name)
                        # ids may be the empty set if no matches
                        self.send(multitools.ipc.IdsReplyMessage(
                          m.source, ids)
                        )
                    else:
                        raise SupervisorException("Unknown query message type {0}".format(type(m)))
                elif isinstance(m, multitools.ipc.PrntMessage):
                    if prntHandler:
                        prntHandler(str(m))
                    else:
                        print(m)
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
        return True

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
                        PrntMessage is received from one of the subprocesses
                        (via Process.prnt) instead of allowing it to be printed
                        to screen
        objHandler    - Optional callable to be called when a non-message
                        object gets sent, so you can use this framework for
                        your own message types (not derived from EmptyMessage)
                        if you want.
        warn - By default, the method will warn you if your processes don't
               derive from client.Process, thus messages from it can't be
               received.  Set this to False to use it with standard
               multiprocessing.Process objects, bearing in mind your
               msgHandler won't be called for messages from those objects.

        Raises:
        SupervisorException - raised in case of an invalid message or if no
                              objHandler is supplied, anything other than an
                              ExceptionMessage (from raise), QueryMessage
                              (either a GetIdsMessage or from Process.inpt) or
                              a PrntMessage (from Process.prnt) is received
        '''
        if warn:
            warning=False
            for p in self.processes:
                if not hasattr(p, 'set_pipe'):
                    warning=True
            if warning:
                print("""
WARNING: Messages from standard multiprocessing.Process objects that don't acccept and use the pipe object via set_pipe() not be received.
""")
        self.start()
        while self.is_alive():
            self.join(interval)
            try:
                while True: # While there are messages to be got
                    m=self.get_message(block=False)
                    try:
                        if not self.handle_message(
                          m, prntHandler, objHandler
                        ):
                            self.terminate()
                    except SupervisorException as e:
                        print("ERROR: Supervisor; Invalid message received;\n"+
                          "{0}:\n{1}".format( str(m),str(e) )
                        )
            except queue.Empty:
                pass
        for p in self.processes:
            if hasattr(p, 'RESIDENT') and p.RESIDENT:
                self.send(multitools.ipc.ResidentTermMessage(p.p_id))
        if finishHandler != None:
            finishHandler()

    def is_alive(self):
        '''
        Method to see if all processes (except the resident ones) have
        finished naturally (either through error or just finishing their
        op() method).

        This method also releases queues for finsihed processes, so that
        messages can no longer be sent to them.
        '''
        alive=False
        for n in range(len(self.processes)):
            if self.connections[n]:
                if (not hasattr(self.processes[n], 'RESIDENT') or
                  self.processes[n].RESIDENT == False):
                    if (self.processes[n].is_alive() or
                      self.connections[n].poll()):
                        alive=True
                    else:
                        self.connections[n]=None
        return alive

### Test code ############################################################

import unittest, multitools.ipc.client

class Test_Handshake_init(multitools.ipc.QueryMessage):
    pass

class Test_Handshake_reply(multitools.ipc.EmptyMessage):
    pass

class TestSupervisor(unittest.TestCase):
    tick=0.2

    #TODO Test handle_message returning false
    class job_one(multitools.ipc.client.Resident):
        '''
        Simple job demostrating sending StringMessages
        '''
        M_NAME="Job 1"

        def handle_message(self,m):
            # Start on first message
            self.send_message(self.sup_id,multitools.ipc.PrntMessage,'Starting job one') # Helper for sending message objects
            time.sleep(2*TestSupervisor.tick)
            self.prnt('Finished job one') # Shortcut for sending PrntMessage objects
            return False

    def job_two(self,inpt,output):
        '''
        Non-Process derived demo of non-supervisable messages that can still communicate (provided you generate and provide Queue objects for that purpose)
        '''
        inpt.get(block=True)
        time.sleep(TestSupervisor.tick)
        output.put('Starting job two')
        output.close()
        output.join_thread()

    class job_foo(multitools.ipc.client.Resident):
        M_NAME="Job foo"
        listening=True

        def setup(self,num):
            self.num=num

        def handle_message(self,m):
            time.sleep((self.num*2-5)*TestSupervisor.tick) # 3=1 tick,4=3 ticks
            self.prnt('Starting job '+str(self.num))
            time.sleep((12-self.num*3)*TestSupervisor.tick) # 3=1+3 ticks,4=3+0
            self.prnt('Finished job '+str(self.num))
            return False

    class job_starter(multitools.ipc.client.Process):
        M_NAME="Job starter"

        def op(self):
            time.sleep(TestSupervisor.tick)
            self.send_message(BROADCAST, multitools.ipc.StringMessage, "Go go go!")
            time.sleep(TestSupervisor.tick*5)

        def handle_message(self, m):
            # The broadcast message will get sent here to; just ignore it
            pass

    # Schedule reference:
    # -1 ticks - job_starter starts
    # 0 ticks - job_starter signals other jobs to start; 'Starting job one'
    # 1 ticks - 'Starting job two'; 'Starting job 3'
    # 2 ticks - 'Finished job one'
    # 3 ticks - 'Starting job 4'; 'Finished job 4'
    # ...
    # 5 ticks - 'Finished job 3'
    def setUp(self):
        self.p=Supervisor()
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
        self.assertEqual(self.p.connections,[])

    def test_add(self):
        self.p.add(self.j1)
        self.p.add(self.j2)
        self.assertEqual(self.p.processes[0], self.j1)
        self.assertTrue(hasattr(self.p.connections[0], "poll"))
        self.assertEqual(self.p.processes[1], self.j2)
        self.assertEqual(self.p.connections[1], None)

    def test_add_list(self):
        self.p.add_list([self.j2, self.j1])
        self.assertEqual(len(self.p.processes),2)
        self.assertEqual(self.p.processes[0], self.j2)
        self.assertEqual(self.p.processes[1], self.j1)
        self.assertEqual(self.p.connections[0], None)
        self.assertTrue(hasattr(self.p.connections[1], "poll"))

    def test_send_object(self):
        self.p.add_list([self.j1, self.j3])
        self.p.start()
        self.p.send_object(BROADCAST, multitools.ipc.StringMessage(None, "Ok, go!"))
        self.assertEqual(str(self.p.get_message()),"Starting job one")
        self.assertEqual(str(self.p.get_message(timeout=2,tick=self.tick/2)),"Starting job 3")
        self.assertEqual(str(self.p.get_message()),"Finished job one")
        time.sleep(4*TestSupervisor.tick)
        self.assertEqual(str(self.p.get_message(block=False)),"Finished job 3")

    def test_start(self):
        self.p.add_list([self.j1, self.j2])
        self.p.start()
        j1=self.p.get_ids('Job 1').pop()
        self.p.send_object(j1, multitools.ipc.StringMessage(None, "Ok, go!"))
        self.j2i.put("Right, you too!")
        self.assertEqual(str(self.p.get_message()),"Starting job one")
        self.assertEqual(self.j2o.get(),"Starting job two")
        self.assertEqual(str(self.p.get_message()),"Finished job one")
        self.j1.terminate()
        self.j2.terminate()

    def test_join(self):
        self.p.add_list([self.j2, self.j1])
        self.p.start()
        self.p.send_object(BROADCAST, multitools.ipc.StringMessage(None, "Ok, go!"))
        self.j2i.put("Right, you too!")
        self.p.join()
        self.assertEqual(str(self.p.get_message()),"Starting job one")
        self.assertEqual(str(self.p.get_message()),"Finished job one")
        self.assertRaises(queue.Empty, self.p.get_message, block=False)
        self.assertEqual(self.j2o.get(),"Starting job two")

    def test_is_alive(self):
        class alive_p(multitools.ipc.client.Process):
            M_NAME='Alive process'
            def op(self):
                while True:
                    time.sleep(10)

        ap=alive_p()
        # self.j1 is a resident process
        # self.j2 is a process-wrapped non-communicative function
        # ap is a non-resident process
        self.p.add_list([self.j1, self.j2, ap])
        self.p.start()
        self.assertTrue(self.p.is_alive())
        ap.terminate()
        time.sleep(0.1) # Hack: Needs a little time to terminate stuff
        self.assertFalse(self.p.is_alive())
        if self.j1.is_alive(): self.j1.terminate()
        if self.j2.is_alive(): self.j2.terminate()

    def test_terminate(self):
        self.p.add_list([self.j1, self.j2])
        self.p.start()
        self.p.terminate()
        time.sleep(0.1)
        self.assertFalse(self.j1.is_alive())
        self.assertFalse(self.j2.is_alive())

    def test_supervise(self):
        class objJob(multitools.ipc.client.Process):
            M_NAME="objJob"

            def op(self):
                self.send_object("Str object")

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
                    print("MESSAGE FAIL: Expected {0} messages, got {1} (extra message was '{2}')".format(len(self.messages),self.order,str(m)))
                elif self.messages[self.order] != str(m):
                    self.passed=False
                    print("MESSAGE FAIL: Expected '{0}' got '{1}'".format(self.messages[self.order],str(m)))
                self.order+=1

            def finishedHandler(self):
                if self.order!=len(self.messages):
                    self.passed=False
                    print("MESSAGE FAIL: Expected {0} messages, got {1}".format(len(self.messages), self.order))
                if self.obj!=len(self.objects):
                    self.passed=False
                    print("OBJ FAIL: Expected {0} objects, got {1}".format(len(self.objects), self.obj))

            def objHandler(self,m):
                if self.obj > len(self.objects):
                    self.passed=False
                    print("OBJ FAIL: Expected {0} objects, got {1} (extra object str was '{2}')".format(len(self.objects),self.obj,str(m)))
                elif m != self.objects[self.obj]:
                    self.passed=False
                    print("OBJ FAIL: Expected object '{0}' got '{1}'".format(self.objects[self.obj]))
                self.obj+=1

        #TODO: Put some trace statements in to work out what's happening and what isnae
        handler=handlers()
        prntProxy = lambda m: handler.prntHandler(m)
        finishedProxy = lambda: handler.finishedHandler()
        objProxy = lambda m: handler.objHandler(m)
        self.p.supervise(TestSupervisor.tick/4.0,prntProxy,finishedProxy,objProxy,warn=False)
        self.assertTrue(handler.passed)
        # Note: Not testing warner automatically
        # Note: Not testing SupervisorException
        # Note transparent exception raising is tested in TestProcess.testOP()

    def test_get_ids(self):
        class agent(multitools.ipc.client.Process):
            M_NAME="Agent"
            def op(opself):
                # Ask for id, but don't block; it's not cached so we'll get
                # none, but it'll trigger the id to be cached in the background
                self.assertEqual(len(opself.get_ids('Agent', block=False)), 0)
                # Ask again, but blocking until we get the right id now.
                self.assertEqual(opself.get_ids('Agent'), set((opself.p_id,)))
                # We've now got the Agent id cached, so we can ask for it again without blocking
                self.assertEqual(opself.get_ids('Agent', block=False), set((opself.p_id,)))
                # Finally, a negative test
                self.assertEqual(opself.get_ids('Non existent name'), set())

        self.p.add(agent())
        self.p.supervise()

    # IPC tests

    def testGetIdsMessage(self):
        class agent(multitools.ipc.client.Process):
            M_NAME="Agent"
            def op(opself):
                opself.send_message(opself.sup_id, multitools.ipc.GetIdsMessage, opself.p_id, 'Agent')
                ids = opself.pipe.recv().ids
                # Safe to assume the next message is a IdsReplyMessage only
                # because we're the only process here.  If anything else it
                # liable to talk to you, the suggested API is to use
                # self.get_ids()
                self.assertEqual(len(ids), 1)
                self.assertEqual(ids.pop(),opself.p_id)
        self.p.add(agent())
        self.p.supervise()

    def testIPC(self):
        class agent_one(multitools.ipc.client.Process):
            M_NAME="Agent 1"
            def op(self):
                # NOTE: Note not testing non-blocking prequerying
                ids=self.get_ids('Agent 2')
                if len(ids) == 1:
                    self.send_message(ids.pop(), Test_Handshake_init, self.p_id)
                else:
                    if len(ids) == 0:
                        self.prnt("ERROR: No id got")
                    else:
                        self.prnt("ERROR: Too many ids got")
                m=self.pipe.recv()
                if isinstance(m, Test_Handshake_reply):
                    self.prnt("Test OK!")
                else:
                    self.prnt("ERROR: Bad test reply for agent one")

        class agent_two(multitools.ipc.client.Process):
            M_NAME="Agent 2"
            def op(self):
                m=self.pipe.recv()
                if isinstance(m, Test_Handshake_init):
                    # Send a reply back to the source of the handshake
                    self.send_message(m.source,Test_Handshake_reply)
                else:
                    self.prnt("ERROR: Unexpected message to agent two")

        class logger(multitools.ipc.client.Process):
            M_NAME="Logger"
            LISTEN_TO=[multitools.ipc.EmptyMessage]
            RESIDENT=True
            def setup(self):
                self.messagetypes=[Test_Handshake_init, Test_Handshake_reply]
                self.messageindex=0

            def handle_message(self_, m):
                if isinstance(m, multitools.ipc.ResidentTermMessage):
                    self.assertEqual(self_.messageindex, len(self_.messagetypes))
                    return False
                else:
                    self.assertLess(self_.messageindex, len(self_.messagetypes))
                    self.assertEqual(type(m),self_.messagetypes[self_.messageindex])
                    self_.messageindex=self_.messageindex+1

        def testHandler(m):
            if m.startswith('ERROR:'):
                print(m)
            else:
                self.assertEqual(m, "Test OK!")

        self.p.add(agent_one())
        self.p.add(agent_two())
        self.p.add(logger())
        self.p.supervise(prntHandler=testHandler)
        #TODO: Add a simple Process and check it doesn't try to broadcast to it

if __name__=='__main__':
    unittest.main()
