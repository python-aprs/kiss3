#!/usr/bin/env python3
"""
Print every frame a KISS TNC hears.

Connect to a TNC over TCP (Dire Wolf listens on port 8001) or a serial port,
and print each AX.25 frame in TNC2 text form with the time it arrived::

    $ python kiss_monitor.py --tcp localhost:8001
    14:02:11  N0CALL-9>APRS,WIDE1-1:!4610.00N/12255.00W>on the road

    $ python kiss_monitor.py --serial /dev/ttyUSB0 --baud 9600 --kiss-on

``--hex`` also prints each frame's raw AX.25 bytes, and ``--count`` stops
after a number of frames. Uses the asyncio API; see ``kiss_send.py`` for the
blocking one.
"""

import argparse
import asyncio
import datetime

import kiss


async def connect(args: argparse.Namespace):
    """Open the TNC connection; returns (transport, KISSProtocol)."""
    if args.tcp:
        host, _, port = args.tcp.rpartition(":")
        return await kiss.create_tcp_connection(host or "localhost", int(port))
    transport, protocol = await kiss.create_serial_connection(args.serial, args.baud)
    if args.kiss_on:
        protocol.kiss_on()  # for TNCs that start in command mode
    return transport, protocol


async def monitor(args: argparse.Namespace) -> None:
    transport, protocol = await connect(args)
    try:
        seen = 0
        async for frame in protocol.read():
            now = datetime.datetime.now().strftime("%H:%M:%S")
            print(f"{now}  {frame}", flush=True)
            if args.hex:
                print(f"          {bytes(frame).hex(' ')}", flush=True)
            seen += 1
            if args.count and seen >= args.count:
                break
    finally:
        transport.close()


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    via = parser.add_mutually_exclusive_group(required=True)
    via.add_argument("--tcp", metavar="HOST:PORT", help="KISS over TCP")
    via.add_argument("--serial", metavar="DEVICE", help="serial port")
    parser.add_argument("--baud", type=int, default=9600, help="serial speed")
    parser.add_argument("--kiss-on", action="store_true", help="send KISS ON first")
    parser.add_argument("--hex", action="store_true", help="also print raw bytes")
    parser.add_argument("--count", type=int, default=0, help="stop after N frames")
    return parser


def main(argv=None) -> None:
    try:
        asyncio.run(monitor(make_parser().parse_args(argv)))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
