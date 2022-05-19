"""asyncio Protocol for extracting individual KISS frames from a byte stream."""
import asyncio
import enum
import functools
from typing import (
    Any,
    Awaitable,
    Callable,
    cast,
    Dict,
    Generic,
    Iterable,
    Optional,
    Tuple,
    TypeVar,
    Union,
)

from attrs import define, field
import serial_asyncio

from . import util
from .ax25 import Frame
from .constants import FEND, KISS_OFF, KISS_ON

__author__ = "Masen Furer KF7HVM <kf7hvm@0x26.net>"
__copyright__ = "Copyright 2022 Masen Furer and Contributors"
__license__ = "Apache License, Version 2.0"


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
    RETURN = b"\xFF"


def handle_fend(buffer: bytes, strip_df_start: bool = True) -> bytes:
    """
    Handle FEND (end of frame) encountered in a KISS data stream.

    :param buffer: the buffer containing the frame
    :param strip_df_start: remove leading null byte (DATA_FRAME opcode)
    :return: the bytes of the frame without escape characters or frame
             end markers (FEND)
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
        if self._last_pframe:
            yield from self.decode_frames(self._last_pframe)


@define
class KISSDecode(GenericDecoder[bytes]):
    """
    Stateful KISS framing decoder.

    Decoded frames remain as raw bytes.
    """

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
    """
    Stateful AX25 framing decoder.

    Decoded frames are `kiss3.Frame` objects
    """

    def decode_frames(self, frame: bytes) -> Iterable[Frame]:
        for kiss_frame in super().decode_frames(frame):
            yield from Frame.from_bytes(kiss_frame)


@define
class KISSProtocol(asyncio.Protocol):
    """A protocol for encoding and decoding KISS frames."""

    transport: Optional[asyncio.Transport] = field(default=None)
    decoder: KISSDecode = field(factory=AX25KISSDecode)
    frames: asyncio.Queue = field(factory=asyncio.Queue, init=False)
    connection_future: asyncio.Future = field(
        factory=asyncio.Future,
        init=False,
    )

    def connection_made(self, transport: asyncio.Transport) -> None:
        """
        asyncio callback when connection is established.

        Because this protocol exposes higher-level read/write operations that
        require the transport, an awaitable `connection_future` is completed for consumers
        who depend on an active connection.
        """
        self.transport = transport
        self.connection_future.set_result(transport)

    def connection_lost(self, exc: Exception) -> None:
        """asyncio callback when connection is lost."""
        for frame in self.decoder.flush():
            self.frames.put_nowait(frame)

    def data_received(self, data: bytes) -> None:
        """Pass data off to decoder instance and put frames on the queue."""
        for frame in self.decoder.update(data):
            self.frames.put_nowait(frame)

    async def read(self, n_frames=None) -> Iterable[Frame]:
        """
        Iterate through decoded frames.

        If n_frames is specified, exit after yielding that number of frames.
        """
        if n_frames is None:
            n_frames = -1
        transport = await self.connection_future
        while not transport.is_closing() and n_frames:
            yield await self.frames.get()
            n_frames -= 1
        while not self.frames.empty() and n_frames:
            yield await self.frames.get()
            n_frames -= 1

    def write(self, frame: bytes, command: Command = Command.DATA_FRAME) -> None:
        """
        Write the framed bytes to the transport.

        :param frame: any bytes-able object that can be sent via KISS
        :param command: kiss Command to send with the frame, default is 0x00 (DATA)
        """
        frame_escaped = util.escape_special_codes(bytes(frame))
        frame_kiss = b"".join([FEND, command.value, frame_escaped, FEND])
        return self.transport.write(frame_kiss)

    def write_setting(self, name: Command, value: Union[bytes, int]) -> None:
        """
        Writes KISS Command Codes to attached device.

        http://en.wikipedia.org/wiki/KISS_(TNC)#Command_Codes

        :param name: KISS Command Code enum
        :param value: KISS Command Code Value to write.
        """
        # Do the reasonable thing if a user passes an int
        if isinstance(value, int):
            value = bytes([value])

        return self.write(
            util.escape_special_codes(value),
            command=name,
        )

    def write_settings(self, settings: Dict[Command, bytes]):
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
    protocol_kwargs: Dict[str, Any],
    create_connection_kwargs: Dict[str, Any],
    **kwargs: Any
) -> Dict[str, Any]:
    """Handle async connection kwarg combination to avoid duplication."""
    if create_connection_kwargs is None:
        create_connection_kwargs = {}
    create_connection_kwargs.update(kwargs)
    create_connection_kwargs["protocol_factory"] = functools.partial(
        create_connection_kwargs.pop("protocol_factory", KISSProtocol),
        **(protocol_kwargs or {})
    )
    return create_connection_kwargs


async def _generic_create_connection(
    f: Callable[..., Awaitable[Tuple[asyncio.Transport, KISSProtocol]]],
    args: Iterable[Any],
    kwargs: Dict[str, Any],
    kiss_settings: Dict[Command, bytes],
) -> Tuple[asyncio.Transport, KISSProtocol]:
    """Create a generic KISS connection and apply settings."""
    transport, protocol = await f(*args, **kwargs)
    if kiss_settings:
        await protocol.connection_future
        protocol.write_settings(kiss_settings)
    return transport, protocol


async def create_tcp_connection(
    host,
    port,
    protocol_kwargs: Optional[Dict[str, Any]] = None,
    loop: Optional[asyncio.BaseEventLoop] = None,
    create_connection_kwargs: Optional[Dict[str, Any]] = None,
    kiss_settings: Optional[Dict[Command, bytes]] = None,
) -> Tuple[asyncio.Transport, KISSProtocol]:
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


async def create_serial_connection(
    port: str,
    baudrate: int,
    protocol_kwargs: Optional[Dict[str, Any]] = None,
    loop: Optional[asyncio.BaseEventLoop] = None,
    create_connection_kwargs: Optional[Dict[str, Any]] = None,
    kiss_settings: Optional[Dict[Command, bytes]] = None,
) -> Tuple[asyncio.Transport, KISSProtocol]:
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
