"""
kiss3 Python KISS Module.
~~~~


:author: Greg Albrecht W2GMD <oss@undef.net>
:copyright: Copyright 2017 Greg Albrecht and Contributors
:license: Apache License, Version 2.0
:source: <https://github.com/ampledata/kiss>
"""
from importlib_metadata import version

from .classes import SerialKISS, TCPKISS
from .kiss import (
    create_serial_connection,
    create_tcp_connection,
    KISSDecode,
    AX25KISSDecode,
    KISSProtocol,
)

__author__ = "Greg Albrecht W2GMD <oss@undef.net>"  # NOQA pylint: disable=R0801
__copyright__ = (
    "Copyright 2017 Greg Albrecht and Contributors"  # NOQA pylint: disable=R0801
)
__license__ = "Apache License, Version 2.0"  # NOQA pylint: disable=R0801
__distribution__ = "kiss3"
__version__ = version(__distribution__)
__all__ = [
    "AX25KISSDecode",
    "create_serial_connection",
    "create_tcp_connection",
    "KISSDecode",
    "KISSProtocol",
    "SerialKISS",
    "TCPKISS",
]
