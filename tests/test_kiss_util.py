#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Tests for KISS Util Module."""

import kiss3

__author__ = "Greg Albrecht W2GMD <oss@undef.net>"  # NOQA pylint: disable=R0801
__copyright__ = (
    "Copyright 2017 Greg Albrecht and Contributors"  # NOQA pylint: disable=R0801
)
__license__ = "Apache License, Version 2.0"  # NOQA pylint: disable=R0801


def test_escape_special_codes_fend():
    """
    Tests `kiss3.escape_special_codes` util function.
    """
    assert kiss3.escape_special_codes(kiss3.FEND) == kiss3.FESC_TFEND


def test_escape_special_codes_fesc():
    """
    Tests `kiss3.escape_special_codes` util function.
    """
    assert kiss3.escape_special_codes(kiss3.FESC) == kiss3.FESC_TFESC


def test_extract_ui(sample_frames):
    """
    Tests `kiss3.extract_ui` util function.
    """
    frame_ui = kiss3.extract_ui(sample_frames[0])
    assert frame_ui == "APRX240W2GMD 6WIDE1 1"
