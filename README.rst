===========
Multitools
===========
A suite of python 2.x tools to make working with multiple simultaneously running processes easier and more powerful.

It's based on the multiprocessing library.  Oh, and it needs python 2.7 or better.

Building it
===========

This is distributed as a disttools library, so it install it you'll need root
rights and to be able to execute (in the root directory of the repo)::

    # python setup.py install

That will install the library to your systems python library directory (e.g.
/usr/lib/python2.7/site-packages) so you can just use it like any other
importable library::

    import multitools
    dir(multitools)

How to use it
=============

Further documentation exists as API pydoc, and in the
`guide documentation <doc/guide.rst>`_ which takes you through running
multiprocssing code to using multitools in all the different ways it can be
used, assuming you're familiar with python coding.
