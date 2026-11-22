"""TCPKISS and SerialKISS against real sockets and a pseudo-terminal."""

import asyncio
import contextlib
import os
import socket
import threading
import time

import pytest
from ax253 import Frame

from kiss import TCPKISS, SerialKISS, kiss, util
from kiss.constants import FEND, KISS_ON

AX25 = bytes(Frame.from_str("N0CALL>APRS,WIDE1-1:>hello "))
KISS_FRAME = FEND + b"\x00" + AX25 + FEND


class TNCServer:
    """A one-connection KISS TCP 'TNC' running in a thread."""

    def __init__(self, send=b""):
        self.listener = socket.create_server(("127.0.0.1", 0))
        self.port = self.listener.getsockname()[1]
        self.send = send
        self.received = b""
        self.conn = None
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        self.conn, _ = self.listener.accept()
        self.conn.sendall(self.send)
        while True:
            try:
                data = self.conn.recv(4096)
            except OSError:
                break
            if not data:
                break
            self.received += data

    def wait_for(self, n_bytes, timeout=5):
        deadline = time.time() + timeout
        while len(self.received) < n_bytes and time.time() < deadline:
            time.sleep(0.01)
        return self.received

    def close(self):
        if self.conn:
            with contextlib.suppress(OSError):
                self.conn.shutdown(socket.SHUT_RDWR)
            self.conn.close()
        self.listener.close()
        self.thread.join(5)


@pytest.fixture
def tnc():
    servers = []

    def make(send=b""):
        servers.append(TNCServer(send))
        return servers[-1]

    yield make
    for s in servers:
        s.close()


def test_tcpkiss_read_write_settings(tnc):
    server = tnc(send=KISS_FRAME * 2)
    k = TCPKISS("127.0.0.1", server.port, strip_df_start=True)
    k.start(TX_DELAY=40, PERSISTENCE=b"\x3f")
    try:
        assert k.read(min_frames=2) == [AX25, AX25]
        k.write(AX25)
        expected = FEND + b"\x01\x28" + FEND + FEND + b"\x02\x3f" + FEND + KISS_FRAME
        assert server.wait_for(len(expected)) == expected
    finally:
        k.stop()


def test_create_tcp_connection_with_settings(tnc):
    server = tnc(send=KISS_FRAME)

    async def main():
        transport, protocol = await kiss.create_tcp_connection(
            "127.0.0.1",
            server.port,
            kiss_settings={kiss.Command.TX_TAIL: 3},
        )
        frames = [f async for f in protocol.read(n_frames=1)]
        transport.close()
        return frames

    frames = asyncio.run(main())
    assert [bytes(f) for f in frames] == [AX25]
    assert server.wait_for(4) == FEND + b"\x04\x03" + FEND


@pytest.fixture
def pty_pair():
    pytest.importorskip("termios")
    controller, worker = os.openpty()
    import tty

    tty.setraw(worker)
    yield controller, os.ttyname(worker)
    os.close(controller)
    os.close(worker)


def _read_fd(fd, n_bytes, timeout=5):
    import select

    data = b""
    deadline = time.time() + timeout
    while len(data) < n_bytes and time.time() < deadline:
        ready, _, _ = select.select([fd], [], [], 0.1)
        if ready:
            data += os.read(fd, 4096)
    return data


def test_serialkiss_over_pty(pty_pair):
    controller, device = pty_pair
    k = SerialKISS(device, "9600", strip_df_start=True)
    k.start(TX_DELAY=50)
    try:
        assert _read_fd(controller, 4) == FEND + b"\x01\x32" + FEND
        # split the incoming frame across two writes, as a UART would
        os.write(controller, KISS_FRAME[:7])
        time.sleep(0.05)
        os.write(controller, KISS_FRAME[7:])
        assert k.read(min_frames=1) == [AX25]
        k.write(AX25)
        assert _read_fd(controller, len(KISS_FRAME)) == KISS_FRAME
        k.config_xastir()
        assert _read_fd(controller, 5 * 4).count(FEND) == 10
        k.kiss_off()
        assert _read_fd(controller, 4) == FEND + b"\xff" + FEND + FEND
    finally:
        k.stop()


def test_util_helpers(sample_frames):
    assert util.strip_df_start(b"\x00\x00abc \r\n") == b"abc"
    assert util.strip_nmea(b"\xf0$GPGGA\r\n") == b"$GPGGA"
    assert util.strip_nmea(b"") == b""
    log = util.getLogger("kiss.test.helper")
    assert util.getLogger("kiss.test.helper") is log
    assert len(log.handlers) == 1


def test_serialkiss_kiss_on(pty_pair):
    controller, device = pty_pair
    k = SerialKISS(device, "9600")
    k.start_no_config()
    try:
        k.kiss_on()
        assert _read_fd(controller, len(KISS_ON)) == KISS_ON
    finally:
        k.stop()


def test_drain_timeout_logs_and_returns(caplog):
    class StuckTransport:
        def write(self, data):
            pass

        def get_write_buffer_size(self):
            return 10

        def is_closing(self):
            return False

    k = TCPKISS("127.0.0.1", 1)
    k.drain_timeout = 0.05
    asyncio.set_event_loop(k.loop)
    k._protocol = kiss.KISSProtocol()
    k.protocol.transport = StuckTransport()
    k.write(AX25)
    assert "still queued" in caplog.text
    k._protocol = None


def test_ax25_decoder_skips_undecodable_data_frame():
    d = kiss.AX25KISSDecode()
    frames = list(d.update(FEND + b"\x00short" + FEND + KISS_FRAME))
    assert [bytes(f) for f in frames] == [AX25]


@pytest.mark.parametrize(
    "value, ok",
    [(b"a", True), (b"ab", True), (b"", False), (b"abc", False)],
)
def test_util_valid_length(value, ok):
    import attr

    @attr.s
    class Holder:
        v = attr.ib()

    validator = util.valid_length(1, 2, attr.validators.instance_of(bytes))
    if ok:
        validator(None, attr.fields(Holder).v, value)
    else:
        with pytest.raises(ValueError):
            validator(None, attr.fields(Holder).v, value)


def test_util_instance_of_or_and_optional_bool_or_bytes():
    import attr

    @attr.s
    class Holder:
        v = attr.ib()

    validator = util.instance_of_or(bool, attr.validators.instance_of(bytes))
    validator(None, attr.fields(Holder).v, True)
    with pytest.raises(TypeError):
        validator(None, attr.fields(Holder).v, "x")
    assert util.optional_bool_or_bytes(None) is None
    assert util.optional_bool_or_bytes(True) is True
    assert util.optional_bool_or_bytes(bytearray(b"x")) == b"x"


@pytest.mark.parametrize(
    "cls,args", [(TCPKISS, ("127.0.0.1", 1)), (SerialKISS, ("/dev/x", "9600"))]
)
def test_stop_before_start_is_harmless(cls, args):
    cls(*args).stop()
