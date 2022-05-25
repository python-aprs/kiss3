import pytest

from kiss3 import constants
from kiss3.ax25 import Frame
from kiss3.util import getLogger, escape_special_codes


__author__ = "Greg Albrecht W2GMD <oss@undef.net>"  # NOQA pylint: disable=R0801
__copyright__ = (
    "Copyright 2017 Greg Albrecht and Contributors"  # NOQA pylint: disable=R0801
)
__license__ = "Apache License, Version 2.0"  # NOQA pylint: disable=R0801


logger = getLogger(__name__)


@pytest.mark.parametrize(
    "data_buffer,exp_frames",
    (
        (b"", []),
        (b"12345", [b"12345"]),
        (constants.FEND.join([b"12345", b"67890"]), [b"12345", b"67890"]),
        (b"".join([constants.FEND] * 10 + [b"12345"]), [b"12345"]),
        (b"".join([b"12345"] + [constants.FEND] * 10), [b"12345"]),
    ),
)
@pytest.mark.parametrize("min_frames", [0, 1, 2, None])
@pytest.mark.parametrize("strip_df_start", [True, False])
def test_frame_split(
    kiss_instance, data_buffer, exp_frames, min_frames, strip_df_start
):
    k = kiss_instance(data_buffer=data_buffer, strip_df_start=strip_df_start)
    if min_frames is not None:
        exp_frames = exp_frames[:min_frames]
    seen_frames = []

    def fr_callback(frame):
        assert frame == exp_frames[len(seen_frames)]
        seen_frames.append(frame)

    assert (
        k.read(chunk_size=2, callback=fr_callback, min_frames=min_frames) == exp_frames
    )


def test_read_write_read_frame(kiss_instance, sample_frame):
    rk = kiss_instance(data_buffer=sample_frame, strip_df_start=True)
    frames = rk.read()
    assert len(frames) == 1
    wk = kiss_instance()
    wk.write(frames[0])
    rk2 = kiss_instance(
        data_buffer=wk.protocol.transport.buffer.getvalue(), strip_df_start=True
    )
    frames2 = rk2.read()
    assert len(frames2) == 1
    assert frames[0] == frames2[0]


def test_write_frame(kiss_instance):
    data = b"12345"
    k = kiss_instance(data_buffer=b"")
    k.write(data)
    assert (
        k.protocol.transport.buffer.getvalue()
        == constants.FEND + constants.DATA_FRAME + data + constants.FEND
    )


@pytest.mark.parametrize(
    "data,exp_data",
    (
        (constants.FEND, constants.FESC_TFEND),
        (constants.FESC, constants.FESC_TFESC),
        (constants.FESC_TFESC, b"".join([constants.FESC_TFESC, constants.TFESC])),
        (constants.FESC_TFEND, b"".join([constants.FESC_TFESC, constants.TFEND])),
    ),
)
@pytest.mark.parametrize("direction", ["read", "write"])
def test_read_write_escape(kiss_instance, data, exp_data, direction):
    k = kiss_instance(data_buffer=b"" if direction == "write" else exp_data)
    if direction == "write":
        k.write(data)
        assert (
            k.protocol.transport.buffer.getvalue()
            == constants.FEND + constants.DATA_FRAME + exp_data + constants.FEND
        )
    elif direction == "read":
        frames = k.read()
        assert len(frames) == 1
        assert frames[0] == data
    else:
        raise RuntimeError("Unknown direction: {}".format(direction))


@pytest.mark.parametrize(
    "name,value,exp_data",
    (
        ("TX_DELAY", 100, b"".join([constants.TX_DELAY, bytes([100])])),
        ("TX_DELAY", b"\x3a", b"".join([constants.TX_DELAY, b"\x3a"])),
        ("PERSISTENCE", 116, b"".join([constants.PERSISTENCE, bytes([116])])),
        ("PERSISTENCE", b"\x0b", b"".join([constants.PERSISTENCE, b"\x0b"])),
        ("SLOT_TIME", 50, b"".join([constants.SLOT_TIME, bytes([50])])),
        ("SLOT_TIME", b"\x1c", b"".join([constants.SLOT_TIME, b"\x1c"])),
        ("TX_TAIL", 0, b"".join([constants.TX_TAIL, bytes([0])])),
        ("TX_TAIL", b"\x0d", b"".join([constants.TX_TAIL, b"\x0d"])),
        ("FULL_DUPLEX", 1, b"".join([constants.FULL_DUPLEX, bytes([1])])),
        ("FULL_DUPLEX", b"\x00", b"".join([constants.FULL_DUPLEX, b"\x00"])),
        ("SET_HARDWARE", 64, b"".join([constants.SET_HARDWARE, bytes([64])])),
        (
            "SET_HARDWARE",
            b"\x00\x01\x02",
            b"".join([constants.SET_HARDWARE, b"\x00\x01\x02"]),
        ),
        ("RETURN", 0, b"".join([constants.RETURN, bytes([0])])),
        ("RETURN", b"\x00", b"".join([constants.RETURN, b"\x00"])),
    ),
)
def test_write_setting(kiss_instance, name, value, exp_data):
    k = kiss_instance()
    k.write_setting(name, value)
    assert (
        k.protocol.transport.buffer.getvalue()
        == constants.FEND + exp_data + constants.FEND
    )


def test_config_xastir(dummy_serialkiss):
    """Tests writing Xastir config to KISS TNC."""
    dummy_serialkiss.config_xastir()
    print(dummy_serialkiss.protocol.transport.buffer.getvalue())


@pytest.fixture
def payload_frame_kiss(payload_frame):
    frame_encoded = bytes(payload_frame)
    logger.debug('frame_encoded="%s"', frame_encoded)

    frame_escaped = escape_special_codes(frame_encoded)
    logger.debug('frame_escaped="%s"', frame_escaped)

    frame_kiss = b"".join(
        [constants.FEND, constants.DATA_FRAME, frame_escaped, constants.FEND]
    )
    logger.debug('frame_kiss="%s"', frame_kiss)
    return frame_kiss


def test_write_ax25(kiss_instance, payload_frame, payload_frame_kiss):
    frame_encoded = bytes(payload_frame)
    logger.debug('frame_encoded="%s"', frame_encoded)

    ks = kiss_instance(strip_df_start=True)
    ks.write(frame_encoded)
    assert ks.protocol.transport.buffer.getvalue() == payload_frame_kiss


@pytest.mark.parametrize("min_frames", [1, 2, 10])
def test_read_ax25(kiss_instance, payload_frame_kiss, payload_frame, min_frames):
    """Test decode of ax25 from kiss."""
    ks = kiss_instance(payload_frame_kiss * min_frames, strip_df_start=True)
    frames = ks.read()
    assert len(frames) >= min_frames
    for frame in frames:
        decoded_frame = Frame.from_ax25(frame)
        assert len(decoded_frame) == 1
        assert decoded_frame[0] == payload_frame
