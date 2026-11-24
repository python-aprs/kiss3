"""asyncio Protocol for extracting individual KISS frames from a byte stream."""

import asyncio
import enum
import functools
import logging
from collections.abc import Awaitable, Callable, Iterable, Mapping
from typing import (
    Any,
    SupportsBytes,
    TypeVar,
    cast,
)

import serial_asyncio
from attrs import define, field
from ax253 import Frame, FrameDecodeProtocol, GenericDecoder

from . import util
from .constants import DATA_FRAME, FEND, KISS_OFF, KISS_ON

NMEA_START = b"\xf0"
# T3-Micro NMEA passthrough: 0xF0 followed by the start of a sentence. A
# bare 0xF0 command byte is a data frame on KISS port 15.
NMEA_SENTENCE_START = NMEA_START + b"$"

__author__ = "Masen Furer KF7HVM <kf7hvm@0x26.net>"
__copyright__ = "Copyright 2022 Masen Furer and Contributors"
__license__ = "Apache License, Version 2.0"


log = logging.getLogger(__name__)


# pylint: disable=duplicate-code
class Command(enum.Enum):
    """
    KISS Command Codes

    http://en.wikipedia.org/wiki/KISS_(TNC)#Command_Codes
    """

    DATA_FRAME = b"\x00"
    TX_DELAY = b"\x01"
    PERSISTENCE = b"\x02"
    SLOT_TIME = b"\x03"
    TX_TAIL = b"\x04"
    FULL_DUPLEX = b"\x05"
    SET_HARDWARE = b"\x06"
    RETURN = b"\xff"


# pylint: enable=duplicate-code


def handle_fend(buffer: bytes, strip_df_start: bool = True) -> bytes | None:
    """
    Handle FEND (end of frame) encountered in a KISS data stream.

    :param buffer: the buffer containing the frame
    :param strip_df_start: remove the leading command byte. Data frames for
        any KISS port (command byte 0x00, 0x10, ... 0xF0) are returned
        without it; frames carrying any other command (TNC parameter
        echoes, SetHardware replies, 0xFF return) are not data and return
        None.
    :return: the bytes of the frame without escape characters or frame
             end markers (FEND), or None if the frame is not a data frame
    """
    buffer = bytes(buffer)
    if buffer[:2] == NMEA_SENTENCE_START:
        # T3-Micro style NMEA passthrough
        return util._recover_special_codes(util.strip_nmea(buffer))
    frame = util._recover_special_codes(buffer)
    if strip_df_start:
        if not frame:
            return None
        if frame[0] & 0x0F != DATA_FRAME[0]:
            log.debug("Ignore non-data KISS command frame %r", frame)
            return None
        # exactly one command byte: the AX.25 frame itself may end in
        # 0x00, spaces, CR or LF, all of which are significant
        frame = frame[1:]
        if not frame:
            return None
    return frame


_T = TypeVar("_T")

# a KISS frame holds one AX.25 frame (at most a few hundred bytes, twice
# that if every byte is escaped); leave plenty of headroom
DEFAULT_MAX_BUFFERED_BYTES = 8192


