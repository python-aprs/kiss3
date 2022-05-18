"""asyncio Protocol for extracting individual KISS frames from a byte stream."""
import asyncio
from typing import Callable, cast, Generic, Iterable, Optional, TypeVar

from attrs import define, field

from . import util
from .ax25 import Frame
from .constants import DATA_FRAME, FEND

__author__ = "Masen Furer KF7HVM <kf7hvm@0x26.net>"
__copyright__ = "Copyright 2022 Masen Furer and Contributors"
__license__ = "Apache License, Version 2.0"


def handle_fend(
    buffer: bytes,
    strip_df_start: bool = True,
) -> bytes:
    """
    Handle FEND (end of frame) encountered in a KISS data stream.

    :param buffer: the buffer containing the frame
    :param strip_df_start: remove leading null byte (DATA_FRAME opcode)
    :return: the bytes of the frame without escape characters or frame end markers (FEND)
    """
    frame = util.recover_special_codes(util.strip_nmea(bytes(buffer)))
    if strip_df_start:
        frame = util.strip_df_start(frame)
    return bytes(frame)


_T = TypeVar("_T")


@define
class GenericDecoder(Generic[_T]):
    """Generic stateful decoder with a callback."""
    callback: Optional[Callable[[_T], None]] = field(default=None)
    _last_pframe: bytes = field(default=b"", init=False)

    @staticmethod
    def decode_frames(frame: bytes) -> Iterable[_T]:
        yield cast(_T, frame)

    def update(self, new_data: bytes) -> Iterable[_T]:
        """
        Decode the next sequence of bytes from the stream.

        :param new_data: the next bytes from the stream
        :return: an iterable of decoded frames
        """
        yield cast(_T, new_data)

    def flush(self) -> Iterable[_T]:
        if self._last_pframe:
            yield from self.decode_frames(self._last_pframe)


@define
class KISSDecode(GenericDecoder[bytes]):
    strip_df_start: bool = field(default=True)

    def decode_frames(self, frame: bytes) -> Iterable[bytes]:
        yield handle_fend(frame, strip_df_start=self.strip_df_start)

    def update(self, new_data: bytes) -> Iterable[bytes]:
        trail_data_from = new_data.rfind(FEND)
        if trail_data_from < 0:
            # end of frame not found, this is just a chunk
            self._last_pframe = self._last_pframe + new_data
            return
        else:
            # end of frame found in data:
            #   prepend previous partial frame to current data
            #   save bytes following final FEND as the next partial frame
            new_data, self._last_pframe = (
                self._last_pframe + new_data[: trail_data_from + 1],
                new_data[trail_data_from + 1 :],
            )

        for kiss_frame in filter(None, new_data.split(FEND)):
            for decoded_frame in self.decode_frames(kiss_frame):
                if self.callback is not None:
                    self.callback(decoded_frame)
                yield decoded_frame


class AX25KISSDecode(KISSDecode):
    def decode_frames(self, frame: bytes) -> Iterable[Frame]:
        for kiss_frame in super().decode_frames(frame):
            yield from Frame.from_bytes(kiss_frame)


@define
class KISSProtocol(asyncio.Protocol):
    transport: Optional[asyncio.Transport] = field(default=None)
    decoder: KISSDecode = field(factory=AX25KISSDecode)
    frames: asyncio.Queue = field(factory=asyncio.Queue, init=False)

    def connection_made(self, transport: asyncio.Transport) -> None:
        self.transport = transport

    def connection_lost(self, exc: Exception) -> None:
        for frame in self.decoder.flush():
            self.frames.put_nowait(frame)

    def data_received(self, data: bytes) -> None:
        for frame in self.decoder.update(data):
            self.frames.put_nowait(frame)

    async def read(self) -> Iterable[Frame]:
        while not self.transport.is_closing():
            yield await self.frames.get()

    def write(self, frame: bytes) -> None:
        frame_escaped = util.escape_special_codes(bytes(frame))
        frame_kiss = b"".join([FEND, DATA_FRAME, frame_escaped, FEND])
        return self.transport.write(frame_kiss)


async def create_tcp_connection(host, port, loop=None, **kwargs) :
    if loop is None:
        loop = asyncio.get_event_loop()

    return await loop.create_connection(
        protocol_factory=KISSProtocol,
        host=host,
        port=port,
        **kwargs
    )
