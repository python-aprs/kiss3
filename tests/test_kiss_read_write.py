import pytest

from kiss3 import constants

from .conftest import MockKISS


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


def test_read_write_read_frame(sample_frame):
    rk = MockKISS(data_buffer=sample_frame, strip_df_start=True)
    frames = rk.read()
    assert len(frames) == 1
    wk = MockKISS()
    wk.write(frames[0])
    rk2 = MockKISS(data_buffer=wk.buffer.getvalue(), strip_df_start=True)
    frames2 = rk2.read()
    assert len(frames2) == 1
    assert frames[0] == frames2[0]


def test_write_frame(kiss_instance):
    data = b"12345"
    k = kiss_instance(data_buffer=b"")
    k.write(data)
    assert (
        k.buffer.getvalue()
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
            k.buffer.getvalue()
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
def test_write_setting(name, value, exp_data):
    k = MockKISS()
    k.write_setting(name, value)
    assert k.buffer.getvalue() == constants.FEND + exp_data + constants.FEND
