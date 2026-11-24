kiss3 - Python KISS Module
**************************

.. image:: https://github.com/python-aprs/kiss3/actions/workflows/pytest.yml/badge.svg
    :target: https://github.com/python-aprs/kiss3/actions

kiss3 talks `KISS <https://en.wikipedia.org/wiki/KISS_(TNC)>`_ to TNCs
over serial ports and TCP (Dire Wolf, hardware TNCs, Bluetooth TNCs), with
plain blocking calls or asyncio. It frames and unframes AX.25 data and sends
TNC parameters. It needs Python 3.11 or newer.

Install it from PyPI::

    pip install kiss3

For APRS decoding on top of KISS, use `aprs3 <https://github.com/python-aprs/aprs3>`_.

Sending and receiving
=====================

``TCPKISS`` and ``SerialKISS`` block. ``start()`` connects and writes any
TNC parameters you pass, ``write()`` returns once the frame has gone out,
and ``read()`` waits for frames:

.. code-block:: python

    from ax253 import Frame

    import kiss

    tnc = kiss.TCPKISS("localhost", 8001)  # Dire Wolf
    # or: kiss.SerialKISS("/dev/ttyUSB0", baudrate=9600)
    tnc.start(TX_DELAY=40)
    try:
        tnc.write(Frame.from_str("N0CALL>APRS,WIDE1-1:>on the air"))
        for raw in tnc.read(min_frames=1):
            print(Frame.from_bytes(raw))
    finally:
        tnc.stop()

``read()`` returns each data frame's AX.25 bytes, without the KISS command
byte, and drops frames that aren't data. Pass ``strip_df_start=False`` to get
every frame with its command byte (``0x00`` for data on port 0); before
kiss3 9.0 that was the default.

With asyncio, ``create_tcp_connection`` and ``create_serial_connection``
return a ``KISSProtocol`` whose ``read()`` yields ``ax253.Frame`` objects:

.. code-block:: python

    import asyncio

    import kiss


    async def main():
        transport, protocol = await kiss.create_tcp_connection("localhost", 8001)
        async for frame in protocol.read():
            print(frame)


    asyncio.run(main())

Decoding a byte stream
======================

If you read the bytes yourself, the decoders turn them into frames as they
arrive:

>>> from ax253 import Frame
>>> import kiss
>>> stream = b"\xc0\x00" + bytes(Frame.from_str("N0CALL>APRS:>hi")) + b"\xc0"
>>> decoder = kiss.AX25KISSDecode()
>>> list(decoder.update(stream[:10]))
[]
>>> [str(frame) for frame in decoder.update(stream[10:])]
['N0CALL>APRS:>hi']

Multi-port TNCs
===============

Dual-port TNCs and Dire Wolf with several radio channels put a port number
(0-15) in the high nibble of the KISS command byte. Decoded frames are
``kiss.KISSFrame`` objects, an ``ax253.Frame`` with the ``port`` it came in
on:

>>> port2 = b"\xc0\x20" + bytes(Frame.from_str("N0CALL>APRS:>hi")) + b"\xc0"
>>> [(frame.port, str(frame)) for frame in kiss.AX25KISSDecode().update(port2)]
[(2, 'N0CALL>APRS:>hi')]

To send on a port, pass it to ``write(frame, port=2)`` or
``write_setting("TX_DELAY", 40, port=2)``. A received frame written back
without a port goes out the port it arrived on. ``AX25KISSDecode(ports={0})``
ignores frames from other ports.

Detecting a lost connection
===========================

``read(min_frames=None)`` blocks until the connection closes, then returns
the frames that were left. Check ``connected`` to tell a closed connection
from a quiet one, and call ``stop()`` and ``start()`` to reconnect:

.. code-block:: python

    while True:
        tnc.read(callback=print, min_frames=None)
        if not tnc.connected:
            tnc.stop()
            tnc.start()

A TCP peer that disappears without closing the connection (network cable
pulled, host crashed) is only noticed when a write fails or the operating
system's TCP keepalive gives up.

Examples
========

The `examples <./examples>`_ directory has two scripts that work with any
KISS TNC, given ``--tcp host:port`` or ``--serial device``:

* ``kiss_monitor.py`` prints every frame the TNC hears.
* ``kiss_send.py`` sends frames given in TNC2 text, and can set TNC
  parameters like ``--set TX_DELAY=40``.

Versions
========

8.x is published by python-aprs as ``kiss3``. Earlier versions were released
by Greg Albrecht as ``kiss``.

Testing
=======

Run the tests with `uv <https://docs.astral.sh/uv/>`_::

    uv run pytest

Related projects
================

* `ax253 <https://github.com/python-aprs/ax253>`_, the AX.25 frames this
  package carries.
* `aprs3 <https://github.com/python-aprs/aprs3>`_, APRS encoding and decoding
  over KISS and APRS-IS.
* `Dire Wolf <https://github.com/wb2osz/direwolf>`_ by WB2OSZ, a sound card
  TNC with a KISS interface.

Source
======
GitHub: https://github.com/python-aprs/kiss3

Authors
=======
Greg Albrecht W2GMD oss@undef.net

http://ampledata.org/

Masen Furer KF7HVM kf7hvm@0x26.net

Copyright
=========
Copyright 2022 Masen Furer and Contributors

Copyright 2017 Greg Albrecht and Contributors

`Automatic Packet Reporting System (APRS) <http://www.aprs.org/>`_ is Copyright Bob Bruninga WB4APR wb4apr@amsat.org

License
=======
Apache License, Version 2.0. See LICENSE for details.