# -*- coding: utf-8 -*-
"""Python KISS Module Utility Functions Definitions."""
import asyncio
import logging
from typing import Callable, cast, Generic, Iterable, Optional, TypeVar

from attrs import define, field

from . import constants

__author__ = "Greg Albrecht W2GMD <oss@undef.net>"  # NOQA pylint: disable=R0801
__copyright__ = (
    "Copyright 2017 Greg Albrecht and Contributors"  # NOQA pylint: disable=R0801
)
__license__ = "Apache License, Version 2.0"  # NOQA pylint: disable=R0801


# indicates that no more frames will appear on this protocol
EOF = object()


def escape_special_codes(raw_codes):
    """
    Escape special codes, per KISS spec.

    "If the FEND or FESC codes appear in the data to be transferred, they
    need to be escaped. The FEND code is then sent as FESC, TFEND and the
    FESC is then sent as FESC, TFESC."
    - http://en.wikipedia.org/wiki/KISS_(TNC)#Description
    """
    return raw_codes.replace(constants.FESC, constants.FESC_TFESC).replace(
        constants.FEND,
        constants.FESC_TFEND,
    )


def recover_special_codes(escaped_codes):
    """
    Recover special codes, per KISS spec.

    "If the FESC_TFESC or FESC_TFEND escaped codes appear in the data received,
    they need to be recovered to the original codes. The FESC_TFESC code is
    replaced by FESC code and FESC_TFEND is replaced by FEND code."
    - http://en.wikipedia.org/wiki/KISS_(TNC)#Description
    """
    out = bytearray()
    i = 0
    while i < len(escaped_codes):
        if escaped_codes[i] == constants.FESC[0] and i + 1 < len(escaped_codes):
            if escaped_codes[i + 1] == constants.TFESC[0]:
                out.append(constants.FESC[0])
                i += 1  # Skips over the next byte, which would be the TFESC
            elif escaped_codes[i + 1] == constants.TFEND[0]:
                out.append(constants.FEND[0])
                i += 1
            else:
                out.append(escaped_codes[i])
        else:
            out.append(escaped_codes[i])
        i += 1

    return out


def extract_ui(frame):
    """
    Extracts the UI component of an individual frame.

    :param frame: APRS/AX.25 frame.
    :type frame: str
    :returns: UI component of frame.
    :rtype: str
    """
    start_ui = frame.split(b"".join([constants.FEND, constants.DATA_FRAME]))
    end_ui = start_ui[0].split(
        b"".join([constants.SLOT_TIME, constants.NO_PROTOCOL_ID]),
    )
    return "".join([chr(x >> 1) for x in end_ui[0]])


def strip_df_start(frame):
    """
    Strips KISS DATA_FRAME start (0x00) and newline from frame.

    :param frame: APRS/AX.25 frame.
    :type frame: str
    :returns: APRS/AX.25 frame sans DATA_FRAME start (0x00).
    :rtype: str
    """
    return frame.lstrip(constants.DATA_FRAME).strip()


def strip_nmea(frame):
    """
    Extracts NMEA header from T3-Micro or NMEA encoded KISS frames.
    """
    if len(frame) > 0:
        if frame[0] == 240:
            return frame[1:].rstrip()
    return frame


def getLogger(name):
    """
    Get a logger hooked up with the appropriate levels and outputs.
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        logger.setLevel(constants.LOG_LEVEL)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(constants.LOG_LEVEL)
        console_handler.setFormatter(constants.LOG_FORMAT)
        logger.addHandler(console_handler)
    return logger


def valid_length(at_least, at_most=None, sequence_validator=None):
    def _validator(instance, attribute, value):
        if sequence_validator:
            sequence_validator(instance, attribute, value)
        len_value = len(value)
        if len_value < at_least:
            raise ValueError(
                "{} must be at least {} (actual={})".format(
                    attribute.name, at_least, len_value
                )
            )
        if at_most is not None and len_value > at_most:
            raise ValueError(
                "{} must be at most {} (actual={})".format(
                    attribute.name, at_most, len_value
                )
            )

    return _validator


def instance_of_or(types, other_validator):
    """check if the value is a bool or satisfies `other_validator`."""

    def _validator(instance, attribute, value):
        if not isinstance(value, types):
            other_validator(instance, attribute, value)

    return _validator


def optional_bool_or_bytes(v):
    if v is not None and not isinstance(v, bool):
        return bytes(v)
    return v


_T = TypeVar("_T")


@define
class GenericDecoder(Generic[_T]):
    """Generic stateful decoder."""

    @staticmethod
    def decode_frames(frame: bytes) -> Iterable[_T]:
        """
        Decode a single deframed byte chunk.

        :param frame: should represent a single higher level frame to
            decode in some way.
        """
        yield cast(_T, frame)

    def update(self, new_data: bytes) -> Iterable[_T]:
        """
        Decode the next sequence of bytes from the stream.

        :param new_data: the next bytes from the stream
        :return: an iterable of decoded frames
        """
        yield cast(_T, new_data)

    def flush(self) -> Iterable[_T]:
        """Call when the stream is closing to decode any final buffered bytes."""
        if None:
            yield
        return


@define
class FrameDecodeProtocol(asyncio.Protocol, Generic[_T]):
    """Protocol which uses a GenericDecoder to split the stream into frames."""

    transport: Optional[asyncio.Transport] = field(default=None)
    decoder: GenericDecoder = field(factory=GenericDecoder)
    callback: Optional[Callable[[_T], None]] = field(default=None)
    frames: asyncio.Queue = field(factory=asyncio.Queue, init=False)
    connection_future: asyncio.Future = field(
        factory=asyncio.Future,
        init=False,
    )

    def _queue_frame(self, frame: _T) -> None:
        self.frames.put_nowait(frame)
        if self.callback is not None:
            self.callback(frame)

    def connection_made(self, transport: asyncio.Transport) -> None:
        """
        asyncio callback when connection is established.

        Because this protocol exposes higher-level read/write operations that
        require the transport, an awaitable `connection_future` is completed for consumers
        who depend on an active connection.
        """
        self.transport = transport
        self.connection_future.set_result(transport)

    def data_received(self, data: bytes) -> None:
        """Pass data off to decoder instance and put frames on the queue."""
        for frame in self.decoder.update(data):
            self._queue_frame(frame)

    def connection_lost(self, exc: Exception) -> None:
        """asyncio callback when connection is lost."""
        for frame in self.decoder.flush():
            self._queue_frame(frame)
        self.frames.put_nowait(EOF)

    async def read(self, n_frames=None) -> Iterable[_T]:
        """
        Iterate through decoded frames.

        If n_frames is specified, exit after yielding that number of frames.
        """
        if n_frames is None:
            n_frames = -1
        transport = await self.connection_future
        while (not transport.is_closing() or not self.frames.empty()) and n_frames:
            frame = await self.frames.get()
            if frame is EOF:
                break
            yield frame
            n_frames -= 1

    def read_frames(
        self,
        n_frames: Optional[int],
        loop: Optional[asyncio.BaseEventLoop] = None,
    ) -> Iterable[_T]:
        """Blocking read of the given number of frames."""
        if loop is None:
            loop = asyncio.get_event_loop()

        if n_frames is not None and n_frames < 0:
            n_frames = self.frames.qsize()

        async def _():
            return [f async for f in self.read(n_frames)]

        return loop.run_until_complete(_())
