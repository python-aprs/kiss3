import pytest

from kiss3.ax25 import Address, Control, Frame


__author__ = "Masen Furer KF7HVM <kf7hvm@0x26.net>"  # NOQA pylint: disable=R0801
__copyright__ = (
    "Copyright 2022 Masen Furer and Contributors"  # NOQA pylint: disable=R0801
)
__license__ = "Apache License, Version 2.0"  # NOQA pylint: disable=R0801


@pytest.mark.parametrize(
    "text,exp_address",
    (
        ("N0CALL", Address(b"N0CALL", 0, False, False)),
        ("N0CALL*", Address(b"N0CALL", 0, True, True)),
        ("N0CALL-1", Address(b"N0CALL", 1, False, False)),
        ("N0CALL-1*", Address(b"N0CALL", 1, True, True)),
    ),
)
def test_address_from_text(text, exp_address):
    a = Address.from_str(text)
    assert a == exp_address
    assert str(a) == text
    print(repr(bytes(a)))


@pytest.mark.parametrize(
    "ax25_bytes,exp_address",
    (
        (b"\x9c`\x86\x82\x98\x98`", Address(b"N0CALL", 0, False, False)),
        (b"\x9c`\x86\x82\x98\x98\xe1", Address(b"N0CALL", 0, True, True)),
        (b"\x9c`\x86\x82\x98\x98b", Address(b"N0CALL", 1, False, False)),
        (b"\x9c`\x86\x82\x98\x98\xe3", Address(b"N0CALL", 1, True, True)),
    ),
)
def test_address_from_ax25(ax25_bytes, exp_address):
    a = Address.from_bytes(ax25_bytes)
    assert a == exp_address
    assert Address.from_str(str(a)) == exp_address


@pytest.mark.parametrize(
    "ax25_str, exp_frame",
    (
        (
            "FOO>APRS:!4605.21N/12327.31W#RNG0125Foo comment",
            Frame(
                destination=Address(
                    callsign=b"APRS", ssid=0, digi=False, a7_hldc=False
                ),
                source=Address(callsign=b"FOO", ssid=0, digi=False, a7_hldc=True),
                path=[],
                control=Control(b"\x03"),
                pid=b"\xf0",
                info=b"!4605.21N/12327.31W#RNG0125Foo comment",
                fcs=None,
            ),
        ),
    ),
)
def test_Frame_from_str(ax25_str, exp_frame):
    assert Frame.from_str(ax25_str) == exp_frame
