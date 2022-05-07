#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Python KISS Module Exception Definitions."""

__author__ = "Greg Albrecht W2GMD <oss@undef.net>"  # NOQA pylint: disable=R0801
__copyright__ = (
    "Copyright 2017 Greg Albrecht and Contributors"  # NOQA pylint: disable=R0801
)
__license__ = "Apache License, Version 2.0"  # NOQA pylint: disable=R0801


class SocketClosedError(Exception):
    """Socket Closed Error."""

    pass


# for compatibility
SocketClosetError = SocketClosedError
