"""Tests for KISS Util Module."""

from kiss3 import constants, util

__author__ = "Greg Albrecht W2GMD <oss@undef.net>"  # NOQA pylint: disable=R0801
__copyright__ = (
    "Copyright 2017 Greg Albrecht and Contributors"  # NOQA pylint: disable=R0801
)
__license__ = "Apache License, Version 2.0"  # NOQA pylint: disable=R0801


def test_escape_special_codes_fend():
    """
    Tests `kiss3.escape_special_codes` util function.
    """
    assert util.escape_special_codes(constants.FEND) == constants.FESC_TFEND


def test_escape_special_codes_fesc():
    """
    Tests `kiss3.escape_special_codes` util function.
    """
    assert util.escape_special_codes(constants.FESC) == constants.FESC_TFESC


def test_extract_ui(sample_frames):
    """
    Tests `util.extract_ui` util function.
    """
    assert util.extract_ui(sample_frames[0]) == "APRX240W2GMD 6WIDE1 1"
