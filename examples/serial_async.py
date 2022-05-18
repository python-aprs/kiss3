#!/usr/bin/env python3
import asyncio
import logging
import os

import kiss3
import kiss3.kiss


MYCALL = os.environ.get("MYCALL", "N0CALL")
KISS_SERIAL = os.environ.get("KISS_SERIAL", "/dev/ttyUSB0")
KISS_SPEED = os.environ.get("KISS_SPEED", "9600")


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)


async def main():
    transport, kiss_protocol = await kiss3.kiss.create_serial_connection(
        port=KISS_SERIAL,
        baudrate=int(KISS_SPEED),
    )
    async for frame in kiss_protocol.read():
        print(frame)


if __name__ == "__main__":
    asyncio.run(main())
