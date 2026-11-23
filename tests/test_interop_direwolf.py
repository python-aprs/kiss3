"""
Interop with Dire Wolf's KISS TCP interface.

direwolf_kiss_tcp.bin is the exact byte stream Dire Wolf 1.7 sent to a KISS
TCP client while receiving the packets in ax25_frames.json over (simulated)
radio; see tests/fixtures/direwolf/generate.py. The ``live`` tests talk to
a real ``direwolf`` process and are skipped when it is not installed.
"""

import asyncio
import json
import pathlib
import queue
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time

import pytest
from ax253 import Frame

from kiss import kiss, util
from kiss.constants import DATA_FRAME, FEND

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "direwolf"
CORPUS = json.loads((FIXTURES / "ax25_frames.json").read_text())
AX25 = [bytes.fromhex(f["ax25"]) for f in CORPUS["frames"]]
STREAM = (FIXTURES / "direwolf_kiss_tcp.bin").read_bytes()
DW_HEX_ESCAPE = re.compile(r"<0x([0-9a-f]{2})>")


def _decode(decoder, data, chunk_size=None):
    chunk_size = chunk_size or len(data) or 1
    frames = []
    for start in range(0, len(data), chunk_size):
        frames.extend(decoder.update(data[start : start + chunk_size]))
    frames.extend(decoder.flush())
    return frames


def test_fixture_shape():
    assert len(AX25) >= 38
    assert STREAM.startswith(FEND + DATA_FRAME)
    assert STREAM.endswith(FEND)
    assert b"\xdb\xdc" in STREAM and b"\xdb\xdd" in STREAM  # escapes present


@pytest.mark.parametrize("chunk_size", [None, 1, 2, 3, 5, 17, 64, 256])
def test_decode_direwolf_stream_exact_bytes(chunk_size):
    """Every frame Dire Wolf sent, byte for byte, however the stream is chunked."""
    frames = _decode(kiss.KISSDecode(strip_df_start=True), STREAM, chunk_size)
    assert frames == AX25


def test_decode_direwolf_stream_raw_keeps_command_byte():
    frames = _decode(kiss.KISSDecode(strip_df_start=False), STREAM)
    assert frames == [DATA_FRAME + f for f in AX25]


def test_decode_direwolf_stream_ax25():
    frames = _decode(kiss.AX25KISSDecode(), STREAM)
    assert [f.info for f in frames] == [Frame.from_bytes(raw).info for raw in AX25]


def test_trailing_whitespace_in_info_preserved():
    """Info fields ending in a space must not be stripped (APRS messages do)."""
    trailing = [raw for raw in AX25 if raw.endswith(b" ")]
    assert trailing, "corpus should contain a frame ending in a space"
    assert set(trailing) <= set(_decode(kiss.KISSDecode(strip_df_start=True), STREAM))


def test_encode_matches_direwolf_framing():
    """kiss3's KISS encoding of each frame is exactly what Dire Wolf sends."""
    encoded = b"".join(
        FEND + DATA_FRAME + util.escape_special_codes(raw) + FEND for raw in AX25
    )
    assert encoded == STREAM


def test_protocol_write_matches_direwolf_framing():
    written = []

    class Transport(asyncio.Transport):
        def write(self, data):
            written.append(data)

    protocol = kiss.KISSProtocol()
    protocol.transport = Transport()
    for raw in AX25:
        protocol.write(raw)
    assert b"".join(written) == STREAM


# --- live tests against a real direwolf process --------------------------

direwolf = pytest.mark.skipif(
    not shutil.which("direwolf"), reason="direwolf is not installed"
)


def _free_port():
    """A free port Dire Wolf accepts (it rejects ports above 49151)."""
    import random

    for _ in range(100):
        port = random.randint(20000, 49151)
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("no free port")


@pytest.fixture
def direwolf_kiss():
    """Start direwolf with null audio and a KISS TCP port; yield (port, proc)."""
    port = _free_port()
    with tempfile.TemporaryDirectory() as tmp:
        conf = pathlib.Path(tmp) / "direwolf.conf"
        conf.write_text(
            "ADEVICE stdin null\nARATE 44100\nCHANNEL 0\nMYCALL N0CALL\n"
            f"MODEM 1200\nKISSPORT 0\nKISSPORT {port}\nAGWPORT 0\n"
        )
        proc = subprocess.Popen(
            ["direwolf", "-c", str(conf), "-t", "0", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        try:
            yield port, proc
        finally:
            if proc.poll() is None:
                assert proc.stdin is not None
                proc.stdin.close()
                proc.terminate()
                proc.wait(10)


def _connect(port, proc):
    # Dire Wolf pauses for several seconds at startup when run as root
    for _ in range(300):
        try:
            return socket.create_connection(("127.0.0.1", port))
        except OSError:
            if proc.poll() is not None:
                raise RuntimeError(
                    "direwolf exited: " + proc.stdout.read().decode("latin1")
                ) from None
            time.sleep(0.1)
    proc.terminate()
    raise RuntimeError(
        "direwolf KISS port did not open: " + proc.stdout.read().decode("latin1")[-600:]
    )


def _dw_text(text):
    return DW_HEX_ESCAPE.sub(lambda m: chr(int(m.group(1), 16)), text)


@direwolf
def test_live_direwolf_transmits_kiss3_frames(direwolf_kiss):
    """
    Frames written with kiss3 are accepted by Dire Wolf and transmitted
    unchanged. Dire Wolf logs each transmission as "[0L] <monitor text>"
    ("[0H]" for frames that were already digipeated).
    """
    port, proc = direwolf_kiss
    client = _connect(port, proc)
    protocol = kiss.KISSProtocol()

    class Transport(asyncio.Transport):
        def write(self, data):
            client.sendall(data)

    protocol.transport = Transport()
    for raw in AX25:
        protocol.write(raw)

    transmitted = []
    lines = queue.Queue()
    threading.Thread(
        target=lambda: [lines.put(line) for line in proc.stdout], daemon=True
    ).start()
    deadline = time.time() + 120  # Dire Wolf paces transmissions in real time
    while len(transmitted) < len(AX25) and time.time() < deadline:
        try:
            line = lines.get(timeout=1).decode("latin1").rstrip("\r\n")
        except queue.Empty:
            continue
        if line[:5] in ("[0L] ", "[0H] "):
            transmitted.append(_dw_text(line[5:]))
    client.close()
    # Dire Wolf sends already-digipeated ([0H]) frames ahead of the rest
    assert sorted(transmitted) == sorted(
        _dw_text(f["direwolf_monitor"]) for f in CORPUS["frames"]
    )
