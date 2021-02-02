import os
import time
import zmq

from utils.epics import Ioc, ca
import utils.proto as proto

class TimedOut(Exception):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class Channel(object):
    def __init__(self, addr, timeout=None):
        self.addr = addr
        self.timeout = timeout

        self.context = zmq.Context()
        self.socket = context.socket(zmq.PAIR)
        
        self.socket.bind(addr)

    def _timeout_ms(self):
        if self.timeout is not None:
            return 1000 * self.timeout
        return None

    def _recv_all_raw():
        msgs = []
        while True:
            try:
                msg = self.socket.recv(zmq.NOBLOCK)
            except 

    def wait():
        if not (self.socket.poll(self._timeout_ms(), zmq.POLLIN) | zmq.POLLIN):
            raise TimedOut()

    def _send_raw(data):
        evts = self.out_poller.poll(1000*self.timeout)
        if not (evts[self.socket] | zmq.POLLOUT):
            raise TimedOut()
        self.socket.send(data, zmq.NOBLOCK)

    def send(id, )

class FakeDev(object):
    @staticmethod
    def _decode_wf_data(data, nbytes=3, dlen=256):
        cmd = int(data[0])
        assert(cmd == IDS["PSCA_WF_DATA"])
        assert(int(data[1]) == len(data) - 2)

        arr = data[2:]
        arr = [arr[i : i + nbytes] for i in range(0, len(arr), nbytes)]
        assert(all([len(a) == nbytes for a in arr]))
        arr = [int.from_bytes(a, "little") for a in arr]
        return arr

    @staticmethod
    def _encode(id, data=b""):
        assert(len(data) <= 256 - 2)
        return bytes([id, len(data)]) + data

    def __init__(self, common_dir):
        self.ids = proto.read_definitions(os.path.join(common_dir, "proto.h"))
        self.addr = addr
        
        self._io = None
    
    def _io_gen(self):
        queue = []
        channel = Channel(self.addr)
        channel.send()

    def io(self):
        if not self._io:
            self._io = self._io_gen()
        return self._io

def assert_pop(queue, arr):
    print(arr)
    assert len(queue) >= len(arr)
    try:
        assert all((a == b for a, b in zip(queue, arr)))
    except AssertionError:
        print("{} != {}".format(queue[:len(arr)], arr))
        raise
    return queue[len(arr):]

def run_test(
    epics_base_dir,
    ioc_dir,
    common_dir,
    arch,
):
    global IDS

    ioc = Ioc(
        os.path.join(ioc_dir, "bin", arch, "PSC"),
        os.path.join(ioc_dir, "iocBoot/iocPSC/st.cmd")
    )

    # "tcp://127.0.0.1:8321"

    prefix = os.path.join(epics_base_dir, "bin", arch)
    IDS = proto.read_defines(os.path.join(common_dir, "proto.h"))
    def id_as_bytes(id):
        return bytes([id])

    wfs = 200
    with ca.Repeater(prefix), ioc:
        start_msg = socket.recv()
        assert(int(start_msg[0]) == IDS["PSCA_START"])
        assert(int(start_msg[1]) == 0)
        print("Received start signal")

        socket.send(encode(IDS["PSCM_MESSAGE"], "Hello from MCU!".encode("utf-8")))

        queue = [0]*wfs*2
        for _ in range(4):
            socket.send(encode(IDS["PSCM_WF_REQ"]))
            queue = assert_pop(queue, decode_wf_data(socket.recv()))
        
        wf = list(range(wfs))
        ca.put("WAVEFORM", wf, array=True, prefix=prefix)
        queue += wf*2
        for _ in range(5):
            socket.send(encode(IDS["PSCM_WF_REQ"]))
            queue = assert_pop(queue, decode_wf_data(socket.recv()))

        wf = [wfs - x - 1 for x in range(wfs)]
        ca.put("WAVEFORM", wf, array=True, prefix=prefix)
        queue += wf*2
        for _ in range(5):
            socket.send(encode(IDS["PSCM_WF_REQ"]))
            queue = assert_pop(queue, decode_wf_data(socket.recv()))

        wf = [wfs + x for x in range(wfs)]
        ca.put("WAVEFORM", range(0, 2*wfs, 2), array=True, prefix=prefix)
        ca.put("WAVEFORM", wf, array=True, prefix=prefix)
        queue += wf*4
        for _ in range(9):
            socket.send(encode(IDS["PSCM_WF_REQ"]))
            queue = assert_pop(queue, decode_wf_data(socket.recv()))

    print("Test passed!")
