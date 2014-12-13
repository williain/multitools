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

    def op(result, arg_one, arg_two):
        result.value=arg_one*arg_two

    val=multiprocessing.Value('i',0)
    p=multiprocessing.Process(target=op, args=[val,1234,5678])
    pl=multitools.ProcessList()
    pl.add(p)
    pl.start()
    pl.join()
    print "Result",val.value

In this example, using multitools.ProcessList just adds two lines and achieves
nothing extra.  If you have more that one process to run though, ProcessList
gives you power to call start() and join() once to start() and join() all the
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
    pl.add(multiprocessing.Process(target=op_one, args=[val_one,1234]))
    pl.add(multiprocessing.Process(target=op_two, args=[val_two,5678]))
    pl.start()
    pl.join()
    print "Result one",val_one.value
    print "Result two",val_two.value

To do the same without using multitools.ProcessList, you'd need to run
Process.start() and Process.join() on all of them.  That's all ProcessList
does; it collects a set of multiprocessing.Processes and allows you to run them
together.  It's quite a simple thing, but it's the foundation for the rest of
the multitools libraries.

Introducing ipc.client.Process
------------------------------
::

    import multiprocessing
    import multitools, multitools.ipc.client

    class MyProcess(multitools.ipc.client.Process):
        M_NAME=None

        def op(self, result, arg_one, arg_two):
            result.value=arg_one*arg_two

    pl=multitools.ProcessList()
    val=multiprocessing.Value('i',0)
    pl.add(MyProcess(val,1234,5678))
    pl.start()
    pl.join()
    print "Result",val.value

This example is more like the original class example, but it needs slightly
less boilerplate code to make it work.  multitools.ipc.client.Process inherits
from multiprocessing.Process, so it works in much the same way althogh note
that your method is renamed back to op(), not run() this time.

If you do overload run() you'd need to put the code that takes the args in the
class's __init__, and disable much of the supervisor functionality that
follows - i.e. you might as well use multiprocessing.Process directly.

Note the M_NAME constant defined (as None) there.  That's just there to prevent
a warning output by the Process constructor.  We're slightly abusing its
functionality here; as its name suggests, it's more designed to be used with
the class documented next, where declaring an identifiable name is more
important.  But for now we can just ignore the warning, so we suppress it by
delaring it as any value, such as None.

Introducing ipc.host.Supervisor
-------------------------------
::

    import multiprocessing
    import multitools.ipc.client, multitools.ipc.host

    class MyProcess(multitools.ipc.client.Process):
        M_NAME=None

        def op(self, result, arg_one, arg_two):
            result.value=arg_one*arg_two

    s=multitools.ipc.host.Supervisor()
    val=multiprocessing.Value('i',0)
    s.add(MyProcess(val,1234,5678))
    s.supervise()
    print "Result", val.value

multitools.ipc.host.Supervisor is a type of ProcessList, so it's just like
using one of those.  In this example, using the supervisor just means calling
s.supervise(), rather than s.start() and s.join(), but the supervisor also
maintains connections to the processes which can enable the passing of data
between the process and the supervisor.  The supervisor also detects special
types of objects sent called ipc messages which it will send to their targetted
process, as we'll see soon.

ipc.client.Process.prnt()
-------------------------

If you try to print to screen from your processes, it won't always work because
TODO

The prnt() function of ipc.client.Process is a drop in replacement for the
print operator, when you're using the supervisor::

    import multitools.ipc.client, multitools.ipc.host

    class MyProcess(multitools.ipc.client.Process):
        M_NAME="My process"
        def op(self, arg_one):
            self.prnt("DEBUG:",arg_one)

    s=multitools.ipc.host.Supervisor()
    s.add(MyProcess(1234))
    s.supervise()

This code will print 'DEBUG: 1234' to screen.

Supervisor Handlers
...................

One basic way to extend the supervisor is to use the handlers.  These are
function arguments passed to the supervisor to extend it's functionality.

These arguments are named prntHandler and objHandler for the print handler
and object handler respectively.

The print handler:

You can override the behaviour of the prnt() function by passing a
print handler to the supervisor e.g. ::

    def myPrntHandler(p):
        print "CAUGHT",p

    s.supervisor(prntHandler=myPrntHandler)

Add this to the previous code example (replacing the supervisor() call with
this one), and this now prints 'CAUGHT DEBUG: 1234'.

This mechanism could be used for a simplified form of debug logging, or
progress logging.

The object handler:

The object handler is a function passed to the supervisor using the
objHandler named argument::

    import multitools.ipc as ipc
    from multitools.ipc.client import Process
    from multitools.ipc.host import Supervisor

    class MyProcess(Process):
        M_NAME='My process'
        def op(self, arg_one, arg_two):
            self.send_object(arg_one*arg_two)

    def myObjHandler(m):
        print "DEBUG:",m

    s=Supervisor()
    s.add(MyProcess(1234,5678))
    s.supervise(objHandler=myObjHandler)

