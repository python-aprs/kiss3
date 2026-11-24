"""Python KISS Module Utility Functions Definitions."""

import logging
import warnings

from . import constants

__author__ = "Greg Albrecht W2GMD <oss@undef.net>"
__copyright__ = "Copyright 2017 Greg Albrecht and Contributors"
__license__ = "Apache License, Version 2.0"


def escape_special_codes(raw_codes):
    """
    Escape special codes, per KISS spec.

    "If the FEND or FESC codes appear in the data to be transferred, they
    need to be escaped. The FEND code is then sent as FESC, TFEND and the
    FESC is then sent as FESC, TFESC."
    - http://en.wikipedia.org/wiki/KISS_(TNC)#Description
    """
    return raw_codes.replace(constants.FESC, constants.FESC_TFESC).replace(
        constants.FEND,
        constants.FESC_TFEND,
    )


def recover_special_codes(escaped_codes):
    """
    Recover special codes, per KISS spec.

    "If the FESC_TFESC or FESC_TFEND escaped codes appear in the data received,
    they need to be recovered to the original codes. The FESC_TFESC code is
    replaced by FESC code and FESC_TFEND is replaced by FEND code."
    - http://en.wikipedia.org/wiki/KISS_(TNC)#Description
    """
    return bytearray(_recover_special_codes(bytes(escaped_codes)))


def _recover_special_codes(escaped_codes: bytes) -> bytes:
    """recover_special_codes() as bytes.

    Escapes pair up left to right and never overlap (the byte after FESC is
    TFEND or TFESC, never FESC), so replacing FESC TFEND first and then
    FESC TFESC is the same as a left-to-right scan. A FESC followed by
    anything else is kept as is.
    """
    if constants.FESC not in escaped_codes:
        return escaped_codes
    return escaped_codes.replace(constants.FESC_TFEND, constants.FEND).replace(
        constants.FESC_TFESC, constants.FESC
    )


def extract_ui(frame):
    """
    Extracts the UI component of an individual frame.

    Deprecated: this legacy helper does not decode AX.25 correctly. Use
    ``ax253.Frame.from_bytes`` on a frame from a decoder with
    ``strip_df_start=True`` instead.

    :param frame: APRS/AX.25 frame.
    :type frame: bytes
    :returns: UI component of frame.
    :rtype: str
    """
    warnings.warn(
        "kiss.util.extract_ui is deprecated; decode frames with ax253.Frame.from_bytes",
        DeprecationWarning,
        stacklevel=2,
    )
    start_ui = frame.split(b"".join([constants.FEND, constants.DATA_FRAME]))
    end_ui = start_ui[0].split(
        b"".join([constants.SLOT_TIME, constants.NO_PROTOCOL_ID]),
    )
    return "".join([chr(x >> 1) for x in end_ui[0]])


def strip_df_start(frame):
    """
    Strips the KISS DATA_FRAME command byte (0x00) from the start of a frame.

    Only that one byte is removed: the AX.25 frame after it may itself start
    with 0x00 or end in spaces, CR or LF, all of which are significant.

    :param frame: KISS frame contents, starting with the command byte.
    :type frame: bytes
    :returns: the frame without its leading DATA_FRAME byte.
    :rtype: bytes
    """
    if frame[:1] == constants.DATA_FRAME:
        return frame[1:]
    return frame


def strip_nmea(frame):
    """
    Extracts NMEA header from T3-Micro or NMEA encoded KISS frames.
    """
    if len(frame) > 0:
        if frame[0] == 240:
            return frame[1:].rstrip()
    return frame


def getLogger(name):
    """
    Get the logger for ``name``.

    kiss3 is a library, so it no longer attaches handlers or sets levels:
    configure logging in your application (e.g. ``logging.basicConfig``).
    """
    return logging.getLogger(name)


def valid_length(at_least, at_most=None, sequence_validator=None):
    def _validator(instance, attribute, value):
        if sequence_validator:
            sequence_validator(instance, attribute, value)
        len_value = len(value)
        if len_value < at_least:
            raise ValueError(
                f"{attribute.name} must be at least {at_least} (actual={len_value})"
            )
        if at_most is not None and len_value > at_most:
            raise ValueError(
                f"{attribute.name} must be at most {at_most} (actual={len_value})"
            )

    return _validator


def instance_of_or(types, other_validator):
    """check if the value is a bool or satisfies `other_validator`."""

    def _validator(instance, attribute, value):
        if not isinstance(value, types):
            other_validator(instance, attribute, value)

    return _validator


def optional_bool_or_bytes(v):
    if v is not None and not isinstance(v, bool):
        return bytes(v)
    return v
