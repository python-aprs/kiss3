#!/usr/bin/env python3
import asyncio
import logging
import os

import kiss3
import kiss3.kiss


MYCALL = os.environ.get("MYCALL", "N0CALL")
KISS_HOST = os.environ.get("KISS_HOST", "localhost")
KISS_PORT = os.environ.get("KISS_PORT", "8001")
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)


async def from_ax25(transport, kiss_protocol):
    while not transport.is_closing():
        try:
            kiss_frame = await kiss_protocol.frames.get()
        except Exception:
            transport.close()
            raise
        try:
            yield kiss3.Frame.from_ax25(kiss_frame)
        except Exception:
            logger.info("AX.25 decode error: {!r}".format(kiss_frame), exc_info=True)


async def main():
    loop = asyncio.get_event_loop()
    transport, kiss_protocol = await loop.create_connection(
        protocol_factory=kiss3.kiss.KISSProtocol,
        host=KISS_HOST,
        port=KISS_PORT,
    )
    async for ax25_frames in from_ax25(transport, kiss_protocol):
        for frame in ax25_frames:
            print(frame)
            kiss_protocol.write(
                kiss3.Frame.ui(
                    destination="TEST",
                    source=MYCALL,
                    path=[],
                    info=b"RX'd frame len=%d" % len(bytes(frame)),
                )
            )


if __name__ == "__main__":
    asyncio.run(main())
