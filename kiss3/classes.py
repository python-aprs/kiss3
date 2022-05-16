#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Python KISS Module Class Definitions."""

import abc
import socket
from types import TracebackType
from typing import Any, Callable, Iterable, List, Optional, Union, Type

import serial

from . import constants, exceptions, util

__author__ = "Greg Albrecht W2GMD <oss@undef.net>"  # NOQA pylint: disable=R0801
__copyright__ = (
    "Copyright 2017 Greg Albrecht and Contributors"  # NOQA pylint: disable=R0801
)
__license__ = "Apache License, Version 2.0"  # NOQA pylint: disable=R0801


class KISS(abc.ABC):
    """KISS Object Abstract Class."""

    _logger = util.getLogger(__name__)  # pylint: disable=R0801

    def __init__(self, strip_df_start: bool = False) -> None:
        self.strip_df_start = strip_df_start
        self.interface = None

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
    def _read_handler(self, read_bytes: Optional[int] = None) -> bytes:
        """
        Helper method to call when reading from KISS interface.
        """

    @abc.abstractmethod
    def _write_handler(self, frame: Optional[bytes] = None) -> int:
        """
        Helper method to call when writing to KISS interface.
        """

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

    def write_setting(self, name: str, value: Union[bytes, int]) -> int:
        """
        Writes KISS Command Codes to attached device.

        http://en.wikipedia.org/wiki/KISS_(TNC)#Command_Codes

        :param name: KISS Command Code Name as a string.
        :param value: KISS Command Code Value to write.
        """
        self._logger.debug("Configuring %s=%s", name, repr(value))

        # Do the reasonable thing if a user passes an int
        if isinstance(value, int):
            value = bytes([value])

        return self._write_handler(
            b"".join(
                [
                    constants.FEND,
                    bytes(getattr(constants, name.upper())),
                    util.escape_special_codes(value),
                    constants.FEND,
                ],
            ),
        )

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

        read_buffer = bytearray()
        frames = []

        def handle_fend():
            frame = util.recover_special_codes(util.strip_nmea(bytes(read_buffer)))
            if self.strip_df_start:
                frame = util.strip_df_start(frame)
            frames.append(frame)
            if callback is not None:
                callback(frame)
            read_buffer.clear()

        while min_frames is None or len(frames) < min_frames:
            read_data = self._read_handler(chunk_size)
            if not read_data:
                break

            self._logger.debug('read_data(%s)="%s"', len(read_data), read_data)

            # Handle NMEAPASS on T3-Micro (Unclear on this one)
            # http://wiki.argentdata.com/index.php?title=T3-Micro
            if len(read_data) >= 900:
                if constants.NMEA_HEADER in read_data and "\r\n" in read_data:
                    if callback:
                        callback(read_data)
                    return [read_data]

            # Normal frame splitting loop
            for byte in read_data:
                if byte == constants.FEND[0]:
                    if read_buffer:
                        handle_fend()
                else:
                    read_buffer.append(byte)
        if read_buffer:
            handle_fend()
        return frames

    def write(self, frame: bytes) -> int:
        """
        Writes frame to KISS interface.

        :param frame: Frame to write.
        """
        self._logger.debug('frame(%s)="%s"', len(frame), frame)

        frame_escaped = util.escape_special_codes(frame)
        self._logger.debug('frame_escaped(%s)="%s"', len(frame_escaped), frame_escaped)

        frame_kiss = b"".join(
            [constants.FEND, constants.DATA_FRAME, frame_escaped, constants.FEND],
        )
        self._logger.debug('frame_kiss(%s)="%s"', len(frame_kiss), frame_kiss)

        return self._write_handler(frame_kiss)


class TCPKISS(KISS):

    """KISS TCP Class."""

    def __init__(self, host: str, port: int, strip_df_start: bool = False):
        self.address = (host, int(port))
        super().__init__(strip_df_start)

    def _read_handler(self, read_bytes: Optional[int] = None) -> bytes:
        read_bytes = read_bytes or constants.READ_BYTES
        read_data = self.interface.recv(read_bytes)
        self._logger.debug("len(read_data)=%s", len(read_data))
        return read_data

    def _write_handler(self, frame: Optional[bytes] = None) -> int:
        if not frame:
            return 0
        if self.interface:
            self.interface.send(frame)
        else:
            raise exceptions.SocketClosedError

    def stop(self) -> None:
        if self.interface:
            self.interface.shutdown(socket.SHUT_RDWR)

    def start(self) -> None:
        """
        Initializes the KISS device and commits configuration.
        """
        self.interface = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._logger.debug("Connecting to %s", self.address)
        self.interface.connect(self.address)
        self._logger.info("Connected to %s", self.address)


class SerialKISS(KISS):

    """KISS Serial Class."""

    def __init__(self, port: str, speed: str, strip_df_start: bool = False) -> None:
        self.port = port
        self.speed = speed
        self.strip_df_start = strip_df_start
        super(SerialKISS, self).__init__(strip_df_start)

    def _read_handler(self, read_bytes: Optional[int] = None) -> bytes:
        read_data = b""
        while self.interface.isOpen() and not read_data:
            read_bytes = read_bytes or self.interface.in_waiting or constants.READ_BYTES
            read_data = self.interface.read(read_bytes)
        if len(read_data) > 0:
            self._logger.debug("len(read_data)=%s", len(read_data))
        return read_data

    def _write_handler(self, frame: Optional[bytes] = None) -> int:
        if not frame:
            return 0
        self.interface.write(frame)

    def _write_defaults(self, **kwargs: Any) -> Iterable[int]:
        """
        Previous verious defaulted to Xastir-friendly configs. Unfortunately
        those don't work with Bluetooth TNCs, so we're reverting to None.

        Use `config_xastir()` for Xastir defaults.
        """
        return [self.write_setting(k, v) for k, v in list(kwargs.items())]

    def config_xastir(self) -> Iterable[int]:
        """
        Helper method to set default configuration to those that ship with
        Xastir.
        """
        return self._write_defaults(**constants.DEFAULT_KISS_CONFIG_VALUES)

    def kiss_on(self) -> None:
        """Turns KISS ON."""
        self.interface.write(constants.KISS_ON)

    def kiss_off(self) -> None:
        """Turns KISS OFF."""
        self.interface.write(constants.KISS_OFF)

    def stop(self) -> None:
        try:
            if self.interface and self.interface.isOpen():
                self.interface.close()
        except AttributeError:
            if self.interface and self.interface._isOpen:
                self.interface.close()

    def start_no_config(self) -> None:
        """
        Initializes the KISS device without writing configuration.
        """
        self.interface = serial.Serial(self.port, self.speed)
        self.interface.timeout = constants.SERIAL_TIMEOUT

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