The ipc.Process class has a method called send_object which will send any
object you pass back to the supervisor.  Without an object handler, the
supervisor will throw an exception on receiving an unrecognised object.

Note we've now got rid of having to import multiprocessing to use a Value
object, we can just use any serialisable object now (an int in this case).
You can still use multiprocessing.Value if you want a value you can pass
around and modify from anywhere, but it's unnecessary if you just want
to get a value out.

ipc.client.Process.inpt()
-------------------------

Getting user input from within a process can be tricky.  If you're an
interactive process that can be problematic because you can't print out
the prompt (except using .prnt()), and blocking on user input can TODO

The inpt() function saves you all that trouble.  Call it, and it will
sit and wait for user input, then return what they entered to you. In
other words it's a blocking call that returns the user input.

If you want a prompt, you can pass it as an argument::

    class MyProcess(multitools.ipc.client.Process):
        ...
        def op(self,...):
            ...
            name=self.inpt("Enter your name:")
            ...

Sending messages
================

Overusing the handlers can lead to code that embeds much of its logic in
the module that owns the supervisor instance.  You might find a better
design for you code by allowing the overall behaviour to emerge from logic
that is associated with the processes that receive them.

To comminicate from one process to another, you'll need to send a message
object.

Message objects
---------------

multitools.ipc defines a handful of message object types.  Message objects
follow a heirarchy, with all deriving ultimately from
multitools.ipc.EmptyMessage.

EmptyMessage takes only one argument - the target id, that is the id of the
target process that should receive the message::

    message=EmptyMessage("target_id")

In practive, you'll rarely instantiate an empty message, unless you subclass
it to give it a type that you can use as an event notifier.  Other message
types take arguments, such as StringMessage::

    message=StringMessage("target_id","Test Message")

Process ids
-----------

Every process added to a host.Supervisor gets a process id (p_id)::

    from multitools.ipc.client import Process
    from multitools.ipc.host import Supervisor

    class MyProcessOne(Process):
        M_NAME=None

        def op(self):
            pass

    s=Supervisor()
    p=MyProcessOne()
    s.add(p)
    print p.p_id

The p_id is what you need to put as the target id in a message object, and
sending it will cause it to be sent to that process::

    import multitools.ipc as ipc

    class MyProcessTwo(Process):
        M_NAME=None

        def op(self, target, arg):
            self.send_object(ipc.StringMessage(target, arg))

    s.add(MyProcessTwo(p.p_id,"Test message"))
    s.supervise()

client.Process.get()
--------------------

To receive objects you simply need to call self.get() from within a
client.Process.  It will block and return the next object received;
replace MyProcessOne()'s op() method in the previous example with::

    def op(self):
        print "DEBUG:",self.get()

Now, when run it will print out::

    DEBUG: StringMessage to 0xhhhhhhhh_1;"Test message"

...where 0xhhhhhhhh is the 32 bit supervisor id; all processes attached to
the same supervisor will have that part of their id the same, but the number
on the end incremented.

Since get() blocks by default, if you were to not include MyProcessTwo which
sends the message, your process wouldn't terminate, and the whole program
will hang. Your only escape is to abort the process with a SIGINT or Ctrl-C,
which will cause a KeyboardInterrupt and a whole unwinding of all the
running processes, including the the multitools and multiprocessing magic
going on behind the scenes.

That makes debugging wayward code a bit more tricky in multi-processing code,
but the answer is just to page up to your own stacktrace.  You have been
warned!

Other exceptions are handled a bit more serenely when using multitools though.
When one process raises an exception, multitools catches it and pretties up
the output slightly making it easier to distinguish between your code fouling
up and the rest of the smoke and mirrors being unwound.  The other processes
are silently terminated, so control returns to you and you can start debugging
immediately.

If you don't want get() to block indefinitely, you can specify a timeout (even
a timeout of 0 if you don't want it to block at all).  It will raise a
queue.Empty exception if nothing is recieved within the timeout::

    try:
        m==self.get(timeout=0)
        # Message received
        ...
    except Queue.Empty:
        # No messages available
        ...

multitools.ipc.client.Process.get_ids()
---------------------------------------

Finally we get to explain why you need to set an M_NAME identifier.
Process.get_ids() takes a name as a string, asks the supervisor for the
set of processes with that name as their M_NAME, and returns their ids.

