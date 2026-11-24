"""Tests for KISS Util Module."""

import itertools

import pytest

from kiss import constants, util

__author__ = "Greg Albrecht W2GMD <oss@undef.net>"
__copyright__ = "Copyright 2017 Greg Albrecht and Contributors"
__license__ = "Apache License, Version 2.0"


def test_escape_special_codes_fend():
    """
    Tests `kiss.escape_special_codes` util function.
    """
    assert util.escape_special_codes(constants.FEND) == constants.FESC_TFEND


def test_escape_special_codes_fesc():
    """
    Tests `kiss.escape_special_codes` util function.
    """
    assert util.escape_special_codes(constants.FESC) == constants.FESC_TFESC


def test_extract_ui(sample_frames):
    """
    Tests `util.extract_ui` util function.
    """
    with pytest.deprecated_call():  # issue #21
        assert util.extract_ui(sample_frames[0]) == "APRX240W2GMD 6WIDE1 1"


def _recover_scan(escaped: bytes) -> bytes:
    """Reference unescape: a left-to-right scan over the KISS escapes."""
    out, i = bytearray(), 0
    while i < len(escaped):
        pair = escaped[i : i + 2]
        if pair == constants.FESC_TFESC:
            out += constants.FESC
            i += 2
        elif pair == constants.FESC_TFEND:
            out += constants.FEND
            i += 2
        else:
            out.append(escaped[i])
            i += 1
    return bytes(out)


SPECIAL = [constants.FEND, constants.FESC, constants.TFEND, constants.TFESC, b"A"]


@pytest.mark.parametrize("length", range(7))
def test_recover_special_codes_matches_scan(length):
    """Every sequence of special bytes (and stray FESCs) unescapes like a scan."""
    for combo in itertools.product(SPECIAL, repeat=length):
        escaped = b"".join(combo)
        recovered = util.recover_special_codes(escaped)
        assert isinstance(recovered, bytearray)
        assert recovered == _recover_scan(escaped)
        assert util.recover_special_codes(util.escape_special_codes(escaped)) == escaped
