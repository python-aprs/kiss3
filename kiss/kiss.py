"""asyncio Protocol for extracting individual KISS frames from a byte stream."""

import asyncio
import dataclasses
import enum
import functools
from collections.abc import Awaitable, Callable, Iterable
from typing import (
    Any,
    TypeVar,
)

import serial_asyncio
from ax253 import Frame, FrameDecodeProtocol, GenericDecoder

from . import util
from .constants import DATA_FRAME, FEND, KISS_OFF, KISS_ON

NMEA_START = b"\xf0"

__author__ = "Masen Furer KF7HVM <kf7hvm@0x26.net>"
__copyright__ = "Copyright 2022 Masen Furer and Contributors"
__license__ = "Apache License, Version 2.0"


log = util.getLogger(__name__)


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
    if buffer[:1] == NMEA_START:
        # T3-Micro style NMEA passthrough
        return bytes(util.recover_special_codes(util.strip_nmea(buffer)))
    frame = bytes(util.recover_special_codes(buffer))
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


@dataclasses.dataclass(slots=True)
class GenericKISSDecode(GenericDecoder[_T]):
    """
    Generic stateful KISS framing decoder.

    Generic allows subclasses to return different types from
    decode_frame and update after further decoding the deframed KISS data.

    Direct subclassing without modification should apply `bytes` as _T
    """

    strip_df_start: bool = True
    _last_pframe: bytes = dataclasses.field(default=b"", init=False, repr=False)

    def decode_frames(  # pylint: disable=arguments-differ
        self,
        frame: bytes,
    ) -> Iterable[_T]:
        decoded = handle_fend(frame, strip_df_start=self.strip_df_start)
        if decoded is not None:
            yield decoded

    def update(self, new_data: bytes) -> Iterable[_T]:
        trail_data_from = new_data.rfind(FEND)
        if trail_data_from < 0:
            # end of frame not found, this is just a chunk
            self._last_pframe = self._last_pframe + new_data
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

    def flush(self) -> Iterable[Frame]:
        """Call when the stream is closing to decode any final buffered bytes."""
        if self._last_pframe:
            yield from self.decode_frames(self._last_pframe)


@dataclasses.dataclass(slots=True)
class KISSDecode(GenericKISSDecode[bytes]):
    """
    Stateful KISS framing decoder.

    Frames are returned as bytes (with KISS framing removed).
    """


@dataclasses.dataclass(slots=True)
class AX25KISSDecode(GenericKISSDecode[Frame]):
    """
    Stateful AX25 framing decoder.

    Decoded frames are `ax253.Frame` objects
    """

    def decode_frames(self, frame: bytes) -> Iterable[Frame]:
        # explicit super(): slots=True dataclasses break the zero-argument form
        # before Python 3.14
        for kiss_frame in super(AX25KISSDecode, self).decode_frames(frame):
            try:
                yield Frame.from_bytes(kiss_frame)
            except Exception:  # pylint: disable=broad-except
                log.debug("Ignore frame AX.25 decode error %r", frame, exc_info=True)


@dataclasses.dataclass(slots=True)
class KISSProtocol(FrameDecodeProtocol[Frame]):
    """A protocol for encoding and decoding KISS frames."""

    decoder: AX25KISSDecode = dataclasses.field(default_factory=AX25KISSDecode)

    def write(self, frame: bytes, command: Command = Command.DATA_FRAME) -> None:
        """
        Write the framed bytes to the transport.

        :param frame: any bytes-able object that can be sent via KISS
        :param command: kiss Command to send with the frame, default is 0x00 (DATA)
        """
        frame_escaped = util.escape_special_codes(bytes(frame))
        frame_kiss = b"".join([FEND, command.value, frame_escaped, FEND])
        return self.transport.write(frame_kiss)

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
        return self.write(value, command=name)

    def write_settings(self, settings: dict[Command, bytes]):
        """Write a dictionary of settings."""
        for name, value in settings.items():
            self.write_setting(name, value)

    def kiss_on(self) -> None:
        """Turns KISS ON."""
        self.transport.write(KISS_ON)

    def kiss_off(self) -> None:
        """Turns KISS OFF."""
        self.transport.write(KISS_OFF)


def _handle_kwargs(
    protocol_kwargs: dict[str, Any],
    create_connection_kwargs: dict[str, Any],
    **kwargs: Any,
) -> dict[str, Any]:
    """Handle async connection kwarg combination to avoid duplication."""
    if create_connection_kwargs is None:
        create_connection_kwargs = {}
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
    kiss_settings: dict[Command, bytes],
) -> tuple[asyncio.Transport, KISSProtocol]:
    """Create a generic KISS connection and apply settings."""
    transport, protocol = await f(*args, **kwargs)
    if kiss_settings:
        await protocol.connection_future
        protocol.write_settings(kiss_settings)
    return transport, protocol


async def create_tcp_connection(  # pylint: disable=too-many-arguments
    host,
    port,
    protocol_kwargs: dict[str, Any] | None = None,
    loop: asyncio.BaseEventLoop | None = None,
    create_connection_kwargs: dict[str, Any] | None = None,
    kiss_settings: dict[Command, bytes] | None = None,
) -> tuple[asyncio.Transport, KISSProtocol]:
    """
    Establish an async KISS-over-TCP connection.

    :param host: the host to connect to
    :param port: the TCP port to connect to
    :param protocol_kwargs: These kwargs are passed directly to KISSProtocol
    :param loop: override the asyncio event loop (default calls `get_event_loop()`)
    :param create_connection_kwargs: These kwargs are passed directly to
        loop.create_connection
    :param kiss_settings: dictionary of (Command, bytes) pairs to send after connecting
    :return: (TCPTransport, KISSProtocol)
    """
    if loop is None:
        loop = asyncio.get_event_loop()
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
    loop: asyncio.BaseEventLoop | None = None,
    create_connection_kwargs: dict[str, Any] | None = None,
    kiss_settings: dict[Command, bytes] | None = None,
) -> tuple[asyncio.Transport, KISSProtocol]:
    """
    Establish an async Serial KISS connection.

    :param port: the serial port device (platform dependent)
    :param baudrate: serial port speed
    :param protocol_kwargs: These kwargs are passed directly to KISSProtocol
    :param loop: override the asyncio event loop (default calls `get_event_loop()`)
    :param create_connection_kwargs: These kwargs are passed directly to
        loop.create_connection
    :param kiss_settings: dictionary of (Command, bytes) pairs to send after connecting
    :return: (SerialTransport, KISSProtocol)
    """
    if loop is None:
        loop = asyncio.get_event_loop()
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
