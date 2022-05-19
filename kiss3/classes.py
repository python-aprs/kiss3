#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Python KISS Module Class Definitions."""

import abc
import asyncio
from types import TracebackType
from typing import Any, Callable, List, Optional, Union, Type

from . import constants, kiss, util

__author__ = "Greg Albrecht W2GMD <oss@undef.net>"  # NOQA pylint: disable=R0801
__copyright__ = (
    "Copyright 2017 Greg Albrecht and Contributors"  # NOQA pylint: disable=R0801
)
__license__ = "Apache License, Version 2.0"  # NOQA pylint: disable=R0801


class KISS(abc.ABC):
    """KISS Object Abstract Class."""

    _logger = util.getLogger(__name__)  # pylint: disable=R0801
    _loop = None

    def __init__(self, strip_df_start: bool = False) -> None:
        self.protocol = None
        self.decoder = kiss.KISSDecode(strip_df_start=strip_df_start)

    @property
    def loop(self) -> asyncio.BaseEventLoop:
        """Get a reference to a shared event loop for this class."""
        if KISS._loop is None:
            try:
                KISS._loop = asyncio.get_running_loop()
            except RuntimeError:
                KISS._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(KISS._loop)
        return KISS._loop

    def __enter__(self) -> "KISS":
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> Optional[bool]:
        return self.stop()

    def __del__(self) -> None:
        return self.stop()

    @abc.abstractmethod
    def stop(self) -> None:
        """
        Helper method to call when stopping KISS interface.
        """

    @abc.abstractmethod
    def start(self, **kwargs: Any) -> None:
        """
        Helper method to call when starting KISS interface.
        """

    def write_setting(self, name: str, value: Union[bytes, int]) -> None:
        """
        Writes KISS Command Codes to attached device.

        http://en.wikipedia.org/wiki/KISS_(TNC)#Command_Codes

        :param name: KISS Command Code Name as a string.
        :param value: KISS Command Code Value to write.
        """
        self._logger.debug("Configuring %s=%s", name, repr(value))

        return self.protocol.write_setting(getattr(kiss.Command, name), value)

    def read(
        self,
        chunk_size: Optional[int] = None,
        callback: Optional[Callable[[bytes], Any]] = None,
        min_frames: Optional[int] = None,
    ) -> List[bytes]:  # NOQA pylint: disable=R0912
        """
        Reads data from KISS device until exhausted.

        :param chunk_size: Number of bytes to read from socket.
        :param callback: Callback to call with decoded data.
        :param min_frames: return after reading this many frames (if None,
            return after EOF is seen)
        :type chunk_size: int
        :type callback: func accepting bytes
        :type min_frames: int
        :return: List of frames
        :rtype: list
        """
        self._logger.debug(
            "read_bytes=%s callback=%s",
            chunk_size,
            callback,
        )

        self.decoder.callback = callback
        return self.protocol.read_frames(n_frames=min_frames, loop=self.loop)

    def write(self, frame: bytes) -> None:
        """
        Writes frame to KISS interface.

        :param frame: Frame to write.
        """
        self.protocol.write(frame)


class TCPKISS(KISS):

    """KISS TCP Class."""

    def __init__(self, host: str, port: int, strip_df_start: bool = False):
        super().__init__(strip_df_start)
        self.address = (host, int(port))

    def stop(self) -> None:
        self.protocol.transport.close()

    def start(self) -> None:
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


class SerialKISS(KISS):

    """KISS Serial Class."""

    def __init__(self, port: str, speed: str, strip_df_start: bool = False) -> None:
        self.port = port
        self.speed = speed
        self.strip_df_start = strip_df_start
        super(SerialKISS, self).__init__(strip_df_start)

    def _write_defaults(self, **kwargs: Any) -> None:
        """
        Previous verious defaulted to Xastir-friendly configs. Unfortunately
        those don't work with Bluetooth TNCs, so we're reverting to None.

        Use `config_xastir()` for Xastir defaults.
        """
        for k, v in kwargs.items():
            self.write_setting(k, v)

    def config_xastir(self) -> None:
        """
        Helper method to set default configuration to those that ship with
        Xastir.
        """
        self._write_defaults(**constants.DEFAULT_KISS_CONFIG_VALUES)

    def kiss_on(self) -> None:
        """Turns KISS ON."""
        self.protocol.kiss_on()

    def kiss_off(self) -> None:
        """Turns KISS OFF."""
        self.protocol.kiss_off()

    def stop(self) -> None:
        self.protocol.transport.close()

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
