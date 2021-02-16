import multiprocessing
import zmq


addr = "tcp://127.0.0.1:5678"


def ping():
    """Sends ping requests and waits for replies."""
    context = zmq.Context()
    sock = context.socket(zmq.REQ)
    sock.bind(addr)

    for i in range(5):
        sock.send_unicode("ping %s" % i)
        rep = sock.recv_unicode()  # This blocks until we get something
        print("Ping got reply:", rep)


def pong():
    """Waits for ping requests and replies with a pong."""
    context = zmq.Context()
    sock = context.socket(zmq.REP)
    sock.connect(addr)

    for i in range(5):
        req = sock.recv_unicode()  # This also blocks
        print("Pong got request:", req)
        sock.send_unicode("pong %s" % i)


if __name__ == "__main__":
    pong_proc = multiprocessing.Process(target=pong)
    pong_proc.start()

    ping()

    pong_proc.join()
