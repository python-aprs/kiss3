"""asyncio Protocol for extracting individual frames from CRLF-delimited TNC2."""
import asyncio
import functools
from typing import (
    Any,
    Dict,
    Iterable,
    Optional,
    Tuple,
)

from attrs import define, field

from . import __distribution__, __version__
from .ax25 import Frame
from .util import FrameDecodeProtocol, GenericDecoder, getLogger

__author__ = "Masen Furer KF7HVM <kf7hvm@0x26.net>"
__copyright__ = "Copyright 2022 Masen Furer and Contributors"
__license__ = "Apache License, Version 2.0"


log = getLogger(__name__)


@define
class TNC2Decode(GenericDecoder[Frame]):
    """
    Decode packets in CR-LF delimited TNC2 monitor format.

    Example: SENDER>DEST,PATH:data for the packet
    """

    @staticmethod
    def decode_frames(frame: bytes) -> Iterable[Frame]:
        try:
            yield Frame.from_str(frame.decode("latin1"))
        except Exception:
            log.debug("Ignore frame decode error %r", frame, exc_info=True)

    def update(self, new_data: bytes) -> Iterable[Frame]:
        packets = new_data.splitlines()
        for packet in packets:
            if packet.strip().startswith(b"#"):
                continue
            yield from self.decode_frames(packet)


@define
class TNC2Protocol(FrameDecodeProtocol[Frame]):
    """Protocol for decoding a stream of TNC2 format packets."""

    decoder: GenericDecoder = field(factory=TNC2Decode)

    def write(self, frame: Frame) -> None:
        """Write the Frame to the transport."""
        return self.transport.write(str(frame).encode("latin1") + b"\r\n")


@define
class APRSISProtocol(TNC2Protocol):
    """Protocol for logging into APRS-IS servers (TNC2)."""

    def login(self, user: str, passcode: str, command: str):
        self.transport.write(
            "user {} pass {} vers {} {} {}\r\n".format(
                user,
                passcode,
                __distribution__,
                __version__,
                command,
            ).encode("ascii"),
        )


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
        create_connection_kwargs.pop("protocol_factory", APRSISProtocol),
        **(protocol_kwargs or {}),
    )
    return create_connection_kwargs


async def create_aprsis_connection(
    host: str,
    port: int,
    user: str,
    passcode: str = "-1",
    command: str = "",
    protocol_kwargs: Optional[Dict[str, Any]] = None,
    loop: Optional[asyncio.BaseEventLoop] = None,
    create_connection_kwargs: Optional[Dict[str, Any]] = None,
) -> Tuple[asyncio.BaseTransport, APRSISProtocol]:
    """
    Establish an async APRS-IS connection.

    :param host: the APRS-IS host to connect to
    :param port: the TCP port to connect to (14580 is usually a good choice)
    :param user: callsign of the user to authenticate
    :param passcode: APRS-IS passcode associated with the callsign
    :param command: initial command to send after connecting
    :param protocol_kwargs: These kwargs are passed directly to APRSISProtocol
    :param loop: override the asyncio event loop (default calls `get_event_loop()`)
    :param create_connection_kwargs: These kwargs are passed directly to
        loop.create_connection
    :return: (TCPTransport, APRSISProtocol)
    """
    if loop is None:
        loop = asyncio.get_event_loop()
    protocol: APRSISProtocol
    transport, protocol = await loop.create_connection(
        host=host,
        port=port,
        **_handle_kwargs(
            protocol_kwargs=protocol_kwargs,
            create_connection_kwargs=create_connection_kwargs,
        ),
    )
    await protocol.connection_future
    protocol.login(user, passcode, command)
    return transport, protocol
