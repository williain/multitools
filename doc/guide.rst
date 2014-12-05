================
Multitools guide
================

Introduction
============

Python has a fairly comprehensive set of multiprocessing libraries to help
you run multiple processes in parallel and collect the results.  Multitools
is based on those libraries, and aims to make your life easier especially
if you need the processes to work together - it provides an event model based
on passing messages between them.

A quick recap
=============
You don't need this library if you're happy with the standard multiprocessing
library, so it's worth going back to looking how to use that.

Using functions
---------------
::

    import multiprocessing

    def op(result, arg_one, arg_two):
        result.value=arg_one*arg_two

    val=multiprocessing.Value('i',0)
    p=multiprocessing.Process(target=op, args=[val,1234,5678])
    p.start()
    p.join()
    print "Result",val.value

The above is a simple example of how you can run code in a separate process,
using dummy code that wouldn't actually be any quicker to run in parallel.

Using classes
-------------
::

    import multiprocessing

    class MyProcess(multiprocessing.Process):
        def __init__(self, result, arg_one, arg_two):
            self.result=result
            self.arg_one=arg_one
            self.arg_two=arg_two
            super(MyProcess, self).__init__()

        def run(self):
            self.result.value=self.arg_one*self.arg_two

    val=multiprocessing.Value('i',0)
    p=MyProcess(val,1234,5678)
    p.start()
    p.join()
    print "Result",val.value

This is the same as the previous example, but done by subclassing your own
process class.  The code to run the process is simpler, but there's more
boilerplate involved.  YMMV.

Using multitools
================

ProcessList
-----------

To implement the same example a third time, but this time using multitools.ProcessList, do::

    import multiprocessing
    import multitools
    
    def op(self, result, arg_one, arg_two):
        result.value=arg_one*arg_two

    val=multiprocessing.Value('i',0)
    p=multiprocessing.Process(target=op, args=[val,1234,5678])
    pl=multitools.ProcessList
    pl.add(p)
    pl.start()
    pl.join()

