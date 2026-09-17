#!/usr/bin/env python3
"""Minimal protobuf wire-format writer to complement pbdump.py's reader."""
import struct

def varint(n):
    out = bytearray()
    while True:
        b = n & 0x7f
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)

def tag(field_no, wire_type):
    return varint((field_no << 3) | wire_type)

def field_varint(field_no, value):
    return tag(field_no, 0) + varint(value)

def field_fixed32(field_no, raw4):
    assert len(raw4) == 4
    return tag(field_no, 5) + raw4

def field_fixed32_float(field_no, fval):
    return field_fixed32(field_no, struct.pack('<f', fval))

def field_fixed64(field_no, raw8):
    assert len(raw8) == 8
    return tag(field_no, 1) + raw8

def field_bytes(field_no, raw):
    return tag(field_no, 2) + varint(len(raw)) + raw

def field_string(field_no, s):
    return field_bytes(field_no, s.encode('utf-8'))

def field_message(field_no, submsg_bytes):
    return field_bytes(field_no, submsg_bytes)

def delimited(msg_bytes):
    """Prefix a message with its varint length, for the outer note-file / index-file framing."""
    return varint(len(msg_bytes)) + msg_bytes
