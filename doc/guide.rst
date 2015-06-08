================
Multitools guide
================

Introduction
============

One of the limitations of Python as it currently stands is that it uses a
global interpreter lock to ensure it only does one thing at a time (its
operations are atomic).  However, this means on newer multi-core machines,
a python instance will only run on one core.  If you want to use all your
cores, you'll need to run multiple instances of python in parallel.

Python has a fairly comprehensive set of multiprocessing libraries to help
you run multiple processes in parallel and a set of types so you can collect
the results.  Multitools is based on those libraries, and aims to make your
life easier especially if you need the processes to work together. It adds
the following features to the standard libs:

- Simpler argument passing to process objects

- A collection to run all processes together

- A supervisor object which gives you:

  - Automatic data connections to allow you to pass picklable objects out
    (rather than having to use multiprocessing.Value)

  - A messaging system letting you pass data between concurrent processes

  - A process discovery API letting you plug in and remove processes with
    less code churn

  - A mechanism for processes to declare interesting message types, making
    the receiver declare what messages it responds to, rather than the
    sender needing to know the names of receptive processes

Multiprocessing - a quick recap
===============================

You don't need this library if you're happy with the standard multiprocessing
library, so it's worth going back to looking at how to use that::

    import multiprocessing

    def op(result, arg_one, arg_two):
        result.value = arg_one * arg_two

    val = multiprocessing.Value('i',0)
    p = multiprocessing.Process(target=op, args=[val,1234,5678])
    p.start()
    p.join()
    print "Result", val.value

The above is a simple example of how you can run code in a separate process,
that wouldn't actually be any quicker to run in parallel.  You'd need to
start and join two processes to get any useful parallelism.

You can also derive your own process from multiprocessing.Process, so you
don't need to pass those target and args arguments.  You'll need to pass
your arguments to the Process constructor though, so in terms of boiler
plate code, you're swapping one lot for the other.

Replace the definition of op() with this class declaration::

    class MyProcess(multiprocessing.Process):
        def __init__(self, result, arg_one, arg_two):
            self.result = result
            self.arg_one = arg_one
            self.arg_two = arg_two
            super(MyProcess, self).__init__()

        def run(self):
            self.result.value = self.arg_one * self.arg_two

You can instantiate your object now using easier argument passing::

    p = MyProcess( val, 1234, 5678 )

Using multitools
================

ProcessList
-----------

ProcessList is a collection that allows you to add() multiprocessing.Process
objects.  Once you've added them all you can start() them all together, join()
them, check their is_alive() status or even terminate() them as a unit (see
the warnings in the multiprocessing docs about using terminate() on Process
objects though).

To implement the same example a third time, but this time using
multitools.ProcessList, import multitools and add::

    pl = multitools.ProcessList()
    pl.add( p )

Now use pl.start() and pl.join() just as we previously started and joined
the Process object directly.  With just one process added you don't gain
anything from ProcessList, but if you run more than one process concurrently
with your main process, you can save typing.  For example::

    import multiprocessing
    import multitools

    def op_square(result, arg_one):
        result.value = arg_one * arg_one

    def op_double(result, arg_two):
        result.value = arg_two + arg_two

    pl = multitools.ProcessList()
    val_one = multiprocessing.Value('i',0)
    val_two = multiprocessing.Value('i',0)
    pl.add(multiprocessing.Process( target = op_square, args=[val_one, 1234] ))
    pl.add(multiprocessing.Process( target = op_double, args=[val_two, 5678] ))
    pl.start()
    pl.join()
    print "Result one", val_one.value
    print "Result two", val_two.value

To do the same without using multitools.ProcessList, you'd need to run
Process.start() and Process.join() on all of them.  That's all ProcessList
does; it collects a set of multiprocessing.Processes and allows you to run them
together.

