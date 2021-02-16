import os
import time
import zmq

from utils.epics.ioc import Ioc
from utils.epics import ca
import utils.proto as proto

IDS = None

def decode_wf_data(data, nbytes=3, dlen=256):
    cmd = int(data[0])
    assert(cmd == IDS["PSCA_WF_DATA"])
    assert(int(data[1]) == len(data) - 2)

    arr = data[2:]
    arr = [arr[i : i + nbytes] for i in range(0, len(arr), nbytes)]
    assert(all([len(a) == nbytes for a in arr]))
    arr = [int.from_bytes(a, "little") for a in arr]
    return arr

def encode(id, data=b""):
    assert(len(data) <= 256 - 2)
    return bytes([id, len(data)]) + data

def assert_pop(queue, arr):
    print(arr)
    assert len(queue) >= len(arr)
    try:
        assert all((a == b for a, b in zip(queue, arr)))
    except AssertionError:
        print("{} != {}".format(queue[:len(arr)], arr))
        raise
    return queue[len(arr):]

def send(socket, data):
    print(f"[fakedev] sending data ...")
    socket.send(data)
    print(f"[fakedev] sent {len(data)} bytes")


def recv(socket):
    print(f"[fakedev] receiving data ...")
    data = socket.recv()
    print(f"[fakedev] received {len(data)} bytes")
    return data

def run_test(
    epics_base_dir,
    ioc_dir,
    common_dir,
    arch,
):
    global IDS
    print("Running tests")

    ioc = Ioc(
        os.path.join(ioc_dir, "bin", arch, "PSC"),
        os.path.join(ioc_dir, "iocBoot/iocPSC/st.cmd")
    )

    context = zmq.Context()
    socket = context.socket(zmq.PAIR)
    socket.bind("tcp://127.0.0.1:8321")

    prefix = os.path.join(epics_base_dir, "bin", arch)
    IDS = proto.read_defines(os.path.join(common_dir, "proto.h"))
    def id_as_bytes(id):
        return bytes([id])

    wfs = 200
    print("Starting caRepeater ...")
    with ca.Repeater(prefix):
        print("Starting IOC ...")
        with ioc:
            print("Testing ...")
            start_msg = recv(socket)
            assert(int(start_msg[0]) == IDS["PSCA_START"])
            assert(int(start_msg[1]) == 0)
            print("Received start signal")

            send(socket, encode(IDS["PSCM_MESSAGE"], "Hello from MCU!".encode("utf-8")))

            queue = [0]*wfs*2
            for _ in range(4):
                send(socket, encode(IDS["PSCM_WF_REQ"]))
                queue = assert_pop(queue, decode_wf_data(recv(socket)))
            
            wf = list(range(wfs))
            ca.put(prefix, "WAVEFORM", wf, array=True)
            queue += wf*2
            for _ in range(5):
                send(socket, encode(IDS["PSCM_WF_REQ"]))
                queue = assert_pop(queue, decode_wf_data(recv(socket)))

            wf = [wfs - x - 1 for x in range(wfs)]
            ca.put(prefix, "WAVEFORM", wf, array=True)
            queue += wf*2
            for _ in range(5):
                send(socket, encode(IDS["PSCM_WF_REQ"]))
                queue = assert_pop(queue, decode_wf_data(recv(socket)))

            wf = [wfs + x for x in range(wfs)]
            ca.put(prefix, "WAVEFORM", range(0, 2*wfs, 2), array=True)
            ca.put(prefix, "WAVEFORM", wf, array=True)
            queue += wf*4
            for _ in range(9):
                send(socket, encode(IDS["PSCM_WF_REQ"]))
                queue = assert_pop(queue, decode_wf_data(recv(socket)))

            print("Testing complete")

        print("Stopped IOC")
    print("Stopped caRepeater")
    print("Test passed!")
