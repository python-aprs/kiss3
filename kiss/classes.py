"""Python KISS Module Class Definitions."""

import asyncio
from typing import Any, SupportsBytes

from ax253 import SyncFrameDecode

from . import constants, kiss, util

__author__ = "Greg Albrecht W2GMD <oss@undef.net>"
__copyright__ = "Copyright 2017 Greg Albrecht and Contributors"
__license__ = "Apache License, Version 2.0"


class KISS(SyncFrameDecode):
    """KISS Object representing a TNC."""

    decode_class = kiss.KISSDecode
    _logger = util.getLogger(__name__)

    def __init__(self, strip_df_start: bool = False) -> None:
        super().__init__()
        self.decoder = self.decode_class(strip_df_start=strip_df_start)

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
        if get_size is None or self.loop.is_running():
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

    def write(self, frame: SupportsBytes) -> None:
        """Write a frame to the TNC and wait for it to be sent."""
        self.protocol.write(frame)
        self._drain()

    def write_setting(self, name: str, value: bytes | int) -> None:
        """
        Writes KISS Command Codes to attached device.

        http://en.wikipedia.org/wiki/KISS_(TNC)#Command_Codes

        :param name: KISS Command Code Name as a string.
        :param value: KISS Command Code Value to write.
        """
        self._logger.debug("Configuring %s=%s", name, repr(value))

        self.protocol.write_setting(getattr(kiss.Command, name), value)
        self._drain()

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

    def __init__(self, host: str, port: int, strip_df_start: bool = False):
        super().__init__(strip_df_start)
        self.address = (host, int(port))

    def stop(self) -> None:
        if self._protocol is not None and self._protocol.transport is not None:
            self._protocol.transport.close()

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

    def __init__(self, port: str, speed: str, strip_df_start: bool = False) -> None:
        self.port = port
        self.speed = speed
        super().__init__(strip_df_start)

    def config_xastir(self) -> None:
        """
        Helper method to set default configuration to those that ship with
        Xastir.
        """
        self._write_defaults(**constants.DEFAULT_KISS_CONFIG_VALUES)

    def kiss_on(self) -> None:
        """Turns KISS ON."""
        self.protocol.kiss_on()
        self._drain()

    def kiss_off(self) -> None:
        """Turns KISS OFF."""
        self.protocol.kiss_off()
        self._drain()

    def stop(self) -> None:
        if self._protocol is not None and self._protocol.transport is not None:
            self._protocol.transport.close()

    def start_no_config(self) -> None:
        """
        Initializes the KISS device without writing configuration.
        """
        _, self.protocol = self.loop.run_until_complete(
            kiss.create_serial_connection(
                port=self.port,
                baudrate=int(self.speed),
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
