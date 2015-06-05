===========
Multitools
===========
A suite of python 2/3 tools to make working with multiple simultaneously running processes easier and more powerful.

It's based on the multiprocessing library.  Needs python 2.7.4/3.0 or better.

Building it
===========

This is distributed as a disttools library, so to install it you'll need root
rights and to be able to execute (in the root directory of the repo)::

    # python setup.py install

That will install the library to your systems python library directory (e.g.
/usr/lib/python2.7/site-packages) so you can just use it like any other
importable library::

    import multitools
    dir(multitools)

How to use it
=============

To test your install after installing it, run the test_all bash script.  This
uses the find command to locate source files, and runs them through python,
which causes them to run their internal unit tests.

You can specify the python interpreter to use with the -p argument, e.g.::

    $ ./test_all -p python3

The argument to -p must be an executable which is on your current path.

Further documentation exists as API pydoc, and in the
`guide documentation <doc/guide.rst>`_ which takes you through running
multiprocssing code to using multitools in all the different ways it can be
used, assuming you're familiar with python coding.
