#!/usr/bin/env python3
"""
Regenerate direwolf_kiss_tcp.bin: the raw KISS-over-TCP byte stream that a
Dire Wolf TNC sends to a client while receiving the packets in
ax25_frames.json.

Each packet is modulated with Dire Wolf's ``gen_packets``, the audio is
concatenated and piped into ``direwolf`` (``ADEVICE stdin null``), and a TCP
client records everything Dire Wolf writes on its KISS port.

ax25_frames.json is copied from the ax253 repository
(tests/fixtures/direwolf/direwolf_frames.json); its ``ax25`` field holds
the AX.25 bytes Dire Wolf produces for each packet.

Requires ``direwolf`` and ``gen_packets`` on PATH (``apt install direwolf``).
"""

import json
import pathlib
import socket
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).parent
KISS_PORT = 18001
WAV_HEADER = 44
SAMPLE_RATE = 44100


def main() -> int:
    corpus = json.loads((HERE / "ax25_frames.json").read_text())
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = pathlib.Path(tmp_name)
        audio = bytearray()
        for ix, frame in enumerate(corpus["frames"]):
            txt, wav = tmp / "p.txt", tmp / f"p{ix}.wav"
            txt.write_bytes(frame["input"].encode("latin1"))  # no newline
            subprocess.run(
                ["gen_packets", "-o", str(wav), str(txt)], check=True, capture_output=True
            )
            audio += wav.read_bytes()[WAV_HEADER:]
        audio += b"\0" * SAMPLE_RATE * 2  # one second of silence to flush
        conf = tmp / "direwolf.conf"
        conf.write_text(
            f"ADEVICE stdin null\nARATE {SAMPLE_RATE}\nCHANNEL 0\nMYCALL N0CALL\n"
            f"MODEM 1200\nKISSPORT 0\nKISSPORT {KISS_PORT}\nAGWPORT 0\n"
        )
        dw = subprocess.Popen(
            ["direwolf", "-c", str(conf), "-t", "0", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            for _ in range(300):  # slow startup when run as root
                try:
                    client = socket.create_connection(("127.0.0.1", KISS_PORT))
                    break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError("Dire Wolf KISS port did not open")
            time.sleep(0.5)
            assert dw.stdin is not None
            dw.stdin.write(bytes(audio))
            dw.stdin.flush()
            client.settimeout(0.5)
            stream = b""
            deadline = time.time() + 10
            while time.time() < deadline:
                try:
                    data = client.recv(65536)
                except TimeoutError:
                    if stream.count(b"\xc0") >= 2 * len(corpus["frames"]):
                        break
                    continue
                if not data:
                    break
                stream += data
        finally:
            if dw.stdin is not None:
                dw.stdin.close()
            dw.wait(10)
    (HERE / "direwolf_kiss_tcp.bin").write_bytes(stream)
    print(f"wrote {len(stream)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
