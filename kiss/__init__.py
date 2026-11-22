"""KISS framing for TNCs over serial and TCP.

Encode and decode `KISS <https://en.wikipedia.org/wiki/KISS_(amateur_radio_protocol)>`_
frames with a blocking interface (``SerialKISS``, ``TCPKISS``) or asyncio
protocols (``create_serial_connection``, ``create_tcp_connection``).

Based on the original ``kiss`` module by Greg Albrecht W2GMD
(https://github.com/ampledata/kiss), Apache License 2.0.
"""

import logging
from importlib.metadata import version

from .classes import TCPKISS, SerialKISS
from .kiss import (
    AX25KISSDecode,
    Command,
    KISSDecode,
    KISSProtocol,
    create_serial_connection,
    create_tcp_connection,
)

__author__ = "Greg Albrecht W2GMD <oss@undef.net>"
__copyright__ = "Copyright 2017 Greg Albrecht and Contributors"
__license__ = "Apache License, Version 2.0"
__distribution__ = "kiss3"
__version__ = version(__distribution__)

# library logging etiquette: never print unless the application configures it
logging.getLogger(__name__).addHandler(logging.NullHandler())
__all__ = [
    "AX25KISSDecode",
    "create_serial_connection",
    "create_tcp_connection",
    "Command",
    "KISSDecode",
    "KISSProtocol",
    "SerialKISS",
    "TCPKISS",
]
