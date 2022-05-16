import io
from pathlib import Path
import random
from unittest import mock

import pytest

import kiss3
from kiss3 import KISS, constants, SerialKISS, TCPKISS
from kiss3.ax25 import Address, Frame
from kiss3.util import getLogger
from .constants import ALPHANUM, TEST_FRAMES


__author__ = "Masen Furer KF7HVM <kf7hvm@0x26.net>"  # NOQA pylint: disable=R0801
__copyright__ = (
    "Copyright 2022 Masen Furer and Contributors"  # NOQA pylint: disable=R0801
)
__license__ = "Apache License, Version 2.0"  # NOQA pylint: disable=R0801


logger = getLogger(__name__)


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


@pytest.fixture
def dummy_interface():
    return mock.Mock()


@pytest.fixture
def dummy_serialkiss(dummy_interface):
    ks = kiss3.SerialKISS(port=random_alphanum(), speed="9600", strip_df_start=True)
    ks.interface = dummy_interface
    return ks


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

        class BytesIOSerial(io.BytesIO):
            @property
            def in_waiting(self):
                return int(self.readable())

            def isOpen(self):
                return self.tell() < len(self.getbuffer())

        def make_serial(data_buffer=b"", **kwargs):
            sk = SerialKISS("/dev/foo", "9600", **kwargs)
            sk.buffer = sk.interface = BytesIOSerial(data_buffer)
            return sk

        return make_serial


@pytest.fixture
def sample_frames():
    return (Path(__file__).parent / TEST_FRAMES).read_bytes().split(b"\n")


@pytest.fixture(params=[0, 1])
def sample_frame(request, sample_frames):
    return sample_frames[request.param]


@pytest.fixture
def payload_frame():
    frame = Frame(
        destination=Address.from_text(random_alphanum(6)),
        source=Address.from_text(random_alphanum(6)),
        path=[
            Address.from_text(random_alphanum(6)),
            Address.from_text(random_alphanum(6), a7_hldc=True),
        ],
        info=" ".join(
            [random_alphanum(), "this is the data for the frame", random_alphanum()]
        ),
    )
    logger.debug('frame="%s"', frame)
    return frame


def random_alphanum(length=8, alphabet=ALPHANUM):
    """
    Generates a random string for test cases.

    :param length: Length of string to generate.
    :param alphabet: Alphabet to use to create string.
    :type length: int
    :type alphabet: str
    """
    return "".join(random.choice(alphabet) for _ in range(length))
