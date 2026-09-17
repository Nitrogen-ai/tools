#!/usr/bin/env python3
"""Generic recursive protobuf wire-format decoder (no schema needed).
Produces a nested python structure. Length-delimited fields are tried as
sub-messages first; if that fails, treated as string (if valid utf8) else raw bytes.
"""
import struct, sys, json, binascii

def read_varint(buf, pos):
    result = 0
    shift = 0
    start = pos
    while True:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7f) << shift
        if not (b & 0x80):
            break
        shift += 7
    return result, pos

def try_decode_message(buf):
    """Try to fully parse buf as a sequence of protobuf fields. Return list of (field_no, wiretype, value) or None on failure."""
    pos = 0
    fields = []
    n = len(buf)
    if n == 0:
        return []
    while pos < n:
        try:
            tag, pos = read_varint(buf, pos)
        except IndexError:
            return None
        field_no = tag >> 3
        wire_type = tag & 7
        if field_no == 0:
            return None
        if wire_type == 0:  # varint
            try:
                val, pos = read_varint(buf, pos)
            except IndexError:
                return None
            fields.append((field_no, 'varint', val))
        elif wire_type == 1:  # fixed64
            if pos + 8 > n: return None
            raw = buf[pos:pos+8]
            pos += 8
            fields.append((field_no, 'fixed64', raw))
        elif wire_type == 2:  # length-delimited
            try:
                length, pos = read_varint(buf, pos)
            except IndexError:
                return None
            if pos + length > n:
                return None
            raw = buf[pos:pos+length]
            pos += length
            fields.append((field_no, 'bytes', raw))
        elif wire_type == 5:  # fixed32
            if pos + 4 > n: return None
            raw = buf[pos:pos+4]
            pos += 4
            fields.append((field_no, 'fixed32', raw))
        else:
            return None  # unsupported wire type (groups etc.) - bail
    return fields

def render_bytes_field(raw, depth):
    # try sub-message
    sub = try_decode_message(raw)
    if sub is not None and len(sub) > 0:
        # heuristic: require this actually look "real" -- all field numbers reasonable, wiretypes consistent
        return render_fields(sub, depth+1)
    # try utf8 string
    try:
        s = raw.decode('utf-8')
        if all(c.isprintable() or c in '\n\t' for c in s):
            return {'__str__': s}
    except UnicodeDecodeError:
        pass
    return {'__hex__': binascii.hexlify(raw).decode(), '__len__': len(raw)}

def render_fields(fields, depth=0):
    out = []
    for field_no, wtype, val in fields:
        if wtype == 'varint':
            out.append((field_no, wtype, val))
        elif wtype == 'fixed64':
            f = struct.unpack('<d', val)[0]
            i = struct.unpack('<q', val)[0]
            out.append((field_no, wtype, {'double': f, 'int64': i, 'hex': binascii.hexlify(val).decode()}))
        elif wtype == 'fixed32':
            f = struct.unpack('<f', val)[0]
            i = struct.unpack('<i', val)[0]
            out.append((field_no, wtype, {'float': f, 'int32': i, 'hex': binascii.hexlify(val).decode()}))
        elif wtype == 'bytes':
            out.append((field_no, wtype, render_bytes_field(val, depth)))
    return out

def pretty(fields, indent=0):
    lines = []
    pad = '  ' * indent
    for field_no, wtype, val in fields:
        if wtype == 'varint':
            lines.append(f"{pad}{field_no} (varint): {val}")
        elif wtype in ('fixed64', 'fixed32'):
            lines.append(f"{pad}{field_no} ({wtype}): {val}")
        elif wtype == 'bytes':
            if isinstance(val, list):
                lines.append(f"{pad}{field_no} (message):")
                lines.append(pretty(val, indent+1))
            elif '__str__' in val:
                lines.append(f"{pad}{field_no} (string): {val['__str__']!r}")
            else:
                lines.append(f"{pad}{field_no} (bytes len={val['__len__']}): {val['__hex__']}")
    return '\n'.join(lines)

def read_delimited_messages(data):
    pos = 0
    msgs = []
    n = len(data)
    while pos < n:
        length, pos = read_varint(data, pos)
        chunk = data[pos:pos+length]
        pos += length
        msgs.append(chunk)
    return msgs

if __name__ == '__main__':
    path = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else 'delimited'
    with open(path, 'rb') as f:
        data = f.read()
    if mode == 'delimited':
        msgs = read_delimited_messages(data)
        for i, m in enumerate(msgs):
            print(f"=== message {i} (len={len(m)}) ===")
            fields = try_decode_message(m)
            if fields is None:
                print("  <failed to parse>")
                continue
            rendered = render_fields(fields)
            print(pretty(rendered))
    else:
        fields = try_decode_message(data)
        rendered = render_fields(fields)
        print(pretty(rendered))
