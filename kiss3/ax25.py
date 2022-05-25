# -*- coding: utf-8 -*-
"""AX.25 encode/decode"""
import enum
import re
from typing import Any, List, Optional, Sequence, Union

import attr.validators
from attrs import define, field
from attr import validators
from bitarray import bitarray

from . import util
from .constants import UI_CONTROL_FIELD, NO_PROTOCOL_ID
from .fcs import FCS


__author__ = "Masen Furer KF7HVM <kf7hvm@0x26.net>"  # NOQA pylint: disable=R0801
__copyright__ = (
    "Copyright 2022 Masen Furer and Contributors"  # NOQA pylint: disable=R0801
)
__license__ = "Apache License, Version 2.0"  # NOQA pylint: disable=R0801


AX25_FLAG = 0x7E
AX25_FLAG_B = bytes([AX25_FLAG])
VALID_CALLSIGN_REX = re.compile(rb"^[A-Z0-9]+$")


def valid_callsign(instance, attribute, value):
    validators.instance_of(bytes)(instance, attribute, value)
    if not VALID_CALLSIGN_REX.match(value):
        raise ValueError("{!r} does not match {!r}".format(value, VALID_CALLSIGN_REX))


@define(slots=True, frozen=True)
class Address:
    """AX.25-encoded callsign."""

    callsign: bytes = field(converter=lambda c: c.upper(), validator=valid_callsign)
    ssid: int = field(default=0, converter=int)
    digi: bool = field(default=False, converter=bool)
    a7_hldc: bool = field(default=False, converter=bool)

    _logger = util.getLogger(__name__)  # pylint: disable=R0801

    @classmethod
    def from_bytes(cls, ax25_address: bytes, **kwargs: Any) -> "Address":
        if len(ax25_address) != 7:
            raise ValueError(
                "ax25 address must be 7 bytes, got {}".format(len(ax25_address))
            )
        callsign = bytes(b >> 1 for b in ax25_address[:6]).rstrip()
        ssid = (ax25_address[6] >> 1) & 0x0F
        a7 = bitarray()
        a7.frombytes(ax25_address[6:7])
        c_or_h = a7[0]
        r = a7[1:3]  # noqa: F841
        hldc = a7[7]
        init_kwargs = dict(
            callsign=callsign,
            ssid=ssid,
            digi=c_or_h if hldc else False,
            a7_hldc=hldc,
        )
        if kwargs:
            init_kwargs.update(kwargs)
        return cls(**init_kwargs)

    from_ax25 = from_bytes

    @classmethod
    def from_str(
        cls, address_spec: str, a7_hldc: bool = False, **kwargs: Any
    ) -> "Address":
        digi = "*" in address_spec
        address = address_spec.strip("*")
        callsign_str, found, ssid_str = address.partition("-")
        callsign = callsign_str.encode("utf-8")

        ssid = int(ssid_str) if ssid_str else 0
        init_kwargs = dict(
            callsign=callsign,
            ssid=ssid,
            digi=digi,
            a7_hldc=digi or a7_hldc,
        )
        if kwargs:
            init_kwargs.update(**kwargs)
        return cls(**init_kwargs)

    from_text = from_str

    @classmethod
    def from_any(
        cls, address: Union["Address", bytes, str], **kwargs: Any
    ) -> "Address":
        if isinstance(address, cls):
            if kwargs:
                address = address.evolve(**kwargs)
            return address
        elif isinstance(address, bytes):
            return cls.from_bytes(address, **kwargs)
        return cls.from_str(str(address), **kwargs)

    def __str__(self) -> str:
        return "".join(
            [
                self.callsign.decode("latin1"),
                # Append SSID if non-zero
                "-%d" % self.ssid if self.ssid else "",
                # If callsign was digipeated, append '*'.
                "*" if self.digi else "",
            ]
        )

    def __bytes__(self) -> bytes:
        if len(self.callsign) > 6:
            raise ValueError(
                "Cannot encode callsign > 6 bytes: {}".format(self.callsign)
            )
        callsign = bytes(b << 1 for b in self.callsign.ljust(6))
        a7 = bitarray()
        a7.frombytes(bytes([self.ssid << 1]))
        a7[0] = self.digi and self.a7_hldc
        a7[1:3] = True  # r
        a7[7] = self.a7_hldc
        return callsign + a7.tobytes()

    def evolve(self, **kwargs) -> "Address":
        return attr.evolve(self, **kwargs)


