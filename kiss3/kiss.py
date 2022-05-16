"""asyncio Protocol for extracting individual KISS frames from a byte stream."""
import asyncio
from typing import Callable, Optional

from attrs import define, field

from . import DATA_FRAME, FEND
from . import util

__author__ = "Masen Furer KF7HVM <kf7hvm@0x26.net>"
__copyright__ = "Copyright 2022 Masen Furer and Contributors"
__license__ = "Apache License, Version 2.0"


def handle_fend(
    buffer: bytes,
    callback: Optional[Callable[[bytes], None]] = None,
    strip_df_start: bool = True,
) -> bytes:
    """
    Handle FEND (end of frame) encountered in a KISS data stream.

    :param buffer: the buffer containing the frame
    :param callback: optional function to call, passing the frame bytes
    :param strip_df_start: remove leading null byte (DATA_FRAME opcode)
    :return: the bytes of the frame without escape characters or frame end markers (FEND)
    """
    frame = util.recover_special_codes(util.strip_nmea(bytes(buffer)))
    if strip_df_start:
        frame = util.strip_df_start(frame)
    if callback is not None:
        callback(frame)
    return frame


@define
class KISSProtocol(asyncio.Protocol):
    transport: Optional[asyncio.Transport] = field(default=None)
    callback: Optional[Callable[[bytes], None]] = field(default=None)
    strip_df_start: bool = field(default=True)
    frames: asyncio.Queue = field(factory=asyncio.Queue, init=False)
    last_pframe: bytes = field(default=b"", init=False)

    def connection_made(self, transport: asyncio.Transport) -> None:
        self.transport = transport

    def data_received(self, data: bytes) -> None:
        trail_data_from = data.rfind(FEND)
        if trail_data_from < 0:
            # end of frame not found, this is just a chunk
            self.last_pframe = self.last_pframe + data
            return
        else:
            # end of frame found in data:
            #   prepend previous partial frame to current data
            #   save bytes following final FEND as the next partial frame
            data, self.last_pframe = (
                self.last_pframe + data[: trail_data_from + 1],
                data[trail_data_from + 1 :],
            )

        for frame in filter(None, data.split(FEND)):
            self.frames.put_nowait(
                handle_fend(
                    frame,
                    callback=self.callback,
                    strip_df_start=self.strip_df_start,
                ),
            ),

    def write(self, frame: bytes) -> None:
        frame_escaped = util.escape_special_codes(bytes(frame))
        frame_kiss = b"".join([FEND, DATA_FRAME, frame_escaped, FEND])
        return self.transport.write(frame_kiss)