@define
class GenericKISSDecode(GenericDecoder[_T]):
    """
    Generic stateful KISS framing decoder.

    Generic allows subclasses to return different types from
    decode_frame and update after further decoding the deframed KISS data.

    Direct subclassing without modification should apply `bytes` as _T
    """

    strip_df_start: bool = field(default=True)
    max_buffered_bytes: int = field(default=DEFAULT_MAX_BUFFERED_BYTES, kw_only=True)
    """
    Most bytes kept while waiting for a FEND. Past this, the buffered bytes
    are dropped up to the next FEND, so a stream with no FENDs (the wrong
    baud rate, a TNC not in KISS mode) can't grow without limit.
    """
    _last_pframe: bytes = field(default=b"", init=False)
    _discarding: bool = field(default=False, init=False, repr=False)

    def _deframe(self, frame: bytes) -> Iterable[bytes]:
        """The data frame's payload, with the KISS framing removed."""
        decoded = handle_fend(frame, strip_df_start=self.strip_df_start)
        if decoded is not None:
            yield decoded

    def decode_frames(  # pylint: disable=arguments-differ
        self,
        frame: bytes,
    ) -> Iterable[_T]:
        # the payload bytes themselves; subclasses with another _T override this
        for payload in self._deframe(frame):
            yield cast(_T, payload)

    def update(self, new_data: bytes) -> Iterable[_T]:
        if self._discarding:
            # skip the rest of an overlong run of bytes, up to the next FEND
            fend = new_data.find(FEND)
            if fend < 0:
                return
            new_data, self._discarding = new_data[fend:], False
        trail_data_from = new_data.rfind(FEND)
        if trail_data_from < 0:
            # end of frame not found, this is just a chunk
            self._last_pframe = self._last_pframe + new_data
            if len(self._last_pframe) > self.max_buffered_bytes:
                log.debug("Dropping %d bytes without a FEND", len(self._last_pframe))
                self._last_pframe, self._discarding = b"", True
            return

        # end of frame found in data:
        #   prepend previous partial frame to current data
        #   save bytes following final FEND as the next partial frame
        new_data, self._last_pframe = (
            self._last_pframe + new_data[: trail_data_from + 1],
            new_data[trail_data_from + 1 :],
        )

        for kiss_frame in filter(None, new_data.split(FEND)):
            yield from self.decode_frames(kiss_frame)

    def flush(self) -> Iterable[_T]:
        """Call when the stream is closing to decode any final buffered bytes."""
        self._discarding = False
        if self._last_pframe:
            yield from self.decode_frames(self._last_pframe)


class KISSDecode(GenericKISSDecode[bytes]):
    """
    Stateful KISS framing decoder.

    Frames are returned as bytes (with KISS framing removed).
    """


class AX25KISSDecode(GenericKISSDecode[Frame]):
    """
    Stateful AX25 framing decoder.

    Decoded frames are `ax253.Frame` objects
    """

    def decode_frames(self, frame: bytes) -> Iterable[Frame]:
        for kiss_frame in self._deframe(frame):
            try:
                yield Frame.from_bytes(kiss_frame)
            except Exception:  # pylint: disable=broad-except
                log.debug("Ignore frame AX.25 decode error %r", frame, exc_info=True)


@define
class KISSProtocol(FrameDecodeProtocol[Frame]):
    """A protocol for encoding and decoding KISS frames."""

    decoder: GenericDecoder[Frame] = field(factory=AX25KISSDecode)

    def _transport(self) -> asyncio.Transport:
        if self.transport is None:
            raise ConnectionError("not connected: the transport isn't open yet")
        return self.transport

    def write(
        self, frame: SupportsBytes | bytes, command: Command = Command.DATA_FRAME
    ) -> None:
        """
        Write the framed bytes to the transport.

        :param frame: any bytes-able object that can be sent via KISS
        :param command: kiss Command to send with the frame, default is 0x00 (DATA)
        """
        frame_escaped = util.escape_special_codes(bytes(frame))
        frame_kiss = b"".join([FEND, command.value, frame_escaped, FEND])
        self._transport().write(frame_kiss)

    def write_setting(self, name: Command, value: bytes | int) -> None:
        """
        Writes KISS Command Codes to attached device.

        http://en.wikipedia.org/wiki/KISS_(TNC)#Command_Codes

        :param name: KISS Command Code enum
        :param value: KISS Command Code Value to write.
        """
        # Do the reasonable thing if a user passes an int
        if isinstance(value, int):
            value = bytes([value])

        # write() escapes FEND/FESC; escaping here too would double-escape
        self.write(value, command=name)

    def write_settings(self, settings: Mapping[Command, bytes | int]) -> None:
        """Write a dictionary of settings."""
        for name, value in settings.items():
            self.write_setting(name, value)

    def kiss_on(self) -> None:
        """Turns KISS ON."""
        self._transport().write(KISS_ON)

    def kiss_off(self) -> None:
        """Turns KISS OFF."""
        self._transport().write(KISS_OFF)


