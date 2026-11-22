"""
Python KISS Module.
~~~~


:author: Greg Albrecht W2GMD <oss@undef.net>
:copyright: Copyright 2017 Greg Albrecht and Contributors
:license: Apache License, Version 2.0
:source: <https://github.com/ampledata/kiss>
"""

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
