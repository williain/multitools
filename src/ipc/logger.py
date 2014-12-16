import multitools.ipc.client
import multitools.ipc

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
    LISTEN_TO=[multitools.ipc.EmptyMessage]

    def log(self, m):
        self.prnt(m)