def _handle_kwargs(
    protocol_kwargs: dict[str, Any] | None,
    create_connection_kwargs: dict[str, Any] | None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Handle async connection kwarg combination to avoid duplication."""
    # a copy: the caller's dict must not collect host/port/protocol_factory
    create_connection_kwargs = dict(create_connection_kwargs or {})
    create_connection_kwargs.update(kwargs)
    create_connection_kwargs["protocol_factory"] = functools.partial(
        create_connection_kwargs.pop("protocol_factory", KISSProtocol),
        **(protocol_kwargs or {}),
    )
    return create_connection_kwargs


async def _generic_create_connection(
    f: Callable[..., Awaitable[tuple[asyncio.Transport, KISSProtocol]]],
    args: Iterable[Any],
    kwargs: dict[str, Any],
    kiss_settings: Mapping[Command, bytes | int] | None,
) -> tuple[asyncio.Transport, KISSProtocol]:
    """Create a generic KISS connection and apply settings."""
    transport, protocol = await f(*args, **kwargs)
    # the serial transport calls connection_made() on a later loop iteration;
    # wait for it so the caller can write as soon as this returns
    await protocol.connection_future
    if kiss_settings:
        protocol.write_settings(kiss_settings)
    return transport, protocol


async def create_tcp_connection(  # pylint: disable=too-many-arguments
    host,
    port,
    protocol_kwargs: dict[str, Any] | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
    create_connection_kwargs: dict[str, Any] | None = None,
    kiss_settings: Mapping[Command, bytes | int] | None = None,
) -> tuple[asyncio.Transport, KISSProtocol]:
    """
    Establish an async KISS-over-TCP connection.

    :param host: the host to connect to
    :param port: the TCP port to connect to
    :param protocol_kwargs: These kwargs are passed directly to KISSProtocol
    :param loop: override the asyncio event loop (default: the running loop)
    :param create_connection_kwargs: These kwargs are passed directly to
        loop.create_connection
    :param kiss_settings: dictionary of (Command, bytes) pairs to send after connecting
    :return: (TCPTransport, KISSProtocol)
    """
    if loop is None:
        loop = asyncio.get_running_loop()
    return await _generic_create_connection(
        loop.create_connection,
        args=tuple(),
        kwargs=_handle_kwargs(
            protocol_kwargs=protocol_kwargs,
            create_connection_kwargs=create_connection_kwargs,
            host=host,
            port=port,
        ),
        kiss_settings=kiss_settings,
    )


async def create_serial_connection(  # pylint: disable=too-many-arguments
    port: str,
    baudrate: int,
    protocol_kwargs: dict[str, Any] | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
    create_connection_kwargs: dict[str, Any] | None = None,
    kiss_settings: Mapping[Command, bytes | int] | None = None,
) -> tuple[asyncio.Transport, KISSProtocol]:
    """
    Establish an async Serial KISS connection.

    :param port: the serial port device (platform dependent)
    :param baudrate: serial port speed
    :param protocol_kwargs: These kwargs are passed directly to KISSProtocol
    :param loop: override the asyncio event loop (default: the running loop)
    :param create_connection_kwargs: These kwargs are passed directly to
        loop.create_connection
    :param kiss_settings: dictionary of (Command, bytes) pairs to send after connecting
    :return: (SerialTransport, KISSProtocol)
    """
    if loop is None:
        loop = asyncio.get_running_loop()
    kwargs = _handle_kwargs(
        protocol_kwargs=protocol_kwargs,
        create_connection_kwargs=create_connection_kwargs,
        baudrate=baudrate,
    )
    return await _generic_create_connection(
        serial_asyncio.create_serial_connection,
        args=(loop, kwargs.pop("protocol_factory"), port),
        kwargs=kwargs,
        kiss_settings=kiss_settings,
    )