This allows you to encapsulate all you need to send a message within
the sending process, so the main code doesn't need to pull the p_id out
of the added process and pass it through::

    from multitools.ipc.client import Process
    from multitools.ipc.host import Supervisor
    import multitools.ipc as ipc

    class MyProcessOne(Process):
        M_NAME="My Process One"

        def op(self):
            m=self.get()
            print "Hi from MyProcessOne:",m.message

    class MyProcessTwo(Process):
        M_NAME="My Process Two"

        def op(self, arg):
            targets=self.get_ids('My Process One')
            self.send_object(ipc.StringMessage(targets.pop(), arg))

    s=Supervisor()
    s.add(MyProcessOne())
    s.add(MyProcessTwo("Test message"))
    s.supervise()

client.Process.send_message()
-----------------------------

Note that get_ids() returns a list of ids, because there may be more than
one process with the same name.  Instead of assuming there's only one id
(as in the example above) or iterating over the list, you can use
self.send_message()::

    self.send_message(
      self.get_ids('target'),ipc.StringMessage,'This is my message'
    )

send_message() takes a set of ids as the first argument, then the type of
the message object to send, then the arguments to the message constructor.
It iterates over the ids for you, creates a message object for each target
then sends them.

Implementing self.handle_message()
----------------------------------

Once messages are going this way and that way, it can be hard to keep track
of what you're going to receive.  What happens if a message is received
while your process is blocking on a get_id() call?  That function, as well
as self.inpt() will call self.handle_message().  You need to implement
that function if there's any chance you might get sent a message while
blocking.  Thankfully, it's not that hard::

    from multitools.ipc.client import Process

    class MyProcess(Process):
        M_NAME="My process"
        def handle_message(self,m):
            self.prnt("Received",m)

        def op(self):
            for i in xrange(1,10):
                self.receive()

This example prints the first ten messages it receives then terminates.

The other benefit of organising your code like this is you can separate your
message handling code and other functionality. As your process grows it often
makes sense to respond to messages and set state in one bit of code, but to
do the actual work in another.  One common implementation of op() is::

    def op(self):
        self.running=True
        while self.running:
            self.receive()
            ...

Thus handle_message() sets self.running to False when it receives a certain
message telling it work is done, and the op() terminates.  You can set any
number of other flags and status values and do work in op() as well as
calling self.receive, or you can do the work in handle_message() if that
makes more sense.

self.receive() takes a timeout argument just like self.get() which will
raise Queue.Empty if no message is received within the timeout.

Advanced functionality
======================

Non-blocking get_ids()
----------------------

The supervisor can be very busy to begin with as all processes are asking for
their first ids, so it may make sense to get your request in early.  If the
supervisor replies, calling self.receive() will recognise that message and
cache the result so that if you later call get_ids() in normal blocking mode
when you want to send a message.

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

Message objects extended
------------------------

multitools.ipc defines a handful of useful message objects, which you're
free to reuse or extend for your own purposes.  All message objects, for the
purposes of the supervisor should be derived from multitools.ipc.EmptyMessage,
define a decent __str__() method for logging purposes, and take a target id as
the first argument to the constructor, for example::

    import multitools.ipc as ipc

    class IntegerMessage(ipc.EmptyMessage):
        def __init__(self, target, int_):
            self.int_=int_
            super(IntegerMessage, self).__init__(target)

        def __str__(self):
            return "{0}; Value {1}".format(
          super(IntegerMessage, self).__str__(), self.int_
        )

If you just want to subclass an existing objects and not change it, say
an ipc.StringMessage fits your template, but you want to be able to
distinguish between a plain StringMessage and one that means something to
you::

    class SpecialStringMessage(ipc.StringMessage):
        pass

Note that the ipc.FileMessage type in multitools.ipc takes a filename as
argument, not a File object.  File objects aren't picklable, so can't be
sent in a message.

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

    self.send_message(self.get_ids('My Process'), EmptyMessage)

To broadcast it to all available processes just do::

    self.send_message(multitools.ipc.host.Supervisor.BROADCAST, EmptyMessage)

Listeners is also a meta-process id.  It identifies message sent to only the
processes that have declared they'd like to listen to that sort of message
type.  First we'd better explain how to make a listener class::

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

    class MyLogger(multitools.ipc.logger.Logger):
        M_NAME='My logger'
        LISTEN_TO=[MyMessages]
        def log(self,m):
            self.prnt(m)

To Conclude
===========

That concludes the tour of the multitools api.  It's now up to you to decide
whether it's worth using for your own project - it's aim is to make your code
simpler and more maintainable, but it does that by hiding some of the operation
of multiprocessing and its associated libraries.

Its inspiration was a project that hangs off a slow IO-bound process, so I'm
not sure how quickly it can be made to work (you can try setting the interval
argument to Supervisor.supervise() to something less than the default 0.1s),
but you'll need better hardware than I'm currently running to test that out
though.
