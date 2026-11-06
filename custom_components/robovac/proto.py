# Copyright 2022 Brendan McCluskey
# Copyright (c) 2026 Dave Harvey
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Minimal schema-less protobuf codec for the L60's base64 DPS values.

The L60 sends many DPS (152, 153, 157, 178...) as base64 of a length byte
followed by a protobuf message. This decodes to ``{field_no: value}`` dicts
(repeated fields become lists) and encodes the same subset back. No Home
Assistant imports, so it stays unit-testable.
"""

from __future__ import annotations

import base64
import binascii
from typing import Any

VARINT, FIXED64, LENGTH, FIXED32 = 0, 1, 2, 5
MAX_DEPTH = 6


class ProtoError(ValueError):
    """The bytes are not a well-formed message of the supported subset."""


def _read_varint(data: bytes, pos: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        if pos >= len(data) or shift > 63:
            raise ProtoError("truncated or oversized varint")
        byte = data[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7


def _write_varint(value: int) -> bytes:
    if value < 0:
        raise ProtoError("negative varints are not supported")
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def decode_message(
    data: bytes, depth: int = 0, nested: bool = True
) -> dict[int, Any]:
    """Decode one message. With ``nested``, length-delimited fields that are
    themselves valid non-empty messages become dicts; everything else (and
    every field when ``nested`` is off) stays bytes."""
    fields: dict[int, Any] = {}
    pos = 0
    while pos < len(data):
        tag, pos = _read_varint(data, pos)
        number, wire = tag >> 3, tag & 7
        if number == 0:
            raise ProtoError("field number 0")
        if wire == VARINT:
            value, pos = _read_varint(data, pos)
        elif wire in (FIXED64, FIXED32):
            size = 8 if wire == FIXED64 else 4
            if pos + size > len(data):
                raise ProtoError("truncated fixed field")
            value = int.from_bytes(data[pos : pos + size], "little")
            pos += size
        elif wire == LENGTH:
            size, pos = _read_varint(data, pos)
            if pos + size > len(data):
                raise ProtoError("truncated length-delimited field")
            raw = data[pos : pos + size]
            pos += size
            value = raw
            if nested and raw and depth < MAX_DEPTH:
                try:
                    value = decode_message(raw, depth + 1)
                except ProtoError:
                    value = raw
        else:
            raise ProtoError(f"unsupported wire type {wire}")
        if number in fields:
            existing = fields[number]
            if isinstance(existing, list):
                existing.append(value)
            else:
                fields[number] = [existing, value]
        else:
            fields[number] = value
    return fields


def decode_prefixed(raw: str | bytes, nested: bool = True) -> dict[int, Any]:
    """Decode a base64 DPS value: one length byte(s), then the message."""
    try:
        data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as err:
        raise ProtoError("not base64") from err
    length, pos = _read_varint(data, 0)
    if length != len(data) - pos:
        raise ProtoError("length prefix does not match payload")
    return decode_message(data[pos:], nested=nested)


def try_decode(value: Any) -> dict[int, Any] | None:
    """decode_prefixed for logging: None for anything that is not a message."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return decode_prefixed(value)
    except ProtoError:
        return None


def _encode_field(number: int, value: Any) -> bytes:
    if isinstance(value, bool):
        value = int(value)
    if isinstance(value, int):
        return _write_varint(number << 3 | VARINT) + _write_varint(value)
    if isinstance(value, dict):
        value = encode_message(value)
    elif isinstance(value, str):
        value = value.encode()
    if isinstance(value, bytes | bytearray):
        return _write_varint(number << 3 | LENGTH) + _write_varint(len(value)) + bytes(value)
    raise ProtoError(f"cannot encode {type(value).__name__}")


def encode_message(fields: dict[int, Any]) -> bytes:
    out = bytearray()
    for number, value in fields.items():
        for item in value if isinstance(value, list) else [value]:
            out += _encode_field(number, item)
    return bytes(out)


def encode_prefixed(fields: dict[int, Any]) -> str:
    """Encode to the base64 length-prefixed form the vacuum expects."""
    body = encode_message(fields)
    return base64.b64encode(_write_varint(len(body)) + body).decode("ascii")
