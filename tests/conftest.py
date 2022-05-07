import io
from pathlib import Path
from unittest import mock

import pytest

from kiss3 import KISS, constants, SerialKISS, TCPKISS


class MockKISS(KISS):
    def __init__(self, data_buffer=b"", **kwargs):
        super().__init__(**kwargs)
        self.buffer = io.BytesIO(data_buffer)

    def _read_handler(self, read_bytes=None):
        return self.buffer.read(read_bytes or constants.READ_BYTES)

    def _write_handler(self, frame=None):
        if not frame:
            return 0
        return self.buffer.write(frame)

    def start(self, **kwargs):
        return

    def stop(self):
        return


@pytest.fixture(params=[MockKISS, TCPKISS, SerialKISS])
def kiss_instance(request):
    if request.param is MockKISS:
        return MockKISS
    if request.param is TCPKISS:

        def make_tcp(data_buffer=b"", **kwargs):
            tk = TCPKISS("localhost", "8001", **kwargs)
            tk.interface = mock.Mock()
            tk.buffer = io.BytesIO(data_buffer)
            tk.interface.recv = tk.buffer.read
            tk.interface.send = tk.buffer.write
            return tk

        return make_tcp
    if request.param is SerialKISS:

        def make_serial(data_buffer=b"", **kwargs):
            sk = SerialKISS("/dev/foo", "9600", **kwargs)
            sk.buffer = sk.interface = io.BytesIO(data_buffer)
            sk.interface.in_waiting = 0
            sk.interface.isOpen = lambda: not sk.interface.closed
            return sk

        return make_serial


@pytest.fixture
def sample_frames():
    return (Path(__file__).parent / "test_frames.log").read_bytes().split(b"\n")


@pytest.fixture(params=[0, 1])
def sample_frame(request, sample_frames):
    return sample_frames[request.param]
