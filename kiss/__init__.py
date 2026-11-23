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

    tnc = kiss.TCPKISS("localhost", 8001, strip_df_start=True)
    tnc.start(TX_DELAY=40)
    try:
        tnc.write(Frame.from_str("N0CALL>APRS,WIDE1-1:>on the air"))
        for raw in tnc.read(min_frames=1):
            print(Frame.from_bytes(raw))
    finally:
        tnc.stop()

``create_tcp_connection`` and ``create_serial_connection`` return an asyncio
``KISSProtocol`` whose ``read()`` yields decoded ``ax253.Frame`` objects:

.. code-block:: python

    transport, protocol = await kiss.create_tcp_connection("localhost", 8001)
    async for frame in protocol.read():
        print(frame)

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
