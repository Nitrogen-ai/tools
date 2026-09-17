#!/usr/bin/env python3
"""Extract 'cover stroke' templates from a GoodNotes note file, and clone them
to new positions/uuids while keeping the opaque bv41 geometry blob byte-identical.
"""
import struct, sys, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pbdump import read_delimited_messages, try_decode_message
import pbwrite as W

def gf(fields, num):
    return [v for (n, t, v) in fields if n == num]

class StrokeTemplate:
    def __init__(self, header_raw, geom_payload_fields_raw, uuid, p1, p2, width, color_raw, bv41_raw, inner7_raw, field9_5_raw):
        self.header_raw = header_raw          # raw bytes of header top-level message
        self.uuid = uuid
        self.p1 = p1
        self.p2 = p2
        self.width = width
        self.color_raw = color_raw            # raw bytes of field4 (color) submessage
        self.bv41_raw = bv41_raw              # raw bytes of field2 (bv41 blob)
        self.inner7_raw = inner7_raw           # raw bytes of field7 (nested recognition meta) submessage
        self.field9_5_raw = field9_5_raw       # raw bytes of field9->field5 submessage

def extract_templates(note_file_path):
    with open(note_file_path, 'rb') as f:
        data = f.read()
    if len(data) == 0:
        return []
    msgs = read_delimited_messages(data)
    templates = []
    i = 0
    while i < len(msgs) - 1:
        header_raw = msgs[i]
        geom_raw = msgs[i+1]
        header_fields = try_decode_message(header_raw)
        geom_fields = try_decode_message(geom_raw)
        if header_fields is None or geom_fields is None:
            i += 1
            continue
        g7list = gf(geom_fields, 7)
        h1list = gf(header_fields, 1)
        if not g7list or not h1list:
            i += 1
            continue
        payload = try_decode_message(g7list[0])
        uuidv = gf(payload, 1)
        bv41v = gf(payload, 2)
        colorv = gf(payload, 4)
        inner7v = gf(payload, 7)
        f9v = gf(payload, 9)
        if not (uuidv and bv41v and f9v):
            i += 2
            continue
        f9d = try_decode_message(f9v[0])
        container = gf(f9d, 1)
        pts = try_decode_message(container[0]) if container else []
        ptlist = gf(pts, 1)
        if len(ptlist) < 2:
            i += 2
            continue
        p1d = try_decode_message(ptlist[0])
        p2d = try_decode_message(ptlist[1])
        p1 = (struct.unpack('<f', gf(p1d,1)[0])[0], struct.unpack('<f', gf(p1d,2)[0])[0])
        p2 = (struct.unpack('<f', gf(p2d,1)[0])[0], struct.unpack('<f', gf(p2d,2)[0])[0])
        f9_5 = gf(f9d, 5)
        wv = gf(f9d, 15)
        width = struct.unpack('<f', wv[0])[0] if wv else None
        templates.append(StrokeTemplate(
            header_raw=header_raw,
            geom_payload_fields_raw=None,
            uuid=uuidv[0].decode('utf-8'),
            p1=p1, p2=p2, width=width,
            color_raw=colorv[0] if colorv else b'',
            bv41_raw=bv41v[0],
            inner7_raw=inner7v[0] if inner7v else b'',
            field9_5_raw=f9_5[0] if f9_5 else b'',
        ))
        i += 2
    return templates

def build_stroke_pair(template, new_uuid, new_p1, new_p2, random_int, small_counter,
                       device_id_const, layer_id_const, color_raw_override=None):
    """Return (header_bytes, geometry_bytes) both as delimited (length-prefixed) messages,
    ready to be concatenated directly into a notes/<uuid> file.

    color_raw_override, if given, replaces the template's own captured color (field 4)
    while keeping everything else (bv41 geometry blob, width, recognition metadata)
    byte-identical to the template. Verified safe: a real GoodNotes file was found
    with both blue and white cover strokes sharing byte-identical bv41 blobs at the
    same width, differing only in field 4 (color) and field 7 (recognition metadata,
    not reproduced here since it's already handled as inner7_raw from the template)."""
    # ---- header ----
    header_payload = b''
    header_payload += W.field_string(1, new_uuid)
    header_payload += W.field_message(2, W.field_varint(1, 10) + W.field_varint(2, random_int))
    header_payload += W.field_string(6, new_uuid)
    header_payload += W.field_varint(8, device_id_const)
    header_payload += W.field_varint(9, small_counter)
    header_payload += W.field_varint(14, layer_id_const)
    header_payload += W.field_varint(16, 24)

    # ---- geometry ----
    p1x, p1y = new_p1
    p2x, p2y = new_p2
    pts_container = (
        W.field_message(1, W.field_fixed32_float(1, p1x) + W.field_fixed32_float(2, p1y)) +
        W.field_message(1, W.field_fixed32_float(1, p2x) + W.field_fixed32_float(2, p2y)))
    f9 = W.field_message(1, pts_container)
    if template.field9_5_raw:
        f9 += W.field_message(5, template.field9_5_raw)
    if template.width is not None:
        f9 += W.field_fixed32_float(15, template.width)

    payload = b''
    payload += W.field_string(1, new_uuid)
    payload += W.field_bytes(2, template.bv41_raw)
    color_raw = color_raw_override if color_raw_override is not None else template.color_raw
    if color_raw:
        payload += W.field_message(4, color_raw)
    payload += W.field_string(6, '')
    if template.inner7_raw:
        payload += W.field_message(7, template.inner7_raw)
    payload += W.field_message(9, f9)
    payload += W.field_message(15, W.field_varint(1, 10) + W.field_varint(2, random_int))
    payload += W.field_string(20, '')
    payload += W.field_varint(21, 24)

    geometry_outer = W.field_message(7, payload)

    return W.delimited(header_payload), W.delimited(geometry_outer)


if __name__ == '__main__':
    TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
    tpls = extract_templates(f"{TEMPLATE_DIR}/notes/319A0E34-AD58-5F63-9E40-DF28F9B60AE4")
    tpls += extract_templates(f"{TEMPLATE_DIR}/notes/25E8EBC7-2742-53D5-A382-63DE44D29E86")
    widths = sorted(set(round(t.width, 3) for t in tpls))
    print(f"{len(tpls)} templates, distinct widths: {widths}")
    for w in widths:
        example = next(t for t in tpls if round(t.width,3) == w)
        print(f"  width={w}: bv41_len={len(example.bv41_raw)} inner7_len={len(example.inner7_raw)}")
