#!/usr/bin/env python3
"""Build an index.events.pb byte stream for a fresh GoodNotes document,
structurally cloned from the pattern observed in a real GoodNotes-authored file:
  30 = CreateDocument
  6  = AddAttachment
  2  = AddPage
  54 = CreateNoteVersion (pre-commit)
  102 = CommitNoteContent (final, matches notes/<uuid> file)
  10  = PagingViewServiceUpdater (last-viewed-page marker)
"""
import sys, os, random, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pbwrite as W

DEVICE_CONST = 3217826306554175947  # opaque per-device id, reused verbatim from the source document
SCHEMA_VERSION = 24

def id_pair(const1, randval):
    return W.field_varint(1, const1) + W.field_varint(2, randval)

def rand32():
    return random.randint(1, 2**32 - 1)

def now_ms():
    return int(time.time() * 1000)

class EventsBuilder:
    def __init__(self, doc_id, title, viewport_transform_raw):
        self.doc_id = doc_id
        self.title = title
        self.viewport_transform_raw = viewport_transform_raw
        self.seq = 1
        self.out = bytearray()
        # Real GoodNotes events are timestamped at human editing speed, so their
        # field-10 timestamps are always strictly increasing and never tie. This
        # builder emits a whole document in milliseconds, so a wall-clock timestamp
        # can easily collide or land out of order between events - which GoodNotes
        # appears to use (at least as a tie-breaker) for page display order, causing
        # pages to occasionally come out shuffled/reversed. Force strict monotonic
        # increase by hand instead of trusting time.time() resolution.
        self._ts_base_ms = now_ms()
        self._ts_counter = 0

    def _ts(self):
        import struct
        val = self._ts_base_ms + self._ts_counter
        self._ts_counter += 1
        return struct.pack('<d', float(val))

    def add_create_document(self):
        payload = b''
        payload += W.field_string(1, self.doc_id)
        payload += W.field_message(2, W.field_string(1, self.title) + W.field_message(2, id_pair(1, rand32())))
        payload += W.field_message(3, W.field_string(1, str(__import__('uuid').uuid4()).upper()) + W.field_message(2, id_pair(1, rand32())))
        payload += W.field_message(6, W.field_string(1, 'P') + W.field_message(2, id_pair(1, rand32())))
        payload += W.field_message(7, W.field_string(1, str(__import__('uuid').uuid4()).upper()) + W.field_message(2, id_pair(1, rand32())))
        payload += W.field_string(9, 'de_DE')
        payload += W.field_fixed64(10, self._ts())
        payload += W.field_string(11, str(__import__('uuid').uuid4()).upper())
        payload += W.field_varint(13, DEVICE_CONST)
        payload += W.field_varint(14, self.seq); self.seq += 1
        payload += W.field_string(17, '')
        payload += W.field_string(18, '')
        payload += W.field_message(19, W.field_message(2, id_pair(1, rand32())))
        payload += W.field_varint(20, SCHEMA_VERSION)
        msg = W.field_string(1, self.doc_id) + W.field_message(30, payload)
        self.out += W.delimited(msg)

    def add_attachment(self, attachment_id, file_uuid, filesize):
        payload = b''
        payload += W.field_string(1, attachment_id)
        payload += W.field_string(2, file_uuid)
        payload += W.field_varint(5, filesize)
        payload += W.field_string(6, self.doc_id)
        payload += W.field_fixed64(10, self._ts())
        payload += W.field_string(11, str(__import__('uuid').uuid4()).upper())
        payload += W.field_message(12, W.field_varint(1, 1) + W.field_varint(2, 1))
        payload += W.field_varint(14, DEVICE_CONST)
        payload += W.field_varint(15, self.seq); self.seq += 1
        payload += W.field_varint(16, SCHEMA_VERSION)
        msg = W.field_string(1, attachment_id) + W.field_message(6, payload)
        self.out += W.delimited(msg)

    def add_page(self, page_id, attachment_id, page_index, width_canvas, height_canvas):
        # field 5 is the 1-based page index WITHIN the referenced attachment PDF, not
        # an arbitrary/constant value. This was misread as "always 1" from an earlier
        # source document where every page had its own dedicated single-page
        # attachment (so the in-attachment index was trivially always 1 there too).
        # A real multi-page import confirmed it: one shared multi-page attachment,
        # and each AddPage's field 5 was the actual 1-based page number within it.
        # This field is very likely the actual page-ordering signal GoodNotes uses -
        # generating one single-page attachment per page (as this generator did
        # before) gave GoodNotes no explicit, unambiguous way to order pages that
        # each reference a *different* attachment, which lines up with the
        # intermittent page-order bug seen when every page got field 5 = 1.
        payload = b''
        payload += W.field_string(1, self.doc_id)
        payload += W.field_string(2, page_id)
        payload += W.field_string(4, attachment_id)
        payload += W.field_varint(5, page_index)
        payload += W.field_message(8, W.field_fixed32_float(1, width_canvas) + W.field_fixed32_float(2, height_canvas))
        payload += W.field_fixed64(10, self._ts())
        payload += W.field_string(11, str(__import__('uuid').uuid4()).upper())
        payload += W.field_message(12, W.field_message(2, id_pair(1, rand32())))
        payload += W.field_message(13, W.field_message(2, id_pair(1, rand32())))
        payload += W.field_varint(15, DEVICE_CONST)
        payload += W.field_varint(16, self.seq); self.seq += 1
        payload += W.field_message(17, W.field_message(2, id_pair(1, rand32())))
        payload += W.field_message(19, W.field_message(2, id_pair(1, rand32())))
        payload += W.field_varint(21, SCHEMA_VERSION)
        msg = W.field_string(1, page_id) + W.field_message(2, payload)
        self.out += W.delimited(msg)

    def add_note_version(self, temp_note_id, page_id, short_token):
        payload = b''
        payload += W.field_string(1, self.doc_id)
        payload += W.field_string(2, temp_note_id)
        payload += W.field_message(3, W.field_string(1, page_id) + W.field_message(2, id_pair(1, rand32())))
        payload += W.field_message(4, W.field_string(1, short_token) + W.field_message(2, id_pair(1, rand32())))
        payload += W.field_fixed64(10, self._ts())
        payload += W.field_string(11, str(__import__('uuid').uuid4()).upper())
        payload += W.field_varint(13, DEVICE_CONST)
        payload += W.field_varint(14, self.seq); self.seq += 1
        payload += W.field_varint(15, SCHEMA_VERSION)
        if self.viewport_transform_raw:
            payload += W.field_message(17, self.viewport_transform_raw)
        msg = W.field_string(1, temp_note_id) + W.field_message(54, payload)
        self.out += W.delimited(msg)

    def commit_note(self, final_note_id):
        payload = b''
        payload += W.field_string(1, final_note_id)
        payload += W.field_fixed64(10, self._ts())
        payload += W.field_string(11, str(__import__('uuid').uuid4()).upper())
        payload += W.field_varint(13, DEVICE_CONST)
        payload += W.field_varint(14, self.seq); self.seq += 1
        payload += W.field_varint(15, SCHEMA_VERSION)
        payload += W.field_string(16, self.doc_id)
        msg = W.field_string(1, final_note_id) + W.field_message(102, payload)
        self.out += W.delimited(msg)

    def close_view(self, last_temp_note_id):
        payload = b''
        payload += W.field_string(1, self.doc_id)
        payload += W.field_string(2, last_temp_note_id)
        payload += W.field_string(3, 'PagingViewServiceUpdater:' + str(__import__('uuid').uuid4()).upper())
        payload += W.field_fixed64(10, self._ts())
        payload += W.field_string(11, str(__import__('uuid').uuid4()).upper())
        payload += W.field_varint(13, DEVICE_CONST)
        payload += W.field_varint(14, self.seq); self.seq += 1
        payload += W.field_varint(15, SCHEMA_VERSION)
        msg = W.field_string(1, self.doc_id) + W.field_message(10, payload)
        self.out += W.delimited(msg)

    def bytes(self):
        return bytes(self.out)
