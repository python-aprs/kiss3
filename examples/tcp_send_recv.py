#!/usr/bin/env python3
"""
Send a test frame via TCP, then read & print KISS frames from a TCP Socket.

For use with programs like Dire Wolf.

Mac OS X Tests
--------------

Soundflower, VLC & Dire Wolf as an audio-loopback-to-socket-bridge:

    1. Select "Soundflower (2ch)" as Audio Output.
    2. Play 'test_frames.wav' via VLC: `open -a vlc test_frames.wav`
    3. Startup direwolf: `direwolf "Soundflower (2ch)"`
    4. Run this script.


Dire Wolf as a raw-audio-input-to-socket-bridge:

    1. Startup direwolf: `direwolf - < test_frames.wav`
    2. Run this script.


Test output should be as follows:

    WB2OSZ-15>TEST:,The quick brown fox jumps over the lazy dog!  1 of 4
    WB2OSZ-15>TEST:,The quick brown fox jumps over the lazy dog!  2 of 4
    WB2OSZ-15>TEST:,The quick brown fox jumps over the lazy dog!  3 of 4
    WB2OSZ-15>TEST:,The quick brown fox jumps over the lazy dog!  4 of 4

"""
import os

import kiss3


MYCALL = os.environ.get("MYCALL", "N0CALL")
KISS_HOST = os.environ.get("KISS_HOST", "localhost")
KISS_PORT = os.environ.get("KISS_PORT", "8001")


def print_frame(frame):
    print(kiss3.Frame.from_ax25(frame))


def main():
    ki = kiss3.TCPKISS(host=KISS_HOST, port=int(KISS_PORT), strip_df_start=True)
    ki.start()
    frame = kiss3.Frame.ui(
        destination=kiss3.Address.from_text("PYKISS"),
        source=kiss3.Address.from_text(MYCALL),
        path=[kiss3.Address.from_text("WIDE1-1")],
        info=">Hello World!",
    )
    ki.write(frame)
    ki.read(callback=print_frame)


if __name__ == "__main__":
    main()