In this example, using multitools.ProcessList just adds two lines and achieves
nothing.  If you have more that one process to run though, ProcessList gives
you power to call start() and join() once to start() and join() all the
processes you've add()ed.  For example::

    import multiprocessing
    import multitools

    def op_one(result,arg_one):
        result.value=arg_one*arg_one

    def op_two(result, arg_two):
        result.value=arg_two*arg_two

    pl=multitools.ProcessList()
    val_one=multiprocessing.Value('i',0)
    val_two=multiprocessing.Value('i',0)
    pl.add(multiprocessing.Process(target=op_one, args=[val_one,1234])
    pl.add(multiprocessing.Process(target=op_two, args=[val_two,678])
    pl.start()
    pl.join()

To do the same without using multitools.ProcessList, you'd need to run
Process.start() and Process.join() on all of them.  That's all ProcessList
does; it collects a set of multiprocessing.Processes and allows you to run them
together.  It's quite a simple thing, but it's the foundation for the rest of
the multitools libraries.

Introducing ipc.client.Process
------------------------------
::

    import multitools, multitools.ipc.client

    class MyProcess(multitools.ipc.client.Process):
        def op(self, result, arg_one, arg_two):
            result.value=arg_one*arg_two

    pl=multitools.ProcessList()
    val=multiprocessing.Value('i',0)
    pl.add(MyProcess(val,1234,5678))
    pl.start()
    pl.join()

This example is more like the original class example, but it needs less
boilerplate code to make it work.  multitools.ipc.client.Process inherits
from multiprocessing.Process, so it works in much the same way althogh note
that your method is renamed back to op(), not run() this time.  If you do
overload run() you'd need to put the code that takes the args in the class's
_init__, and disable much of the supervisor functionality that follows - i.e.
you might as well use multiprocessing.Process directly.

Introducing ipc.host.Supervisor
-------------------------------
::

    import multitools.ipc.client, multitools.ipc.host

    class MyProcess(multitools.ipc.client.Process):
        M_NAME='My process'
        def op(self, result, arg_one, arg_two):
            result.value=arg_one*arg_two

    s=multitools.ipc.host.Supervisor()
    val=multiprocessing.Value('i',0)
    s.add(MyProcess(val,1234,5678))
    s.supervise()

multitools.ipc.host.Supervisor is a type of ProcessList, so it's just like
using one of those.  However, the supervisor sets up and maintains conections
to your ipc.client.Processes, so it enables you to talk to your running
processes (use Supervisor.supervise(), not .start() and .join()); note the
definition of M_NAME - that's so other processes can find your process, and
we'll cover that in a later section.

ipc.client.Process.prnt()
-------------------------

If you try to print to screen from your processes, it won't always work because
TODO

The prnt() function of ipc.client.Process is a drop in replacement for the
print operator::

    import multitools.ipc.client, multitools.ipc.host

    class MyProcess(multitools.ipc.client.Process):
        def op(self, arg_one):
            self.prnt("DEBUG:",arg_one)

    s=multitools.ipc.host.Supervisor()
    s.add(MyProcess(1234))
    s.supervise()

The default behaviour is to print 'DEBUG: 1234' to screen.  You can override
the behaviour of the prnt() function by passing a prnt-handler to the
supervisor e.g. ::

    def myPrntHandler(p):
        print "CAUGHT",p

    s.supervisor(prntHandler=myPrntHandler)

This now prints 'CAUGHT DEBUG: 1234' if you replace the last line of the
previous exampe with these lines.

This mechanism could be used for a simplified form of debug logging, or
progress logging, although there are better ways of doing either of those
which we'll cover next:

ipc.client.Process.send()
-------------------------
::

    import multiprocessing.ipc as ipc
    import multiprocessing.ipc.client.Process as Process
    import multiprocessing.ipc.host.Supervisor as Supervisor

    class MyResultsMessage(ipc.StringMessage):
        pass

    class MyProcess(Process):
        M_NAME='My process'
        def op(self, arg_one, arg_two):
            self.send(self.sup_id,MyResultsMessage,'DEBUG:'+str(arg_one*arg_two))

    def myObjHandler(m):
        print m

    s=Supervisor()
    s.add(MyProcess(1234,5678)
    s.supervise(objHandler=myObjHandler)

multitools.ipc.client.Process.send() takes a target id, an object message type
and the arguments for that message.

Note introduced in this example is the concept of an obj-handler.  This is
another way to extend the functionality of the supervisor, making it able to
handle user-defined types.

multitools.ipc.client.Process.get_ids()
---------------------------------------

So far the only target id we've seen is self.sup_id which is the supervisor
id, set in your process by the supervisor.  Adding get_ids it's possible to
implement full interprocess communication::

    import multitools.ipc as ipc
    import multitools.client.Process as Process
    import multitools.host.Supervisor as Supervisor

    class Agent_One(Process):
        M_NAME='Agent one'
        def op(self):
            print self.get_message()

    class Agent_Two(Process):
        M_NAME='Agent two'
        def op(self):
            self.send(self.get_ids('Agent one'),ipc.StringMessage,'Agent two signing in')

    s=Supervisor()
    s.add(Agent_One(),Agent_Two())
    s.supervise()

In this example, we use no handlers to extend the supervisor.  This is the
main model around which multitools was designed, allowing you to
encapsulate message handling functionality within the process, enabling quite
sophisticated behaviour to be encapsulated without the handlers needing to know
the specifics of how everything operates.

Agent_Two calls self.get_ids() with the string argument 'Agent one'.  The
function returns all matching processes, allowing you to switch out multiple
processes all called 'agent one' to alter functionalty, or even run more than
one 'agent one' at the same time.  self.send() takes this list and sends
a copy of the message to all recipients named 'agent one'.

At the same time, the receiver calls self.get().  This blocks by default, so
if you were to not include agent_two which sends the message, your process
wouldn't terminate, and the whole program will hang. Your only escape is
to abort the process with a SIGINT or Ctrl-C, which will cause a
KeyboardInterrupt and a whole unwinding of all the running processes,
including the the multitools and multiprocessing magic going on behind the
scenes.

That makes debugging wayward code a bit more tricky in multi-processing code,
but the answer is just to page up to your own stacktrace.  You have been
warned!

Other exceptions are handled a bit more serenely when using multitools though.
When one process emits an exception, multitools catches it and pretties up
the output slightly making it easier to distinguish between your code fouling
up and the rest of the smoke and mirrors being unwound.  The other processes
are silently terminated, so control returns to you and you can start debugging
immediately.

Note you can specify a timeout to get_message() which will raise a Queue.Empty
exception if no input is received in the timeout, so if you're expecting a
message you could use that to ensure the process doesn't hang, and politely
raises an exception to stop, but you need to come up with a sensible value
for timeout.

Implementing self.handle_message()
----------------------------------

We're nearly done covering how to use the functionality of the supervisor, but
there's one more thing to mention; a way to structure your process code so
that you can get the most out of it::

    import multitools.ipc.client.Process as Process

    class MyProcess(Process):
        M_NAME="My process"
        def handle_message(self,m):
            self.prnt("Received",m)

        def op(self):
            for i in xrange(1,10):
                self.receive()

Thus you can separate your message handling code and other functionality.
This example prints the first ten messages it receives then terminates.
One common implementation of op() is::

    def op(self):
        self.running=True
        while self.running:
            self.receive()

Thus handle_message() sets self.running to False when it receives a certain
message telling it work is done, and the op() terminates.  You can set any
number of other flags and status values and do work in op() as well as
calling self.receive, or you can do the work in handle_message() if that
makes more sense.

self.receive() takes a timeout argument just like self.get_message() which
will raise Queue.Empty if no message is received within the timeout.

The benefit to organising your code like this is that self.receive() does
more than just get the next message and pass it to self.handle_message().
It enables more behind-the-scenes work like calling a non-blocking
get_id().  This sends a request to the supervisor for the ids that correspond
to the specified name, but otherwise returns immediately.

The supervisor can be very busy to begin with as all processes are asking for
ids, so it may make sense to get your request in early.  If the supervisor
replies, calling self.receive() will recognise that message and cache the
result so that if you later call get_ids() in normal blocking mode when you
want to send a message.

If receive has got the ids when you call blocking get_ids() it will return
the result immediately, else it will wait until the message comes through
giving it the ids to use.  That looks like this::

    def handle_message(self,m):
        if isinstance(m, ipc.StringMessage):
            # Use the cached ids, if available
            self.send(self.get_ids("Process two"), ipc.StringMessage, str(m))
        elif isinstance(m, QuitMessage):
            self.running=False

    def op(self):
        self.get_ids("Process two",timeout=0) # Ask supervisor for ids
        self.running=True
        while self.running:
            self.receive()

RESIDENT Processes
------------------

One common model is for a process to be simply reactive to incoming messages,
but not have anything to do without something else happening that it needs to
react to.  We term this model a resident process, because it needs to be active while other processes are around, but once they're gone, it's no longer needed.

To make one, just set RESIDENT in the object or class to True::

    class MyProcess(Process):
        M_NAME="My process"
        RESIDENT=True

        def handle_message(self,m):
            if isinstance(m, ipc.ResidentTermMessage):
                self.running=False
            elif isinstance(m, ...
                ...

        def op(self):
            self.running=True
            while self.running:
                self.receive()

ipc.ResidentTermMessage is a message sent to all processes marked as RESIDENT
when all non-resident processes have finished.

BROADCAST and LISTENERS
-----------------------

Broadcast messages are those sent to all processes, or at least all processes
implementing the client.Process interface that means the supervisor knows how
to communicate with them.  It's just a process id like any other, and easy to
use.

Wheras, to send an EmtpyMessage to a process named 'My Process'::

    self.send(self.get_ids('My Process'), EmptyMessage)

To broadcast it to all available processes just do::

    self.send(multitools.ipc.host.Supervisor.BROADCAST, EmptyMessage)

Listeners is also a meta-process id.  It's a message sent to only the processes
that have declared they'd like to listen to that sort of message type.  First
we'd better explain how to make a listener class::

    class MyProcess(multitools.ipc.client.Process):
        M_NAME='My Process'
        LISTEN_TO=[StringMessage]
        ...

Now the process will receive all messages of type StringProcess (or a subtype
of that, such as multitools.ipc.InptResponseMessage).  Note that's a message
sent to LISTENERS, or to any other process, so it can snoop on communucation
between other processes.  That's one way to set up a logger, as we'll see
later, but it's also a way to design your code if you send messages to
LISTENERS to say 'I don't care who receives this - just send it to those who
are interested'.  Note you will get an exception if it ends up being sent to
nobody, because nobody's listened to that type, so if you just don't care
that nobody's going to receive it, you'll need to catch and handle that
exception.

Loggers
-------

Loggers are just resident processes that listen to messages and perform some
action on them (defined as 'logging' them) but nothing else.  It's designed
as a process that reports on activity, records it to file or screen, or
updates a percantage progress indicator, that type of thing.  The class
defines op and handle_message for you, so you only need to declare your
method to handle messages::

    class MyLogger(ipc.logger.Logger):
        M_NAME='My logger'
        LISTEN_TO=[MyMessages]
        def log(self,m):
            self.prnt(m)

To Conclude
===========

That concludes a whisle-stop tour of the multitools api.  It's now up to you
to decide whether it's worth using for your own project - it's aim is to make
your code simpler and more maintainable, but it does that by hiding some of the
operation of multiprocessing and its associated libraries.

Its inspiration was a project that hangs off a slow IO-bound process, so we're
not sure how quickly it can be made to work - you'll need better hardware than
we're currently running to test that out though.
