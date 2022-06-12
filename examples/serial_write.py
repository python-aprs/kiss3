#!/usr/bin/env python3
"""
Send KISS frames to a Serial TNC.
"""
import os

from ax253 import Frame
import kiss


MYCALL = os.environ.get("MYCALL", "N0CALL")
KISS_SERIAL = os.environ.get("KISS_SERIAL", "/dev/cu.Repleo-PL2303-00303114")
KISS_SPEED = os.environ.get("KISS_SPEED", "9600")


def main():
    frame = Frame.ui(
        destination="PYKISS",
        source=MYCALL,
        path=["WIDE1-1"],
        info=">Hello World!",
    )

    ki = kiss.SerialKISS(port=KISS_SERIAL, speed=KISS_SPEED)
    ki.start()
    ki.write(frame)


if __name__ == "__main__":
    main()