class FrameType(enum.Enum):
    """
    Determines the type of the packet based on the control field.
    """

    U_TEST = 0xE3
    U_XID = 0xAF
    U_FRMR = 0x87
    U_SABME = 0x6F
    U_UA = 0x63
    U_DISC = 0x43
    U_SABM = 0x2F
    U_DM = 0xF
    S_SREJ = 0xD
    S_REJ = 0x9
    S_RNR = 0x5
    U_UI = 0x3
    S_RR = 0x1
    I = 0x0  # noqa: E741

    @classmethod
    def from_control_byte(cls, control: int):
        for val in cls.__members__.values():
            if control & val.value == val.value:
                return val
        raise ValueError(
            "Cannot interpret control byte {!r} as a valid AX.25 frame type."
        )


def bytes_from_int(b_or_i) -> bytes:
    if isinstance(b_or_i, int):
        return bytes([b_or_i])
    return bytes(b_or_i)


@define(frozen=True, slots=True)
class Control:
    v: bytes = field(
        validator=util.valid_length(1, 1, validators.instance_of(bytes)),
        converter=bytes_from_int,
    )
    bv: bitarray = field(init=False)
    ftype: FrameType = field(init=False)

    @bv.default
    def _bv_default(self):
        bv = bitarray()
        bv.frombytes(self.v)
        return bv

    @ftype.default
    def _ftype_default(self):
        return FrameType.from_control_byte(self.v[0])

    @property
    def n_r(self) -> int:
        return self.v[0] >> 5

    @property
    def n_s(self) -> int:
        return (self.v[0] & 0x0F) >> 1

    @property
    def p_f(self) -> bool:
        return bool(self.bv[4])

    def __bytes__(self) -> bytes:
        return self.v


def bytes_or_encode_utf8(v):
    if isinstance(v, (bytes, bytearray)):
        return bytes(v)
    return str(v).encode("utf-8")


