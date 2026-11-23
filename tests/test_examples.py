"""The scripts in examples/ run and print what their docstrings say."""

import asyncio
import os
import pathlib
import sys

import pytest
from ax253 import Frame

from kiss.constants import FEND, KISS_ON

from .test_transports import TNCServer, _read_fd, pty_pair  # noqa: F401

EXAMPLES = pathlib.Path(__file__).parent.parent / "examples"
sys.path.insert(0, str(EXAMPLES))

import kiss_monitor  # noqa: E402
import kiss_send  # noqa: E402

TNC2 = "N0CALL>APRS,WIDE1-1:>on the air"
AX25 = bytes(Frame.from_str(TNC2))
KISS_FRAME = FEND + b"\x00" + AX25 + FEND


def test_send_over_tcp(capsys):
    server = TNCServer()
    try:
        kiss_send.main(
            ["--tcp", f"127.0.0.1:{server.port}", "--set", "tx_delay=40", TNC2]
        )
        expected = FEND + b"\x01\x28" + FEND + KISS_FRAME
        assert server.wait_for(len(expected)) == expected
        assert server.peer_closed.wait(2)
    finally:
        server.close()
    assert capsys.readouterr().out.strip() == f"sent {TNC2}"
    assert f"sent {TNC2}" in (kiss_send.__doc__ or "")


def test_send_over_serial(pty_pair, capsys):  # noqa: F811
    controller, device = pty_pair
    kiss_send.main(["--serial", device, "--kiss-on", "--set", "PERSISTENCE=0x3f", TNC2])
    expected = KISS_ON + FEND + b"\x02\x3f" + FEND + KISS_FRAME
    assert _read_fd(controller, len(expected)) == expected


@pytest.mark.parametrize(
    "arg, message",
    [
        ("DATA_FRAME=1", "unknown"),
        ("BOGUS=1", "unknown"),
        ("TX_DELAY=x", "needs a number"),
        ("TX_DELAY=256", "0-255"),
    ],
)
def test_send_rejects_bad_settings(arg, message, capsys):
    with pytest.raises(SystemExit):
        kiss_send.main(["--tcp", "localhost:1", "--set", arg, TNC2])
    assert message in capsys.readouterr().err


def test_monitor_over_tcp(capsys):
    server = TNCServer(send=KISS_FRAME[:9])  # a partial frame first
    args = kiss_monitor.make_parser().parse_args(
        ["--tcp", f"127.0.0.1:{server.port}", "--hex", "--count", "2"]
    )

    async def run():
        task = asyncio.ensure_future(kiss_monitor.monitor(args))
        await asyncio.sleep(0.1)
        assert server.conn is not None
        server.conn.sendall(KISS_FRAME[9:] + KISS_FRAME)
        await asyncio.wait_for(task, 5)

    try:
        asyncio.run(run())
        assert server.peer_closed.wait(2)
    finally:
        server.close()
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 4
    assert lines[0][8:] == f"  {TNC2}"
    assert lines[1].strip() == AX25.hex(" ")
    assert lines[2][8:] == f"  {TNC2}"


def test_monitor_over_serial(pty_pair, capsys):  # noqa: F811
    controller, device = pty_pair
    args = kiss_monitor.make_parser().parse_args(
        ["--serial", device, "--kiss-on", "--count", "1"]
    )

    async def run():
        task = asyncio.ensure_future(kiss_monitor.monitor(args))
        await asyncio.sleep(0.1)
        os.write(controller, KISS_FRAME)
        await asyncio.wait_for(task, 5)

    asyncio.run(run())
    assert _read_fd(controller, len(KISS_ON)) == KISS_ON
    assert capsys.readouterr().out.strip()[8:] == f"  {TNC2}"
