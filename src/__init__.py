#!/usr/bin/env python

'''
Multitools

A utility class providing you tools to work with multiple multiprocessing
Process objects and to pass messages between them.
'''

class ProcessList(object):
    '''
    A wrapper class to collect together a bunch of multiprocessing.Process
    objects and apply functions like start() or join() to them all.
    '''

    def __init__(self):
        self.processes=[]
        super(ProcessList, self).__init__()

    def add(self, process):
        '''
        Add a Process to be later start()ed

        '''
        self.processes.append(process)

    def add_list(self, processes):
        '''
        Add a list of Processes to be later start()ed
        '''
        for p in processes:
            self.add(p)

    def start(self):
        '''
        Start all Processes
        '''
        for p in self.processes:
            p.start()

    def is_alive(self):
        '''
        Return True if any Processes are still running
        '''
        alive=False
        for p in self.processes:
            if p.is_alive(): alive=True
        return alive

    def join(self,timeout=None):
        '''
        Join all Processes.  Block until all Procesesses have terminated, or
        until the timeout is over

        Options:
        timeout - Number of seconds (may be fractional) to block for per process
        '''
        for p in self.processes:
            p.join(timeout)

    def terminate(self):
        '''
        Terminate all Processes, for an emergency shutdown.  See the
        multiprocessing docs for warnings about Process.terminate().
        '''
        for p in self.processes:
            p.terminate()

import unittest, ctypes, multiprocessing, time

class TestProcessList(unittest.TestCase):
    class JobOne(multiprocessing.Process):
        def __init__(self, have_run):
            self.have_run=have_run
            super(TestProcessList.JobOne, self).__init__()

        def run(self):
            self.have_run.value=1

    class JobTwo(JobOne):
        def run(self):
            self.have_run.value=1

    class JobSlow(JobOne):
        def run(self):
            time.sleep(1)
            self.have_run.value=1

    def setUp(self):
        self.p=ProcessList()
        self.j1=self.JobOne(multiprocessing.Value(ctypes.c_int,0))
        self.j2=self.JobTwo(multiprocessing.Value(ctypes.c_int,0))
        self.js=self.JobSlow(multiprocessing.Value(ctypes.c_int,0))

    def test_init(self):
        self.assertEqual(self.p.processes,[])

    def test_add(self):
        self.p.add(self.j1)
        self.assertEqual(len(self.p.processes),1)
        self.assertEqual(self.p.processes[0].have_run.value,0)
        self.p.add(self.j2)
        self.assertEqual(len(self.p.processes),2)
        self.assertEqual(self.p.processes[1].have_run.value,0)

    def test_add_list(self):
        self.p.add_list([self.j2,self.j1])
        self.assertEqual(len(self.p.processes),2)
        self.assertEqual(self.p.processes[1].have_run.value,0)
        self.assertEqual(self.p.processes[0].have_run.value,0)

    def test_start(self):
        self.p.add_list([self.j1,self.j2])
        self.p.start()
        self.p.join()
        self.assertEqual(self.p.processes[0].have_run.value,1)
        self.assertEqual(self.p.processes[1].have_run.value,1)

    def test_is_alive(self):
        self.p.add_list([self.js,self.j2])
        self.p.start()
        self.assertTrue(self.p.is_alive())
        self.p.join()
        while self.js.have_run.value==0:
            pass
        self.assertFalse(self.p.is_alive())

    def test_join(self):
        self.p.add_list([self.j1, self.js])
        self.p.start()
        self.p.join(timeout=0.1)
        self.assertEqual(self.js.have_run.value, 0)
        self.p.join()
        self.assertEqual(self.js.have_run.value, 1)

    def test_terminate(self):
        self.p.add(self.js)
        self.p.start()
        self.p.terminate()
        self.assertEqual(self.js.have_run.value, 0)

if __name__=='__main__':
    unittest.main()