Introducing ipc.client.Process
------------------------------
You can declare these Process objects and instantiate them like this::

    import multitools.ipc.client
    import multiprocessing

    class MyProcess(multitools.ipc.client.Process):
        def setup(self, result, arg_one, arg_two):
            self.result = result
            self.arg_one = arg_one
            self.arg_two = arg_two

        def op(self):
            self.result.value = self.arg_one * self.arg_two

    val = multiprocessing.Value('i',0)
    p = MyProcess( val, 1234, 5678 )
    p.start()
    p.join()
    print "Result:", val.value

multitools.ipc.client.Process works in much the same way as
multiprocessing.Process, although note that your arguments get sent to a
setup() method (so you don't need to write your own constructor) and you
do your work in an op() method again. 

Introducing ipc.host.Supervisor
-------------------------------
::

    import multiprocessing
    import multitools.ipc.client, multitools.ipc.host

    class MyProcess(multitools.ipc.client.Process):
        M_NAME = None

        def setup(self, result, arg_one, arg_two):
            self.result = result
            self.arg_one = arg_one
            self.arg_two = arg_two

        def op(self):
            self.result.value = self.arg_one * self.arg_two

    s = multitools.ipc.host.Supervisor()
    val = multiprocessing.Value('i', 0)
    s.add( MyProcess(val, 1234, 5678) )
    s.supervise()
    print "Result:", val.value

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
different processes can be printing at the same time.

The prnt() function of ipc.client.Process is a drop in replacement for the
print operator, when you're using the supervisor::

    import multitools.ipc.client, multitools.ipc.host

    class MyProcess(multitools.ipc.client.Process):
        def setup(self, arg_one, arg_two):
            self.arg_one = arg_one
            self.arg_two = arg_two

        def op(self):
            self.prnt("Result:", self.arg_one * self.arg_two)

    s = multitools.ipc.host.Supervisor()
    s.add( MyProcess(1234, 5678) )
    s.supervise()

This code will print the same result as the previous example, but you can see
how we've eliminated the need for a multiprocessing.Value, and made it so that
the process will print out the result by itself.  It's shorter and better
encapsulated.

Supervisor Handlers
...................

One basic way to extend the supervisor is to use the handlers.  These are
callable arguments passed to the supervisor to extend its functionality.

These arguments are named prntHandler and objHandler for the print handler
and object handler respectively.

The print handler:

You can override the behaviour of the prnt() function by passing a
print handler to the supervisor e.g. ::

    def myPrntHandler(p):
        print "CAUGHT", p

    s.supervise( prntHandler=myPrntHandler )

Add this to the previous code example (replacing the supervisor() call with
this one), and this now prints 'CAUGHT Result: 7006652'.

This mechanism could be used for a simplified form of debug logging, or
progress logging.

The object handler:

The object handler is a function passed to the supervisor using the
objHandler named argument::

    import multitools.ipc as ipc
    from multitools.ipc.client import Process
    from multitools.ipc.host import Supervisor

    class MyProcess(Process):
        def setup(self, arg_one, arg_two):
            self.arg_one = arg_one
            self.arg_two = arg_two

        def op(self):
            self.send_object(self.arg_one * self.arg_two)

    def myObjHandler(m):
        print "Result:", m

    s = Supervisor()
    s.add( MyProcess(1234, 5678) )
    s.supervise( objHandler = myObjHandler )

The ipc.Process class has a method called send_object which will send any
object you pass back to the supervisor.  Without an object handler, the
supervisor will throw an exception on receiving an unrecognised object::

    ERROR: Supervisor; Invalid message received;
      7006652:
      Unknown object sent to supervisor: 7006652

Supply an object handler (objHandler) though, and that callable will be
called with the object that was sent every time, and in this case will
print out the result rather than an error::

    Result: 7006652

Note that even though we're now passing the value out of the subprocess,
we've got rid of having to import multiprocessing to use a Value object,
we can just use any serialisable object now (an int in this case).
You can still use multiprocessing.Value if you want a value you can pass
around and modify from any subprocess, but it's unnecessary if you just want
to get a value out.

ipc.client.Process.inpt()
-------------------------

Getting user input from within a process can be tricky for the same reasons
as why printing is tricky.

The inpt() function saves you all that trouble.  Call it, and it will
sit and wait for user input, then return what they entered to you. In
other words it's a blocking call that returns the user input.

If you want a prompt, you can pass it as an argument::

    class MyProcess(multitools.ipc.client.Process):
        M_NAME='My process'
        ...
        def op(self):
            ...
            name = self.inpt( "Enter your name:" )
            ...

See how we've now had to give the process a M_NAME, to name the process for
the supervisor, because the supervisor needs to have a name for the process
that asked for input so that it can reply once the user's entered their data.

Note in the present version, inpt will still stop other processes
communicating with each other while it blocks for input.

Sending IPC messages
====================

Using the object and print handlers can be a good way to implement your
project, although it does mean that the logic controlling how the processes
interact is distinct from the processes that do the work.

You might find a better design for your code by using the ability for the
processes to talk to each other, such that the system behaviour can emerge
from the interaction of the separate processes.  The logic of what to do
based on which events can be encapsulated within the process that does the
work.

IPC stands for inter-process communication.  The new objects introduced so far
(except for ProcessList) are all designed to enable this communication.  To
communicate from one process to another, you'll need to send a message object.

IPC message objects
-------------------

multitools.ipc defines a handful of message object types.  Message objects
follow a heirarchy, with all deriving ultimately from
multitools.ipc.EmptyMessage.

EmptyMessage takes only one argument - the target id, that is the id of the
target process that should receive the message::

    message = EmptyMessage( "target_id" )

In practice, you'll rarely instantiate an empty message, unless you subclass
it to give it a type that you can use as an event notifier.  Other message
types take arguments, such as StringMessage::

    message = StringMessage( "target_id", "Test Message" )

Process ids
-----------

Every named process added to a host.Supervisor gets a process id (p_id)::

    from multitools.ipc.client import Process
    from multitools.ipc.host import Supervisor
    import time

    class MyProcessOne(Process):
        M_NAME = "Process one"

        def op(self):
            time.sleep(1)

    s = Supervisor()
    p = MyProcessOne()
    s.add( p )
    print p.p_id

The p_id is what you need to put as the target id in a message object, and
sending it will cause it to be sent to that process::

    import multitools.ipc as ipc

    class MyProcessTwo(Process):
        M_NAME = None

        def setup(self, target, arg):
            self.target = target
            self.arg = arg

        def op(self):
            self.send_object(ipc.StringMessage( self.target, self.arg ))

    s.add( MyProcessTwo(p.p_id, "Test message") )
    s.supervise()

You'll get an exception if you run this code; because the supervisor tries to
send the StringMessage to MyProcessOne (as identified by it's p_id), but
MyProcessTwo has no way of reacting to it.  Now, what do we need to do to fix
that?

multitools.client.ipc.Process.handle_message()
----------------------------------------------

The exception you'll receive is::

    ....
      File "/usr/lib/pythonx.xx/site-packages/multitools/ipc/client/__init__.py", line nnn, in handle_message
        raise NotImplementedError('Someone has sent you a message.  You must override this method to handle it.')
    NotImplementedError: Someone has sent you a message.  You must override this method to handle it.

This tells you that your process hasn't implemented handle_message().  You
react to incoming messages by implementing this method::

    class MyProcessOne(Process):
        ...

        def handle_message(self,m):
            print m

This will print out a slightly cryptic message::
    StringMessage to 0xnnnnnnnn_1;"Test message"
where 0xnnnnnnnn_1 is the p_id of MyProcessOne.

You'll note the bit in quotes is the string you sent.  To get the message
unadorned you can print its m.message argument, but to do that safely we'd
need to ensure it is a StringMessage first.  But all messages provide a
descriptive message when printed as is, which is fine for debug or an example
such as this.

The 'time.sleep(1)' statement in the op() of MyProcessOne is simply there so
that the process doesn't terminate before the message can be received.  Once
your op() implementation completes, your process becomes incommunicado. If
you replace it with 'pass' you'll get the following message::

    ERROR: Supervisor; Invalid message received;
    StringMessage to 0xb6ff33ccL_1;"Test message":
    All processes with id '0xb6ff33ccL_1' have terminated, or were not valid

It's right; MyProcessOne will have terminated, because it reached the end of
it's op() before the message could be sent to it.  Put the 'time.sleep(1)'
statement back and the example will work again.

Be aware that a return code of False from your handle_message function is
treated as a signal to terminate the process.  If you want to stop the process
because the message received indicates no more work is to be done, just return
False.  If an error has occurred, but you don't want to use an exception, you
can display a message then return False - this will kill your process, but
leave others running, unlike raising an exception.

multitools.ipc.client.Process.get_ids()
---------------------------------------

At last we get to explain concretely why you need to set an M_NAME
identifier.  Process.get_ids() takes a name as a string, asks the supervisor
for the set of processes with that name as their M_NAME, and returns their
ids.

You saw earlier how to use a process id with client.Process.send_object().
The owning namespace pulls the p_id out of the process which is to receive
the message and passes that to the sender as an argument.  That's all fine
and dandy if you know when you're writing that code who's going to be sending
messages to who, but it's a rather fragile design.

Better is to use self.get_ids() from within your client.Process.  This allows
you to put all you need to send a message within the sending process::

    from multitools.ipc.client import Process
    from multitools.ipc.host import Supervisor
    import multitools.ipc as ipc
    import time

    class MyProcessOne(Process):
        M_NAME = "My Process One"

        def op(self):
            time.sleep(1)

        def handle_message(self,m):
            print "Hi from MyProcessOne:", m.message

    class MyProcessTwo(Process):
        M_NAME="My Process Two"

        def setup(self, arg):
            self.arg=arg

        def op(self):
            targets = self.get_ids( 'My Process One' )
            self.send_object(ipc.StringMessage( targets.pop(), self.arg ))

    s = Supervisor()
    s.add( MyProcessOne() )
    s.add( MyProcessTwo("Test message") )
    s.supervise()

See how outside of the function calls, we just instantiate the supervisor, add
the processes to it, and supervise them.  No need to go poking around inside
MyProcessOne to get its id to pass to MyProcessTwo this way round.

Note that get_ids doesn't throw an exception in the case it can't find any
matching process ids; it will return the empty set.  In this example you'd
get a KeyError on trying to pop() the empty set, should you have given
get_ids a name that doesn't match.

client.Process.send_message()
-----------------------------

Note that get_ids() returns a list of ids, because there may be more than
one process with the same name.  Instead of assuming there's only one id
(as in the example above) or iterating over the list, you can use
self.send_message()::

    self.send_message(
      self.get_ids('My Process One'),ipc.StringMessage,'This is my message'
    )

send_message() takes a set of ids as the first argument, then the type of
the message object to send, then the arguments to the message constructor.
It iterates over the ids for you, creates a message object for each target
then sends them.

If you pass send_message the empty set, due to having given get_ids a name
that doesn't match any processes the supervisor knows about, an IndexError
exception will be raised.

Advanced functionality
======================

Non-blocking get_ids()
----------------------

The supervisor can be very busy to begin with as all processes are asking for
their first ids, so it may make sense to get your request in early.  If the
supervisor replies, that message will be cached so that if you later call
get_ids() in normal blocking mode when you want to send a message, it can
return the ids immediately (else it will block until the supervisor replies).

That looks like this::

    def op(self):
        self.get_ids("Process two", block=False) # Prep the supervisor for ids
        ...

    def handle_message(self, m):
        if isinstance(m, ipc.StringMessage):
            # Use the cached ids, if available
            self.send(self.get_ids("Process two"), ipc.StringMessage, str(m))
        elif ...

Exception Handling
------------------

If a process hangs, and you terminate it using ctrl-C (or otherwise send a
SIGINT signal on unix/linux), you'll get tracebacks for the unwinding of the
multiprocessing code for all running processes, which can make identifying the
codepath that hung a bit tricky.

Other exceptions are handled a bit more serenely when using multitools though.
When one process raises an exception, multitools catches it and pretties up
the output slightly making it easier to distinguish between your code fouling
up and the rest of the smoke and mirrors being unwound.  The other processes
are silently terminated, so control returns to you and you can start debugging
immediately.

Message objects extended
------------------------

multitools.ipc defines a handful of useful message objects, which you're
free to reuse or extend for your own purposes.  All message objects, for the
purposes of the supervisor should inherit from multitools.ipc.EmptyMessage,
define a decent __str__() method for logging purposes, and take a target id as
the first argument to the constructor (for client.Process.send_message()),
for example::

    import multitools.ipc as ipc

    class IntegerMessage(ipc.EmptyMessage):
        def __init__(self, target, value):
            self.value = value
            super( IntegerMessage, self ).__init__(target)

        def __str__(self):
            return "{0}; Value {1}".format(
              super( IntegerMessage, self ).__str__(), self.value
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

To make one, the client module provides a Resident protype::

    from mulitools.ipc.client import Resident

    class MyProcess(Resident):
        M_NAME = "My process"

        def handle_message(self, m):
            if isinstance(m, ...
                ...

Once all other processes have terminated, this module will terminate as well.

Listener processes
------------------

You can make your process into a listener process just by declaring
self.LISTEN_TYPE as a list of IPC message types::

    class MyProcess(multitools.ipc.client.Process):
        M_NAME = 'My Process'
        LISTEN_TYPE = [StringMessage, FileMessage]
        ...

Now the process will receive all messages of type StringProcess (or a subtype
of that, such as multitools.ipc.InptResponseMessage) or FileMessage.  That's
even if they weren't sent to your process.

That can be used to extend event behaviours when modifying your project.  You
have two pre-existing processes which communicate, but by adding a third
process which listens to their messages you can add behaviours without
modifying the original two processes.

It's also a way to design your project from the start, when used with the
LISTENERS meta-target defined in multitools.ipc.host.Supervisor.  Send it
to that meta-target instead of a real target id, and it will be sent only
to the messages specifically listening for that type (or a supertype of it)::

    self.send_message( multitools.ipc.host.Supervisor.LISTENERS, EmptyMessage )

Note you will get an exception if nobody's listening for that type, so it
ends up being sent to nobody.  If you just don't care that nobody's going
to receive it, you'll need to catch and deal with that exception.

BROADCAST messages
------------------

Broadcast messages are those sent to all named processes.  It's just used as a
process id like any other, and just as easy to use::

    self.send_message( multitools.ipc.host.Supervisor.BROADCAST, EmptyMessage )

Loggers
-------

Loggers are just resident processes that listen to messages and perform some
action on them (defined as 'logging' them) but nothing else.  It's designed
as a process that reports on activity, records it to file or screen, or
updates a percantage progress indicator, that type of thing.

There is a base class defined in multitools.ipc.logger, called Logger().
The class defines op and handle_message for you, so you only need to
declare your method to handle messages::

    import multitools.ipc.logger

    class MyLogger(multitools.ipc.logger.Logger):
        M_NAME = 'My logger'
        LISTEN_TYPE = [MyMessages]
        def log(self, m):
            self.prnt(m)

The module provides a standard DebugLogger which listens to all messages that
derive from EmptyMessage and prints them out.  You may find it useful during
development of your project to add it to the Supervisor object, and remove it
once you've proven that messages are flowing as you expected, before release.

To Conclude
===========

That concludes the tour of the multitools api.  It's now up to you to decide
whether it's worth using for your own project - you can still do anything you
can do with multiprocessing.Process with multitools.ipc.client.Process, but
additionally when used with multitools.ipc.host.Supervisor, you can write
communicative code that's simpler and more maintainable.

Its inspiration was a project that hangs off a slow IO-bound process, so I'm
not sure how quickly it can be made to work (you can try setting the interval
argument to Supervisor.supervise() to something less than the default 0.1s),
but you'll need better hardware than I'm currently running to test that out
though.
