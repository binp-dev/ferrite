import multiprocessing
import zmq
from subprocess import Popen
import time

class Bash:
    def __init__(self):
        self.proc = None

    def __enter__(self):
        self.proc = Popen(
            ["/usr/bin/env", "bash"],
            text=True
        )
        time.sleep(1)
        print("ioc '%s' started")

    def __exit__(self, *args):
        print("terminating '%s' ...")
        self.proc.terminate()
        print("ioc '%s' terminated")

class Pong:
    def __init__(self):
        self.proc = None

    def pong(self):
        context = zmq.Context()
        sock = context.socket(zmq.PAIR)
        sock.connect("tcp://127.0.0.1:8321")

        for i in range(5):
            req = sock.recv()
            print('Pong got request:', req)
            sock.send_unicode('pong %s' % i)

    def __enter__(self):
        self.proc = multiprocessing.Process(target=self.pong)
        self.proc.start()

    def __exit__(self, *args):
        self.proc.join()
        print('Pong joined')

if __name__ == "__main__":
    context = zmq.Context()
    sock = context.socket(zmq.PAIR)
    sock.bind("tcp://127.0.0.1:8321")

    with Bash(), Pong():

        for i in range(5):
            sock.send_unicode('ping %s' % i)
            rep = sock.recv_unicode()
            print('Ping got reply:', rep)

        print("Success")
