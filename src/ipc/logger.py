import multitools.ipc.client

class Logger(multitools.ipc.client.Process):
    RESIDENT=True

    def op(self):
        while True:
            m=self.pipe.recv()
            if isinstance(m, multitools.ipc.ResidentTermMessage):
                break
            else:
                self.log(m)

        def log(self, m):
            raise NotImplementedError('This log() method is an example that should be overridden')

class DebugLogger(Logger):
    M_NAME="Debug Logger"
    def log(self, m):
        self.prnt(m)

