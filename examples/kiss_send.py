#!/usr/bin/env python3
"""
Send AX.25 frames through a KISS TNC.

Give frames in TNC2 text form as arguments, or one per line on stdin::

    $ python kiss_send.py --tcp localhost:8001 'N0CALL>APRS,WIDE1-1:>on the air'
    sent N0CALL>APRS,WIDE1-1:>on the air

    $ python kiss_send.py --serial /dev/ttyUSB0 --set TX_DELAY=40 < frames.txt

``--set NAME=VALUE`` writes a KISS parameter before sending: TX_DELAY,
PERSISTENCE, SLOT_TIME and TX_TAIL take a number (TX_DELAY and SLOT_TIME
are in 10 ms units, PERSISTENCE is 0-255), FULL_DUPLEX takes 0 or 1. With
no frames, it only writes the settings. Uses the blocking API; see
``kiss_monitor.py`` for the asyncio one.
"""

import argparse
import sys

from ax253 import Frame

import kiss


def setting(text: str) -> tuple[str, int]:
    """Parse NAME=VALUE for --set."""
    name, _, value = text.partition("=")
    name = name.upper()
    if name not in kiss.Command.__members__ or name in ("DATA_FRAME", "RETURN"):
        raise argparse.ArgumentTypeError(f"unknown KISS parameter {name!r}")
    try:
        number = int(value, 0)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{name} needs a number") from None
    if not 0 <= number <= 255:
        raise argparse.ArgumentTypeError(f"{name} must be 0-255")
    return name, number


def open_tnc(args: argparse.Namespace) -> kiss.TCPKISS | kiss.SerialKISS:
    """A started TNC connection with the requested settings written."""
    if args.tcp:
        host, _, port = args.tcp.rpartition(":")
        tnc = kiss.TCPKISS(host or "localhost", int(port))
        tnc.start()
    else:
        tnc = kiss.SerialKISS(args.serial, baudrate=args.baud)
        tnc.start_no_config()
        if args.kiss_on:
            tnc.kiss_on()
    for name, value in args.set:
        tnc.write_setting(name, value)
    return tnc


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("frames", nargs="*", help="TNC2 frames (default: stdin)")
    via = parser.add_mutually_exclusive_group(required=True)
    via.add_argument("--tcp", metavar="HOST:PORT", help="KISS over TCP")
    via.add_argument("--serial", metavar="DEVICE", help="serial port")
    parser.add_argument("--baud", type=int, default=9600, help="serial speed")
    parser.add_argument("--kiss-on", action="store_true", help="send KISS ON first")
    parser.add_argument(
        "--set", type=setting, action="append", default=[], metavar="NAME=VALUE"
    )
    args = parser.parse_args(argv)
    if args.frames:
        lines = args.frames
    elif args.set and sys.stdin.isatty():
        lines = []  # just configure the TNC
    else:
        lines = sys.stdin
    # parse everything first so a typo doesn't leave half the frames sent
    frames = [Frame.from_str(line.strip()) for line in lines if line.strip()]

    tnc = open_tnc(args)
    try:
        for frame in frames:
            tnc.write(frame)  # returns once the bytes have gone out
            print(f"sent {frame}", flush=True)
    finally:
        tnc.stop()


if __name__ == "__main__":
    main()
