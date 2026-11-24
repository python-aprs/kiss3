r"""KISS framing for TNCs over serial and TCP.

`KISS <https://en.wikipedia.org/wiki/KISS_(amateur_radio_protocol)>`_ is how
software talks to a TNC: each AX.25 frame is wrapped in FEND (``0xC0``)
bytes after a one-byte command, with FEND and FESC bytes inside escaped.
This package frames and unframes that stream, and sends TNC parameters such
as TX delay and persistence.

Connecting
==========

``TCPKISS`` and ``SerialKISS`` block; ``read()`` returns AX.25 bytes and
``write()`` returns once the frame has gone out:

.. code-block:: python

    from ax253 import Frame

    import kiss

    tnc = kiss.TCPKISS("localhost", 8001)
    tnc.start(TX_DELAY=40)
    try:
        tnc.write(Frame.from_str("N0CALL>APRS,WIDE1-1:>on the air"))
        for raw in tnc.read(min_frames=1):
            print(Frame.from_bytes(raw))
    finally:
        tnc.stop()

``connect_tcp`` and ``connect_serial`` give an asyncio ``KISSProtocol``
whose ``read()`` yields decoded ``ax253.Frame`` objects; ``async with``
closes the connection at the end:

.. code-block:: python

    async with kiss.connect_tcp("localhost", 8001, settings={"TX_DELAY": 30}) as tnc:
        tnc.set_persistence(63)
        async for frame in tnc.read():
            print(frame)

``tnc = await kiss.connect_tcp(...)`` works too, with ``await tnc.close()``.
``create_tcp_connection`` and ``create_serial_connection`` are the lower-level
versions, returning ``(transport, protocol)``.

``encode_frame`` wraps bytes in KISS framing, for simulators and bridges:

>>> import kiss
>>> kiss.encode_frame(b"a\xc0b")
b'\xc0\x00a\xdb\xdcb\xc0'

Decoding a stream
=================

The decoders take bytes as they arrive and return complete frames.
``AX25KISSDecode`` returns ``ax253.Frame`` objects and ``KISSDecode`` returns
the unescaped bytes. Both skip frames that aren't data, like TNC parameter
echoes:

>>> from ax253 import Frame
>>> import kiss
>>> stream = b"\xc0\x00" + bytes(Frame.from_str("N0CALL>APRS:>hi")) + b"\xc0"
>>> decoder = kiss.AX25KISSDecode()
>>> list(decoder.update(stream[:10]))  # half a frame: nothing yet
[]
>>> [str(f) for f in decoder.update(stream[10:] + b"\xc0\x01\x28\xc0")]
['N0CALL>APRS:>hi']
>>> list(kiss.KISSDecode().update(b"\xc0\x00a\xdb\xdcb\xc0"))
[b'a\xc0b']

Pass ``strip_df_start=False`` to keep the command byte and every frame.

Multi-port TNCs
===============

The high nibble of the command byte is the KISS port (0-15): dual-port TNCs
and Dire Wolf with several radio channels use it. ``AX25KISSDecode`` returns
``KISSFrame`` objects, which are ``ax253.Frame`` objects with the ``port``
they arrived on. ``ports=`` limits a decoder to some ports:

>>> port1 = b"\xc0\x10" + bytes(Frame.from_str("N0CALL>APRS:>port 1")) + b"\xc0"
>>> [(f.port, str(f)) for f in kiss.AX25KISSDecode().update(port1)]
[(1, 'N0CALL>APRS:>port 1')]
>>> list(kiss.AX25KISSDecode(ports={0}).update(port1))
[]

``KISSProtocol.write(frame, port=1)`` and ``write_setting(..., port=1)``
send on a port. Writing a received ``KISSFrame`` without a port sends it out
the port it came in on, which is what a digipeater wants.

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
    KISSFrame,
    KISSProtocol,
    command_byte,
    connect_serial,
    connect_tcp,
    create_serial_connection,
    create_tcp_connection,
    encode_frame,
    split_data_frame,
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
    "connect_serial",
    "connect_tcp",
    "encode_frame",
    "create_serial_connection",
    "create_tcp_connection",
    "Command",
    "command_byte",
    "KISSDecode",
    "KISSFrame",
    "KISSProtocol",
    "SerialKISS",
    "split_data_frame",
    "TCPKISS",
]
