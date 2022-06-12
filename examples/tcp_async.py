#!/usr/bin/env python3
import asyncio
import logging
import os

from ax253 import Frame
import kiss


MYCALL = os.environ.get("MYCALL", "N0CALL")
KISS_HOST = os.environ.get("KISS_HOST", "localhost")
KISS_PORT = os.environ.get("KISS_PORT", "8001")


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)


async def main():
    transport, kiss_protocol = await kiss.create_tcp_connection(
        host=KISS_HOST,
        port=KISS_PORT,
    )
    async for frame in kiss_protocol.read():
        print(frame)
        kiss_protocol.write(
            Frame.ui(
                destination="TEST",
                source=MYCALL,
                path=[],
                info=b"RX'd frame len=%d" % len(bytes(frame)),
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
