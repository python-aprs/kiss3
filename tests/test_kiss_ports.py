"""Multi-port KISS: the port on received frames, and choosing it on send (#20)."""

import pytest
from ax253 import Frame

import kiss
from kiss import Command, KISSFrame, command_byte, split_data_frame
from kiss.constants import FEND

from .conftest import MockTransport

FRAME = Frame.from_str("N0CALL>APRS,WIDE1-1:>multi-port")


def kiss_bytes(port: int, payload: bytes = bytes(FRAME)) -> bytes:
    return FEND + bytes([port << 4]) + kiss.kiss.util.escape_special_codes(payload) + FEND


@pytest.mark.parametrize("port", [0, 1, 2, 9, 15])
def test_received_frame_carries_port(port):
    (frame,) = kiss.AX25KISSDecode().update(kiss_bytes(port))
    assert isinstance(frame, KISSFrame)
    assert isinstance(frame, Frame)
    assert frame.port == port
    assert str(frame) == str(FRAME)
    assert bytes(frame) == bytes(FRAME)


def test_ports_filter():
    stream = kiss_bytes(0) + kiss_bytes(1) + kiss_bytes(2)
    decoder = kiss.AX25KISSDecode(ports=[1, 2])
    assert [f.port for f in decoder.update(stream)] == [1, 2]
    assert list(kiss.KISSDecode(ports={0}).update(stream)) == [bytes(FRAME)]


def test_ports_filter_rejects_bad_port():
    with pytest.raises(ValueError):
        kiss.AX25KISSDecode(ports=[16])


def test_ports_filter_ignored_without_strip_df_start():
    stream = kiss_bytes(1)
    assert list(kiss.KISSDecode(strip_df_start=False, ports={0}).update(stream)) == [
        b"\x10" + bytes(FRAME)
    ]


def test_port_15_is_data_not_nmea():
    (frame,) = kiss.AX25KISSDecode().update(kiss_bytes(15))
    assert frame.port == 15


def test_nmea_passthrough_still_works():
    assert list(kiss.KISSDecode().update(b"\xc0\xf0$GPGGA,1*00\r\n\xc0")) == [
        b"$GPGGA,1*00"
    ]


def test_non_data_commands_on_other_ports_are_skipped():
    # TX_DELAY echo on port 1
    assert list(kiss.AX25KISSDecode().update(b"\xc0\x11\x28\xc0")) == []


def test_command_byte():
    assert command_byte(Command.DATA_FRAME) == b"\x00"
    assert command_byte(Command.DATA_FRAME, 15) == b"\xf0"
    assert command_byte(Command.SET_HARDWARE, 3) == b"\x36"
    assert command_byte(Command.RETURN) == b"\xff"
    with pytest.raises(ValueError):
        command_byte(Command.RETURN, 1)
    with pytest.raises(ValueError):
        command_byte(Command.DATA_FRAME, 16)
    with pytest.raises(ValueError):
        command_byte(Command.DATA_FRAME, -1)


def test_split_data_frame():
    assert split_data_frame(b"\x20abc") == (2, b"abc")
    assert split_data_frame(b"\x20") is None
    assert split_data_frame(b"") is None
    assert split_data_frame(b"\x21abc") is None
    # escapes are removed
    assert split_data_frame(b"\x00a\xdb\xdcb") == (0, b"a\xc0b")


def test_kiss_frame_from_bytes_validates_port():
    with pytest.raises(ValueError):
        KISSFrame.from_bytes(bytes(FRAME), port=16)
    assert KISSFrame.from_bytes(bytes(FRAME)).port == 0


def test_kiss_frame_constructor_validates_port():
    with pytest.raises(ValueError):
        KISSFrame(
            destination=FRAME.destination,
            source=FRAME.source,
            path=FRAME.path,
            port=16,
        )


@pytest.mark.parametrize("port", [0, 1, 15])
def test_write_on_port(kiss_instance, port):
    k = kiss_instance()
    k.write(FRAME, port=port)
    assert k.protocol.transport.buffer.getvalue() == kiss_bytes(port)


def test_write_received_frame_uses_its_port(kiss_instance):
    (received,) = kiss.AX25KISSDecode().update(kiss_bytes(3))
    k = kiss_instance()
    k.write(received)
    k.write(received, port=0)
    assert k.protocol.transport.buffer.getvalue() == kiss_bytes(3) + kiss_bytes(0)


def test_write_setting_on_port(kiss_instance):
    k = kiss_instance()
    k.write_setting("TX_DELAY", 40, port=1)
    assert k.protocol.transport.buffer.getvalue() == b"\xc0\x11\x28\xc0"


def test_write_settings_on_port():
    protocol = kiss.KISSProtocol()
    transport = MockTransport(protocol)
    protocol.write_settings({Command.TX_DELAY: 40, Command.PERSISTENCE: 63}, port=2)
    assert transport.buffer.getvalue() == b"\xc0\x21\x28\xc0\xc0\x22\x3f\xc0"


def test_round_trip_through_protocol_and_decoder():
    protocol = kiss.KISSProtocol()
    transport = MockTransport(protocol)
    protocol.write(FRAME, port=7)
    (frame,) = kiss.AX25KISSDecode().update(transport.buffer.getvalue())
    assert (frame.port, bytes(frame)) == (7, bytes(FRAME))


def test_handle_fend_strips_any_port():
    assert kiss.kiss.handle_fend(b"\x30abc") == b"abc"
    assert kiss.kiss.handle_fend(b"\x31abc") is None
    assert kiss.kiss.handle_fend(b"\x30abc", strip_df_start=False) == b"\x30abc"


def test_named_setter_on_port(kiss_instance):
    k = kiss_instance()
    k.set_tx_delay(400, port=1)
    assert k.protocol.transport.buffer.getvalue() == b"\xc0\x11\x28\xc0"
    protocol = kiss.KISSProtocol()
    transport = MockTransport(protocol)
    protocol.set_persistence(63, port=2)
    assert transport.buffer.getvalue() == b"\xc0\x22\x3f\xc0"
