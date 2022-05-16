kiss3 - Python KISS Module
**************************

kiss3 is a Python Module that implements the
`KISS Protocol <https://en.wikipedia.org/wiki/KISS_(TNC)>`_ for
communicating with KISS-enabled devices (such as Serial or TCP TNCs)
and provides support for encoding and decoding AX.25 frames.

Versions
========

- 6.5.x branch will be the last version of this Module that supports Python 2.7.x
- 7.x.x branch and-on will be Python 3.x ONLY.
- 8.x branch from ``python-aprs`` supports python 3.6+

Installation
============
Install from pypi using pip: ``pip install kiss3``


Usage Examples
==============
Read & print frames from a TNC connected to '/dev/ttyUSB0' at 1200 baud::

    import kiss3

    def p(x): print(x)  # prints whatever is passed in.

    k = kiss3.SerialKISS('/dev/ttyUSB0', 1200)
    k.start()  # inits the TNC, optionally passes KISS config flags.
    k.read(callback=p)  # reads frames and passes them to `p`.


See also: examples/ directory.


Testing
=======
Run tox::

    tox


See Also
========

* `Python APRS Module <https://github.com/python-aprs/aprs3>`_ Library for sending, receiving and parsing APRS Frames to and from multiple Interfaces
* `Python KISS Module <https://github.com/python-aprs/kiss3>`_ Handles interfacing-to and encoding-for various KISS Interfaces.
* `Python APRS Gateway <https://github.com/ampledata/aprsgate>`_ Uses Redis PubSub to run a multi-interface APRS Gateway.
* `Python APRS Tracker <https://github.com/ampledata/aprstracker>`_ TK.
* `dirus <https://github.com/ampledata/dirus>`_ Dirus is a daemon for managing a SDR to Dire Wolf interface. Manifests that interface as a KISS TCP port.


Similar Projects
================

* `apex <https://github.com/Syncleus/apex>`_ by Jeffrey Phillips Freeman (WI2ARD). Next-Gen APRS Protocol. (based on this Module! :)
* `aprslib <https://github.com/rossengeorgiev/aprs-python>`_ by Rossen Georgiev. A Python APRS Library with build-in parsers for several Frame types.
* `aprx <http://thelifeofkenneth.com/aprx/>`_ by Matti & Kenneth. A C-based Digi/IGate Software for POSIX platforms.
* `dixprs <https://sites.google.com/site/dixprs/>`_ by HA5DI. A Python APRS project with KISS, digipeater, et al., support.
* `APRSDroid <http://aprsdroid.org/>`_ by GE0RG. A Java/Scala Android APRS App.
* `YAAC <http://www.ka2ddo.org/ka2ddo/YAAC.html>`_ by KA2DDO. A Java APRS Client.
* `Ham-APRS-FAP <http://search.cpan.org/dist/Ham-APRS-FAP/>`_ by aprs.fi: A Perl APRS Parser.
* `Dire Wolf <https://github.com/wb2osz/direwolf>`_ by WB2OSZ. A C-Based Soft-TNC for interfacing with sound cards. Can present as a KISS interface!

Build Status
============

Master:

.. image:: https://travis-ci.org/ampledata/kiss.svg?branch=master
    :target: https://travis-ci.org/ampledata/kiss

Develop:

.. image:: https://travis-ci.org/ampledata/kiss.svg?branch=develop
    :target: https://travis-ci.org/ampledata/kiss


Source
======
Github: https://github.com/ampledata/kiss

Author
======
Greg Albrecht W2GMD oss@undef.net

http://ampledata.org/

Copyright
=========
Copyright 2017 Greg Albrecht and Contributors

`Automatic Packet Reporting System (APRS) <http://www.aprs.org/>`_ is Copyright Bob Bruninga WB4APR wb4apr@amsat.org

License
=======
Apache License, Version 2.0. See LICENSE for details.
