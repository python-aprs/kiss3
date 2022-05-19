import io
from pathlib import Path
import random

import pytest

import kiss3
from kiss3 import kiss, SerialKISS, TCPKISS
from kiss3.ax25 import Address, Frame
from kiss3.util import getLogger
from .constants import ALPHANUM, TEST_FRAMES


__author__ = "Masen Furer KF7HVM <kf7hvm@0x26.net>"  # NOQA pylint: disable=R0801
__copyright__ = (
    "Copyright 2022 Masen Furer and Contributors"  # NOQA pylint: disable=R0801
)
__license__ = "Apache License, Version 2.0"  # NOQA pylint: disable=R0801


logger = getLogger(__name__)


class MockTransport:
    def __init__(self, protocol):
        self.buffer = io.BytesIO()
        self.protocol = protocol
        self.protocol.connection_made(self)
        self.closed = False

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            self.protocol.connection_lost(None)

    def is_closing(self) -> bool:
        return self.closed

    def data_received_callback(self, data: bytes) -> None:
        self.protocol.data_received(data)

    def write(self, data):
        self.buffer.write(data)


async def make_mock_connection(kiss_instance=None):
    protocol = kiss.KISSProtocol()
    transport = MockTransport(protocol)
    if kiss_instance:
        protocol.decoder = kiss_instance.decoder
        kiss_instance.protocol = protocol
    return transport, protocol


@pytest.fixture
def dummy_serialkiss():
    ks = kiss3.SerialKISS(port=random_alphanum(), speed="9600", strip_df_start=True)
    ks.transport, ks.protocol = ks.loop.run_until_complete(make_mock_connection(ks))
    return ks


@pytest.fixture(params=[TCPKISS, SerialKISS])
def kiss_instance(request, monkeypatch):
    def make_instance(data_buffer=b"", **kwargs):
        if request.param is TCPKISS:
            k = TCPKISS("localhost", 8001, **kwargs)
        elif request.param is SerialKISS:
            k = SerialKISS("/dev/foo", "9600", **kwargs)
        else:
            raise RuntimeError("Unexpected KISS class: {!r}".format(request.param))
        transport, protocol = k.loop.run_until_complete(make_mock_connection(k))
        if data_buffer:
            transport.data_received_callback(data_buffer)
        transport.close()
        return k

    return make_instance


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
