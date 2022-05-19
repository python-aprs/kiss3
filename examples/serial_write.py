#!/usr/bin/env python3
"""
Send KISS frames to a Serial TNC.
"""
import os

import kiss3


MYCALL = os.environ.get("MYCALL", "N0CALL")
KISS_SERIAL = os.environ.get("KISS_SERIAL", "/dev/cu.Repleo-PL2303-00303114")
KISS_SPEED = os.environ.get("KISS_SPEED", "9600")


def main():
    frame = kiss3.Frame.ui(
        destination=kiss3.Address.from_text("PYKISS"),
        source=kiss3.Address.from_text(MYCALL),
        path=[kiss3.Address.from_text("WIDE1-1")],
        info=">Hello World!",
    )

    ki = kiss3.SerialKISS(port=KISS_SERIAL, speed=KISS_SPEED)
    ki.start()
    ki.write(frame)


if __name__ == "__main__":
    main()
