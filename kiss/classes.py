"""Python KISS Module Class Definitions."""

import asyncio
import logging
import warnings
from typing import Any, SupportsBytes, cast

from ax253 import SyncFrameDecode

from . import constants, kiss

__author__ = "Greg Albrecht W2GMD <oss@undef.net>"
__copyright__ = "Copyright 2017 Greg Albrecht and Contributors"
__license__ = "Apache License, Version 2.0"


def _loop_running_in_this_thread() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


class KISS(SyncFrameDecode):
    """KISS Object representing a TNC."""

    decode_class = kiss.KISSDecode
    _logger = logging.getLogger(__name__)

    def __init__(self, strip_df_start: bool = True) -> None:
        super().__init__()
        self.decoder = self.decode_class(strip_df_start=strip_df_start)

    @property
    def kiss_protocol(self) -> kiss.KISSProtocol:
        """The connection's protocol, for the KISS-specific writes."""
        return cast(kiss.KISSProtocol, self.protocol)

    #: seconds to wait for queued output to reach the device in write()
    drain_timeout: float = 5.0

    def _drain(self) -> None:
        """
        Run the event loop until the transport's write buffer is empty.

        asyncio transports (serial in particular) only send data while the
        event loop runs. Without this, a synchronous caller's writes sat in
        the buffer until the next read(), or were lost at exit.
        """
        transport = self.protocol.transport
        get_size = getattr(transport, "get_write_buffer_size", None)
        if transport is None or get_size is None or self.loop.is_running():
            return

        async def _wait() -> None:
            while get_size() > 0 and not transport.is_closing():
                await asyncio.sleep(0.005)

        try:
            self.loop.run_until_complete(asyncio.wait_for(_wait(), self.drain_timeout))
        except TimeoutError:
            self._logger.warning(
                "%d bytes still queued after %ss", get_size(), self.drain_timeout
            )

    def _close_transport(self) -> None:
        """
        Close the connection and let the event loop finish closing it.

        asyncio transports release the socket or serial port on the next loop
        iteration after close(). A synchronous caller's loop only runs inside
        its calls, so without this the TNC saw the connection stay open until
        the next read() or write(), or until the process exited.
        """
        if self._protocol is None or self._protocol.transport is None:
            return
        transport = self._protocol.transport
        if transport.is_closing():
            return  # already stopped (e.g. stop() and then __del__)
        transport.close()
        loop = self.loop
        if loop is None or loop.is_running() or loop.is_closed():
            return
        if _loop_running_in_this_thread():
            # e.g. stop() (or __del__) from inside a coroutine: this loop can't
            # run here, so it finishes closing the next time it runs
            return
        loop.run_until_complete(asyncio.sleep(0))

    def write(self, frame: SupportsBytes) -> None:
        """Write a frame to the TNC and wait for it to be sent."""
        self.protocol.write(frame)
        self._drain()

    def write_setting(self, name: kiss.Setting, value: bytes | int) -> None:
        """
        Writes KISS Command Codes to attached device.

        http://en.wikipedia.org/wiki/KISS_(TNC)#Command_Codes

        :param name: KISS Command Code, or its name as a string ("TX_DELAY").
        :param value: KISS Command Code Value to write.
        """
        self._logger.debug("Configuring %s=%s", name, repr(value))

        self.kiss_protocol.write_setting(name, value)
        self._drain()

    def set_tx_delay(self, ms: float) -> None:
        """Key-up delay before sending, in milliseconds (sent in 10 ms steps)."""
        self.write_setting(kiss.Command.TX_DELAY, kiss.tenths_of_10ms(ms))

    def set_persistence(self, p: int) -> None:
        """CSMA persistence, 0-255: the chance (p+1)/256 of sending in a free slot."""
        self.write_setting(kiss.Command.PERSISTENCE, p)

    def set_slot_time(self, ms: float) -> None:
        """CSMA slot time in milliseconds (sent in 10 ms steps)."""
        self.write_setting(kiss.Command.SLOT_TIME, kiss.tenths_of_10ms(ms))

    def set_tx_tail(self, ms: float) -> None:
        """Time to hold the transmitter keyed after a frame, in milliseconds."""
        self.write_setting(kiss.Command.TX_TAIL, kiss.tenths_of_10ms(ms))

    def set_full_duplex(self, on: bool) -> None:
        """Full duplex: transmit without waiting for a clear channel."""
        self.write_setting(kiss.Command.FULL_DUPLEX, bool(on))

    def _write_defaults(self, **kwargs: Any) -> None:
        """
        Previous verious defaulted to Xastir-friendly configs. Unfortunately
        those don't work with Bluetooth TNCs, so we're reverting to None.

        Use `config_xastir()` for Xastir defaults.
        """
        for k, v in kwargs.items():
            self.write_setting(k, v)


class TCPKISS(KISS):
    """KISS TCP Class."""

    def __init__(self, host: str, port: int, strip_df_start: bool = True):
        super().__init__(strip_df_start)
        self.address = (host, int(port))

    def stop(self) -> None:
        self._close_transport()

    def start(self, **kwargs: Any) -> None:
        """
        Initializes the KISS device and commits configuration.
        """
        _, self.protocol = self.loop.run_until_complete(
            kiss.create_tcp_connection(
                *self.address,
                protocol_kwargs={"decoder": self.decoder},
            ),
        )
        self.loop.run_until_complete(self.protocol.connection_future)
        self._write_defaults(**kwargs)


class SerialKISS(KISS):
    """KISS Serial Class."""

    def __init__(
        self,
        port: str,
        baudrate: int = 9600,
        strip_df_start: bool = True,
        *,
        speed: int | str | None = None,
    ) -> None:
        if speed is not None:
            warnings.warn(
                "SerialKISS(speed=...) is deprecated; use baudrate=",
                DeprecationWarning,
                stacklevel=2,
            )
            baudrate = int(speed)
        self.port = port
        self.baudrate = int(baudrate)
        super().__init__(strip_df_start)

    @property
    def speed(self) -> int:
        """Deprecated name for ``baudrate``."""
        return self.baudrate

    def config_xastir(self) -> None:
        """
        Helper method to set default configuration to those that ship with
        Xastir.
        """
        self._write_defaults(**constants.DEFAULT_KISS_CONFIG_VALUES)

    def kiss_on(self) -> None:
        """Turns KISS ON."""
        self.kiss_protocol.kiss_on()
        self._drain()

    def kiss_off(self) -> None:
        """Turns KISS OFF."""
        self.kiss_protocol.kiss_off()
        self._drain()

    def stop(self) -> None:
        self._close_transport()

    def start_no_config(self) -> None:
        """
        Initializes the KISS device without writing configuration.
        """
        _, self.protocol = self.loop.run_until_complete(
            kiss.create_serial_connection(
                port=self.port,
                baudrate=self.baudrate,
                protocol_kwargs={"decoder": self.decoder},
            ),
        )
        self.loop.run_until_complete(self.protocol.connection_future)

    def start(self, **kwargs: Any) -> None:
        """
        Initializes the KISS device and commits configuration.

        See http://en.wikipedia.org/wiki/KISS_(TNC)#Command_codes
        for configuration names.

        :param **kwargs: name/value pairs to use as initial config values.
        """
        self._logger.debug("kwargs=%s", kwargs)
        self.start_no_config()
        self._write_defaults(**kwargs)
