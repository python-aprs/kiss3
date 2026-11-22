"""
KISS behaviours seen on real TNCs and software modems beyond the basic spec
examples: multi-port TNCs, parameter echoes, banners before KISS mode,
significant trailing bytes, malformed escapes.
"""

import pytest
from ax253 import Frame

from kiss import kiss
from kiss.constants import FEND, FESC, KISS_ON, TFEND, TFESC
from kiss.util import escape_special_codes

AX25 = bytes(Frame.from_str("N0CALL>APRS,WIDE1-1:>hello"))


def decode(data, strip_df_start=True, cls=kiss.KISSDecode):
    d = cls(strip_df_start=strip_df_start) if cls is kiss.KISSDecode else cls()
    return list(d.update(data)) + list(d.flush())


@pytest.mark.parametrize("port", range(15))
def test_data_frame_any_port(port):
    """
    Multi-port TNCs (e.g. dual-band, KPC-9612) put the port in the high nibble.
    Port 12's command byte is 0xC0 and must itself be escaped.
    """
    command = escape_special_codes(bytes([port << 4]))
    assert decode(FEND + command + AX25 + FEND) == [AX25]


def test_port_15_is_nmea_passthrough():
    """
    0xF0 is both "port 15 data" and the T3-Micro NMEA lead byte; kiss3
    treats it as NMEA (trailing whitespace stripped).
    """
    assert decode(FEND + b"\xf0" + AX25 + b"\r\n" + FEND) == [AX25]


@pytest.mark.parametrize(
    "command",
    [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x11, 0x16, 0x0C, 0x0E, 0xFF],
)
def test_non_data_frames_ignored(command):
    """TX delay echoes, SetHardware replies, Return: never decoded as AX.25."""
    data = FEND + bytes([command]) + b"\x28\x01" + FEND + FEND + b"\x00" + AX25 + FEND
    assert decode(data) == [AX25]


def test_non_data_frames_kept_when_not_stripping():
    data = FEND + b"\x06\x01\x02" + FEND
    assert decode(data, strip_df_start=False) == [b"\x06\x01\x02"]


def test_empty_and_command_only_frames_ignored():
    assert decode(FEND + FEND + b"\x00" + FEND + FEND) == []


@pytest.mark.parametrize("suffix", [b" ", b"  ", b"\r", b"\n", b"\r\n", b"\x00", b"\t"])
def test_trailing_bytes_in_info_preserved(suffix):
    """
    Kenwood and many trackers end info fields with CR; APRS message text
    may end in spaces. KISS must deliver them untouched.
    """
    raw = AX25 + suffix
    assert decode(FEND + b"\x00" + raw + FEND) == [raw]
    frames = decode(FEND + b"\x00" + raw + FEND, cls=kiss.AX25KISSDecode)
    assert frames[0].info == b">hello" + suffix


def test_single_command_byte_stripped():
    """Only the command byte is removed, not every leading 0x00."""
    raw = b"\x00\x00payload"
    assert decode(FEND + b"\x00" + raw + FEND) == [raw]


def test_banner_before_kiss_mode_dropped_by_ax25_decoder():
    """
    A TNC that was just switched into KISS mode may still emit its command
    prompt or banner before the first FEND. Those bytes are not AX.25.
    """
    data = b"cmd:KISS ON\r\n" + FEND + b"\x00" + AX25 + FEND
    frames = decode(data, cls=kiss.AX25KISSDecode)
    assert [bytes(f) for f in frames] == [AX25]


def test_frame_without_leading_fend():
    """Some TNCs only send the trailing FEND."""
    assert decode(b"\x00" + AX25 + FEND + b"\x00" + AX25 + FEND) == [AX25, AX25]


def test_unterminated_final_frame_returned_on_flush():
    d = kiss.KISSDecode(strip_df_start=True)
    assert list(d.update(FEND + b"\x00" + AX25)) == []
    assert list(d.flush()) == [AX25]


@pytest.mark.parametrize(
    "escaped, raw",
    [
        (FESC + TFEND, FEND),
        (FESC + TFESC, FESC),
        (FESC + TFESC + TFEND, FESC + TFEND),
        (FESC + TFEND + FESC + TFESC, FEND + FESC),
        (TFEND + TFESC, TFEND + TFESC),  # transposes alone are literal
    ],
)
def test_escapes(escaped, raw):
    assert decode(FEND + b"\x00" + escaped + FEND) == [raw]


@pytest.mark.parametrize(
    "escaped, raw",
    [
        (FESC + b"A", FESC + b"A"),  # invalid escape: passed through
        (b"A" + FESC, b"A" + FESC),  # FESC truncated by FEND
    ],
)
def test_malformed_escapes_lenient(escaped, raw):
    assert decode(FEND + b"\x00" + escaped + FEND) == [raw]


def test_nmea_passthrough():
    """T3-Micro style: NMEA sentences framed with an 0xF0 lead byte."""
    sentence = b"$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47"
    assert decode(FEND + b"\xf0" + sentence + b"\r\n" + FEND) == [sentence]


class _Transport:
    def __init__(self):
        self.data = b""

    def write(self, data):
        assert isinstance(data, bytes)
        self.data += data


def _protocol():
    p = kiss.KISSProtocol()
    p.transport = _Transport()
    return p


@pytest.mark.parametrize("value, sent", [(0xC0, FESC + TFEND), (b"\xdb", FESC + TFESC)])
def test_write_setting_escaped_once(value, sent):
    p = _protocol()
    p.write_setting(kiss.Command.SET_HARDWARE, value)
    assert p.transport.data == FEND + b"\x06" + sent + FEND


def test_write_settings_in_order():
    p = _protocol()
    p.write_settings({kiss.Command.TX_DELAY: 40, kiss.Command.PERSISTENCE: b"\x3f"})
    assert p.transport.data == FEND + b"\x01\x28" + FEND + FEND + b"\x02\x3f" + FEND


def test_kiss_on_off_write_bytes():
    p = _protocol()
    p.kiss_on()
    assert p.transport.data == KISS_ON
    p.transport.data = b""
    p.kiss_off()
    assert p.transport.data == FEND + b"\xff" + FEND + FEND


def test_decoders_are_slotted():
    from kiss.kiss import AX25KISSDecode, KISSDecode

    for obj in (KISSDecode(), AX25KISSDecode()):
        assert not hasattr(obj, "__dict__"), type(obj)
