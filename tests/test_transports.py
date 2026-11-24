"""TCPKISS and SerialKISS against real sockets and a pseudo-terminal."""

import asyncio
import contextlib
import logging
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
        self.peer_closed = threading.Event()
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
                self.peer_closed.set()
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


def test_tcpkiss_stop_closes_connection(tnc):
    """The TNC sees the close when stop() returns, without another loop run."""
    server = tnc(send=KISS_FRAME)
    k = TCPKISS("127.0.0.1", server.port, strip_df_start=True)
    k.start()
    assert k.read(min_frames=1) == [AX25]
    k.stop()
    assert server.peer_closed.wait(2)
    k.stop()  # idempotent


def test_tcpkiss_stop_inside_another_loop(tnc, recwarn):
    """
    stop() from a coroutine (or __del__ during garbage collection there)
    can't run this instance's loop; it must not raise or leave a never
    awaited coroutine, and the close completes when the loop next runs.
    """
    server = tnc()  # unread data would make the close a reset
    k = TCPKISS("127.0.0.1", server.port, strip_df_start=True)
    k.start()

    async def stop_from_coroutine():
        k.stop()
        k.stop()

    asyncio.run(stop_from_coroutine())
    assert not [w for w in recwarn if issubclass(w.category, RuntimeWarning)]
    k.loop.run_until_complete(asyncio.sleep(0))
    assert server.peer_closed.wait(2)


def test_tcpkiss_instances_in_threads(tnc):
    """Issue #12: two TCPKISS used from different threads at once."""
    servers = [tnc(), tnc()]
    results, errors = {}, []
    started = threading.Barrier(2)

    def work(server):
        try:
            k = TCPKISS("127.0.0.1", server.port, strip_df_start=True)
            k.start()
            started.wait(5)  # both loops exist before either reads
            try:
                results[server.port] = k.read(min_frames=1)
            finally:
                k.stop()
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(s,)) for s in servers]
    for t in threads:
        t.start()
    time.sleep(0.2)  # both threads are now blocked in read()
    for s in servers:
        s.conn.sendall(KISS_FRAME)
    for t in threads:
        t.join(10)
    assert errors == []
    assert results == {s.port: [AX25] for s in servers}


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


def test_create_connection_kwargs_are_not_modified(tnc):
    """The caller's create_connection_kwargs can be reused for a reconnect."""
    server = tnc()
    options = {"ssl": None}

    async def main():
        for _ in range(2):
            transport, _ = await kiss.create_tcp_connection(
                "127.0.0.1", server.port, create_connection_kwargs=options
            )
            transport.close()

    asyncio.run(main())
    assert options == {"ssl": None}


def test_write_before_connection_raises():
    async def main():
        protocol = kiss.KISSProtocol()
        for write in (lambda: protocol.write(AX25), protocol.kiss_on):
            with pytest.raises(ConnectionError):
                write()

    asyncio.run(main())


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


def _open_fds(path):
    fds = []
    for fd in os.listdir("/proc/self/fd"):
        with contextlib.suppress(OSError):
            if os.readlink(f"/proc/self/fd/{fd}") == path:
                fds.append(fd)
    return len(fds)


def test_serialkiss_stop_releases_port(pty_pair):
    if not os.path.isdir("/proc/self/fd"):
        pytest.skip("needs /proc to count open file descriptors")
    _, device = pty_pair
    before = _open_fds(device)
    k = SerialKISS(device, "9600", strip_df_start=True)
    k.start_no_config()
    assert _open_fds(device) == before + 1
    k.stop()
    assert _open_fds(device) == before


def test_util_helpers(sample_frames):
    # issue #21: exactly one command byte; the rest of the frame is kept
    assert util.strip_df_start(b"\x00\x00abc \r\n") == b"\x00abc \r\n"
    assert util.strip_df_start(b"abc") == b"abc"
    assert util.strip_df_start(b"") == b""
    assert util.strip_nmea(b"\xf0$GPGGA\r\n") == b"$GPGGA"
    assert util.strip_nmea(b"") == b""
    log = util.getLogger("kiss.test.helper")
    assert log is logging.getLogger("kiss.test.helper")
    assert log.handlers == []  # issue #19: no handler attached


def test_library_loggers_do_not_configure_logging():
    """Issue #19: kiss leaves handlers and levels to the application."""
    for name in ("kiss.kiss", "kiss.classes"):
        logger = logging.getLogger(name)
        assert logger.handlers == []
        assert logger.level == logging.NOTSET
    assert all(
        isinstance(h, logging.NullHandler) for h in logging.getLogger("kiss").handlers
    )


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
    class StuckTransport(asyncio.Transport):
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


# --- kiss3#32: connect_tcp / close ---


def test_connect_tcp_async_with_closes(tnc):
    server = tnc(send=KISS_FRAME)

    async def main():
        async with kiss.connect_tcp(
            "127.0.0.1", server.port, settings={"TX_TAIL": 3}
        ) as tnc_:
            frames = [f async for f in tnc_.read(n_frames=1)]
            tnc_.set_tx_delay(300)
        return frames, tnc_

    frames, protocol = asyncio.run(main())
    assert [bytes(f) for f in frames] == [AX25]
    assert protocol.transport.is_closing()
    assert server.peer_closed.wait(5)
    assert server.received == FEND + b"\x04\x03" + FEND + FEND + b"\x01\x1e" + FEND


def test_connect_tcp_await_then_close(tnc):
    server = tnc()

    async def main():
        protocol = await kiss.connect_tcp("127.0.0.1", server.port)
        protocol.write(AX25)
        await protocol.close()
        await protocol.close()  # idempotent

    asyncio.run(main())
    assert server.peer_closed.wait(5)
    assert server.received == KISS_FRAME


def test_protocol_close_before_connect_is_a_noop():
    asyncio.run(kiss.KISSProtocol().close())