@define(frozen=True, slots=True)
class Frame:
    """
    An AX.25 Frame.
    """

    # how large the `control` field is: 1 byte for UN frames
    CONTROL_SIZE = 1

    destination: Address
    source: Address
    path: Sequence[Address]
    control: Control = field(default=Control(UI_CONTROL_FIELD))
    pid: Optional[bytes] = field(
        default=NO_PROTOCOL_ID,
        validator=attr.validators.optional(
            util.valid_length(1, 1, validators.instance_of(bytes)),
        ),
        converter=attr.converters.optional(bytes_from_int),
    )
    info: bytes = field(default=b"", converter=bytes_or_encode_utf8)
    fcs: Optional[Union[bytes, bool]] = field(
        default=None,
        validator=attr.validators.optional(
            util.instance_of_or(
                bool, util.valid_length(2, 2, validators.instance_of(bytes))
            ),
        ),
        converter=util.optional_bool_or_bytes,
    )

    _logger = util.getLogger(__name__)

    @classmethod
    def ui(
        cls,
        destination: Union[Address, str],
        source: Union[Address, str],
        path: Optional[Sequence[Union[Address, str]]] = None,
        info: bytes = b"",
    ):
        """Create a UI frame with the given information."""
        return cls(
            destination=Address.from_any(destination),
            source=Address.from_any(source, a7_hldc=not bool(path)),
            path=[Address.from_any(p, a7_hldc=(p == path[-1])) for p in path or []],
            info=info,
        )

    @classmethod
    def from_bytes(cls, ax25_bytes: bytes) -> Sequence["Frame"]:
        """
        Decode the frame from AX.25.

        This method can handle raw AX.25 bytestream with flags and fcs values
        OR simple KISS AX.25 frames that are missing start/end flags. When
        the end flag is missing, it is assumed that the packet does not contain
        an FCS either.
        """
        packet_start = 0
        frames: List[Frame] = []
        while 0 < (packet_start + 1) < len(ax25_bytes):
            if ax25_bytes[packet_start] != AX25_FLAG:
                cls._logger.debug(
                    "AX.25 frame did not start with flag {}, got {} "
                    "instead (treating it as the start)".format(
                        bin(AX25_FLAG),
                        bin(ax25_bytes[packet_start]),
                    )
                )
            header_start = packet_start
            while ax25_bytes[header_start] == AX25_FLAG:
                # consume flag bytes until data is reached
                header_start += 1
            destination = Address.from_ax25(ax25_bytes[header_start : header_start + 7])
            source = last_address = Address.from_ax25(
                ax25_bytes[header_start + 7 : header_start + 14]
            )
            path = []
            path_start = header_start + 14
            while not last_address.a7_hldc:
                last_address = Address.from_ax25(
                    ax25_bytes[path_start : path_start + 7]
                )
                path.append(last_address)
                path_start += 7
            info_start = control_end = path_start + cls.CONTROL_SIZE
            control = Control(ax25_bytes[path_start:control_end])
            if control.ftype in (FrameType.I, FrameType.U_UI):
                info_start += 1
                pid = ax25_bytes[control_end:info_start]
            else:
                pid = None
            # find the end of the packet
            end_flag_at = packet_start = ax25_bytes.find(AX25_FLAG, info_start)
            if end_flag_at < 0:
                # assume missing Flag means no FCS
                fcs = None
                info = ax25_bytes[info_start:]
                cls._logger.debug(
                    "AX.25 frame did not end with flag {}, got {} "
                    "instead (treating it as the end)".format(
                        bin(AX25_FLAG),
                        bin(info[-1]),
                    )
                )
            else:
                fcs = ax25_bytes[end_flag_at - 2 : end_flag_at] or None
                info = ax25_bytes[info_start : end_flag_at - 2]
            frames.append(
                cls(
                    destination=destination,
                    source=source,
                    path=path,
                    control=control,
                    pid=pid,
                    info=info,
                    fcs=fcs,
                )
            )
        return frames

    from_ax25 = from_bytes

    def __bytes__(self) -> bytes:
        """Encode the frame as AX.25."""
        encoded_frame = [
            bytes(self.destination),
            bytes(self.source),
            *(bytes(p) for p in self.path),
            bytes(self.control),
        ]
        if self.control.ftype in (FrameType.I, FrameType.U_UI):
            encoded_frame.append(self.pid)
        encoded_frame.append(bytes(self.info))
        checkable_bytes = b"".join(encoded_frame)
        if not self.fcs:
            # KISS-over-TCP does not make use of fcs
            return checkable_bytes
        if self.fcs is True:
            # unthaw to set the fcs value once we know it
            object.__setattr__(self, "fcs", FCS.from_bytes(checkable_bytes).digest())
        return b"".join([AX25_FLAG_B, checkable_bytes, self.fcs, AX25_FLAG_B])

    @classmethod
    def from_str(cls, ax25_text: str) -> "Frame":
        """Decode the frame from TNC2 monitor format."""
        source_text, gt, rem = ax25_text.partition(">")
        address_field, colon, info_text = rem.partition(":")
        destination_text, *paths_text = address_field.split(",")
        path = [Address.from_text(p) for p in paths_text]
        return cls.ui(
            destination=destination_text,
            source=source_text,
            path=path,
            info=info_text.encode("latin1"),
        )

    def __str__(self) -> str:
        """Serialize the frame as TNC2 monitor format."""
        full_path = [
            str(self.destination),
            *(str(p) for p in self.path or []),
        ]
        return "%s>%s:%s" % (
            str(self.source),
            ",".join(full_path),
            bytes(self.info).decode(
                "latin1"
            ),  # XXX: maybe latin1 is a better choice...
        )
