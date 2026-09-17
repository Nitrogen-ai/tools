#!/usr/bin/env python3
"""Generate a GoodNotes .goodnotes presentation file from a solution PDF: the
solution PDF becomes the page background, and every detected answer gets an
opaque white 'cover bar' stroke (cloned from real GoodNotes stroke templates,
recolored to match a real hand-painted white cover) that a teacher can erase
live in GoodNotes to reveal the answer for comparison.

Two ways to detect which text is "the answer":
  - diff mode (default): supply a blank worksheet PDF: any text present in the
    solution PDF but not the blank one, per line, is an answer.
  - color mode (--color RRGGBB): for worksheets where the answer text is baked
    into a single PDF in a distinct color (e.g. a publisher's pink/magenta
    answer-key text) instead of there being a separate blank PDF at all. No
    blank PDF is needed or used in this mode.
"""
import sys, os, uuid, random, zipfile, struct, tempfile, re
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import fitz
import pbwrite as W
from pbdump import read_delimited_messages, try_decode_message
import strokes as S
from diff_pdfs import diff_page, diff_drawings
from color_answers import find_colored_spans
from events_builder import EventsBuilder, DEVICE_CONST, SCHEMA_VERSION, rand32

SCALE = 11 / 6
TEMPLATE_DIR = os.path.join(SCRIPT_DIR, 'templates')

AVAILABLE_WIDTHS = [6.707, 6.896, 7.795, 10.375, 10.732, 14.2, 23.498]

# Extracted from a real GoodNotes file with hand-painted white cover strokes
# (Chemie Q1 01 Atombau_II, notes/1C18A40E...): RGBA (0.9882353, 0.9882353,
# 0.9882353, 1.0), i.e. #FCFCFC, not literal pure #FFFFFF. Verified byte-exact
# against the real file's field-4 color bytes. A same-width blue and white
# stroke in that file had byte-identical bv41 geometry blobs, confirming color
# can be swapped independently of the cloned template's geometry.
WHITE_COLOR = (W.field_fixed32_float(1, 0.9882352941176471) +
               W.field_fixed32_float(2, 0.9882352941176471) +
               W.field_fixed32_float(3, 0.9882352941176471) +
               W.field_fixed32_float(4, 1.0))

def new_uuid():
    return str(uuid.uuid4()).upper()

def increment_uuid_hex(u):
    """GoodNotes derives a note's final 'committed' id from its pre-commit ('54') temp
    id by incrementing the id's 128-bit hex value by 1 (verified against 3/3 real
    examples in the source document, including a content-less page). The commit ('102')
    event must reference this exact derived id or GoodNotes silently rejects the note
    content (while still applying the page/attachment events that came before it)."""
    hexval = int(u.replace('-', ''), 16) + 1
    h = format(hexval, '032X')
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"

def gf(fields, num):
    return [v for (n, t, v) in fields if n == num]

def extract_viewport_transform():
    """Pull the '54'->field17 viewport/zoom transform block verbatim from the template events.pb."""
    with open(f"{TEMPLATE_DIR}/index.events.pb", 'rb') as f:
        data = f.read()
    msgs = read_delimited_messages(data)
    for m in msgs:
        fields = try_decode_message(m)
        f54 = gf(fields, 54)
        if f54:
            payload = try_decode_message(f54[0])
            f17 = gf(payload, 17)
            if f17:
                return f17[0]
    return b''

def load_stroke_templates():
    tpls = []
    for fname in ["319A0E34-AD58-5F63-9E40-DF28F9B60AE4", "25E8EBC7-2742-53D5-A382-63DE44D29E86"]:
        tpls += S.extract_templates(f"{TEMPLATE_DIR}/notes/{fname}")
    by_width = {}
    for t in tpls:
        w = round(t.width, 3)
        if w not in by_width:
            by_width[w] = t
    return by_width

MAX_STROKE_WIDTH = max(AVAILABLE_WIDTHS)

def pick_width(height_canvas, by_width):
    """Pick the smallest available template whose width fully covers height_canvas,
    not just mostly covers it - the user asked for exact, complete coverage of every
    detected answer pixel, not a visually-snug-but-partial bar. Only text spans (short,
    single-line) reliably fit in one bar; taller graphical spans are tiled by the
    caller instead of ever falling back to an under-covering single bar here."""
    candidates = [w for w in AVAILABLE_WIDTHS if w >= height_canvas]
    if candidates:
        return by_width[min(candidates)]
    return by_width[MAX_STROKE_WIDTH]

def build_note_file(spans, by_width, device_id_const, layer_id_const):
    """spans: list of dicts with x0,y0,x1,y1 in PDF top-left points."""
    out = bytearray()
    counter = 1000 + random.randint(0, 500)
    max_tpl = by_width[MAX_STROKE_WIDTH]
    for s in spans:
        cx0, cy0 = s['x0'] * SCALE, s['y0'] * SCALE
        cx1, cy1 = s['x1'] * SCALE, s['y1'] * SCALE
        pad_x = 3.0
        cx0 -= pad_x
        cx1 += pad_x
        height = cy1 - cy0

        if height <= MAX_STROKE_WIDTH:
            bars = [(pick_width(height, by_width), (cy0 + cy1) / 2)]
        else:
            # No single available stroke width is tall enough (this generator's widest
            # bundled template is ~12.8pt in PDF space) - happens for graphical answers
            # taller than one text line, e.g. a whole sketched spectrum bar. A single
            # centered bar at max width would only cover a fraction of the height and
            # leave the rest of the answer visible before any erasing - confirmed by
            # the user seeing partially-visible spectra. Tile full-width bars down the
            # whole height instead, overlapping slightly so there's no seam between them.
            overlap = 2.0
            step = MAX_STROKE_WIDTH - overlap
            centers = [cy0 + MAX_STROKE_WIDTH / 2]
            while centers[-1] + MAX_STROKE_WIDTH / 2 < cy1:
                centers.append(centers[-1] + step)
            bars = [(max_tpl, c) for c in centers]

        for tpl, cy_mid in bars:
            p1 = (cx0, cy_mid)
            p2 = (cx1, cy_mid)
            stroke_uuid = new_uuid()
            random_int = rand32()
            header, geom = S.build_stroke_pair(
                tpl, new_uuid=stroke_uuid, new_p1=p1, new_p2=p2,
                random_int=random_int, small_counter=counter,
                device_id_const=device_id_const, layer_id_const=layer_id_const,
                color_raw_override=WHITE_COLOR)
            out += header
            out += geom
            counter += 1
    return bytes(out)

def check_printed_page_order(sol):
    """Sanity check suggested by the user after a reported page-order bug: this
    generator trusts the source PDF's physical page order (fitz iteration order) to
    already be the intended reading order. Most of this tool's worksheets print a
    'Seite N' footer, which is independent ground truth for what the intended order
    actually is - if the physical PDF page order and the printed footer numbers ever
    disagree, that's a real problem with the *source* PDF (e.g. pages reordered by a
    prior edit) that would otherwise silently produce a wrong-order .goodnotes file.
    Best-effort only: not every worksheet has this footer, so a page with no match is
    silently skipped rather than treated as a mismatch."""
    numbers = []
    for pno in range(sol.page_count):
        m = re.search(r'Seite\s*(\d+)', sol[pno].get_text())
        numbers.append((pno, int(m.group(1)) if m else None))
    found = [(pno, n) for pno, n in numbers if n is not None]
    if len(found) < 2:
        return
    expected_step = found[0][1] - found[0][0]
    mismatches = [(pno, n) for pno, n in found if n - pno != expected_step]
    if mismatches:
        print(f"  WARNING: printed 'Seite N' footer order disagrees with physical "
              f"PDF page order at: {mismatches} - the source PDF's pages may be "
              f"out of order; the generated .goodnotes will follow physical PDF "
              f"order and will likely display pages in the wrong sequence.")

def render_thumbnail(pdf_path, out_path, page_no=0, max_dim=400):
    doc = fitz.open(pdf_path)
    page = doc[page_no]
    rect = page.rect
    zoom = max_dim / max(rect.width, rect.height)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    pix.save(out_path)

def build_document(blank_pdf_path, solution_pdf_path, title, output_path, answer_color=None, color_tolerance=40, grid=False):
    device_id_const = DEVICE_CONST
    layer_id_const = 5381  # opaque per-document constant, reused verbatim from the source document

    blank = fitz.open(blank_pdf_path) if blank_pdf_path else None
    sol = fitz.open(solution_pdf_path)
    check_printed_page_order(sol)
    by_width = load_stroke_templates()
    viewport_transform = extract_viewport_transform()

    doc_id = new_uuid()
    eb = EventsBuilder(doc_id, title, viewport_transform)
    eb.add_create_document()

    index_attachments = bytearray()
    index_notes = bytearray()
    zip_members = {}  # path -> bytes

    # A real, native multi-page GoodNotes import embeds the WHOLE solution PDF as a
    # single shared attachment, and each page's AddPage event references it with an
    # explicit 1-based page_index (field 5) into that attachment - confirmed by
    # diffing a genuinely native multi-page .goodnotes export. This generator used
    # to split the PDF into one single-page attachment per page (each trivially
    # "page 1 of its own attachment"), which gave GoodNotes no explicit, unambiguous
    # signal for page order across multiple independent attachments - the likely
    # root cause of the page-order bug documented in CLAUDE.md. Embedding one shared
    # attachment with real page indices is both more faithful to native behavior and
    # should give GoodNotes an explicit order to key off.
    attachment_id = new_uuid()
    file_uuid = new_uuid()
    # garbage=4,clean=True repairs malformed PDFs (e.g. an invalid dict key seen in
    # one real worksheet) that would otherwise make tobytes() raise a syntax error.
    pdf_bytes = sol.tobytes(deflate=True, garbage=4, clean=True)
    zip_members[f"attachments/{file_uuid}"] = pdf_bytes
    index_attachments += W.delimited(
        W.field_string(1, attachment_id) + W.field_string(2, f"attachments/{file_uuid}"))
    eb.add_attachment(attachment_id, file_uuid, len(pdf_bytes))

    # Three separate batches (AddPage for every page, then CreateNoteVersion for
    # every page, then CommitNoteContent only for pages with actual ink), each
    # emitted as one contiguous block, not interleaved per page. Confirmed against
    # two independently hand-created, correctly-ordered reference documents (whose
    # page order the user verified on-device): both show this exact three-block
    # shape (2,2,2,2, 54,54,54,54, 102,102,...), never AddPage/NoteVersion/Commit
    # interleaved per page like this generator used to do. That interleaving is the
    # most likely real cause of the page-order bug (see CLAUDE.md "Page order").
    pages = []  # (pno, page_id)
    for pno in range(sol.page_count):
        page = sol[pno]
        rect = page.rect
        width_canvas = rect.width * SCALE
        height_canvas = rect.height * SCALE
        page_id = new_uuid()
        eb.add_page(page_id, attachment_id, pno + 1, width_canvas, height_canvas)
        pages.append((pno, page_id))

    first_temp_note_id = None
    temp_ids = {}  # pno -> temp_note_id
    for pno, page_id in pages:
        temp_note_id = new_uuid()
        temp_ids[pno] = temp_note_id
        if first_temp_note_id is None:
            first_temp_note_id = temp_note_id
        short_token = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789', k=5))
        eb.add_note_version(temp_note_id, page_id, short_token)

    for pno, page_id in pages:
        page = sol[pno]
        temp_note_id = temp_ids[pno]
        final_note_id = increment_uuid_hex(temp_note_id)

        # --- find answers on this page and build strokes ---
        if answer_color is not None:
            spans = find_colored_spans(page, answer_color, tolerance=color_tolerance)
        elif blank is not None and pno < blank.page_count:
            # Text diff catches typed-in answers; drawing diff catches answers drawn
            # as vector graphics instead (sketched spectra, occupied-orbital arrows,
            # etc.) that diff_page() can't see at all since it only looks at PDF text.
            if grid:
                # See diff_pdfs.diff_drawings' docstring and CLAUDE.md's "Grid mode":
                # a table/timetable/seating-chart needs neutral-grey exclusion (not
                # just near-white) and no clustering (each colored cell is already an
                # exact rect; merging fuses whole edge-to-edge rows into oversized
                # boxes). neutral_spread=0.05 was picked against Klassenplan 9-1: its
                # structural grey is a spread of 0, its narrowest genuine subject
                # color a spread of ~0.17, so 0.05 separates them with margin on both
                # sides - re-check with a per-page print of drawing fill spreads before
                # trusting it blind on a differently-styled grid document.
                spans = diff_page(blank[pno], page) + diff_drawings(blank[pno], page, neutral_spread=0.05, cluster=False)
            else:
                spans = diff_page(blank[pno], page) + diff_drawings(blank[pno], page)
        else:
            spans = []

        # Confirmed in both reference documents: a page with zero detected answers
        # gets its CreateNoteVersion (above) but NO CommitNoteContent event at all -
        # only pages with actual strokes are committed. The empty note still gets an
        # index.notes.pb entry (0-byte file) under the same temp_id+1 final id, it's
        # just never referenced by a 102 event. This generator previously committed
        # every page unconditionally, another divergence from real files that likely
        # contributed to the page-order bug.
        if spans:
            eb.commit_note(final_note_id)
            note_bytes = build_note_file(spans, by_width, device_id_const, layer_id_const)
        else:
            note_bytes = b''
        zip_members[f"notes/{final_note_id}"] = note_bytes
        index_notes += W.delimited(
            W.field_string(1, final_note_id) + W.field_string(2, f"notes/{final_note_id}"))

        print(f"  page {pno+1}: {len(spans)} answer(s) covered -> notes/{final_note_id}")

    eb.close_view(first_temp_note_id)

    zip_members["index.attachments.pb"] = bytes(index_attachments)
    zip_members["index.notes.pb"] = bytes(index_notes)
    zip_members["index.events.pb"] = eb.bytes()
    zip_members["index.search.pb"] = b''
    zip_members["schema.pb"] = W.field_varint(1, SCHEMA_VERSION)

    thumb_path = os.path.join(tempfile.gettempdir(), f"_goodnotes_thumb_{uuid.uuid4().hex}.jpg")
    render_thumbnail(solution_pdf_path, thumb_path)
    with open(thumb_path, 'rb') as f:
        zip_members["thumbnail.jpg"] = f.read()
    os.remove(thumb_path)

    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for name, data in zip_members.items():
            zf.writestr(name, data)

    print(f"Wrote {output_path} ({os.path.getsize(output_path)} bytes)")

if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('blank_pdf', nargs='?', default=None,
                     help='Blank worksheet PDF (omit when using --color)')
    ap.add_argument('solution_pdf')
    ap.add_argument('title')
    ap.add_argument('output')
    ap.add_argument('--color', metavar='RRGGBB',
                     help='Detect answers by text color instead of diffing against a blank PDF '
                          '(e.g. --color EC008C for a pink/magenta answer key). blank_pdf is not needed.')
    ap.add_argument('--color-tolerance', type=int, default=40,
                     help='Euclidean RGB distance allowed when matching --color (default 40)')
    ap.add_argument('--grid', action='store_true',
                     help='Grid mode: for a table/timetable/seating-chart blank+solution pair '
                          '(not an ordinary worksheet) whose colored cells sit edge-to-edge across '
                          'whole rows and whose structural header/row-label cells use a neutral '
                          'mid-grey fill rather than near-white. Excludes neutral/grayscale fills '
                          'from being covered (not just near-white ones) and covers each colored '
                          'cell as its own precise rect instead of merging touching cells into one '
                          'oversized box. Requires blank_pdf (diff mode); incompatible with --color. '
                          'See CLAUDE.md\'s "Grid mode" section, built for Klassenplan 9-1.')
    args = ap.parse_args()

    if args.color and args.blank_pdf:
        ap.error("pass either blank_pdf (diff mode) or --color (color mode), not both")
    if not args.color and not args.blank_pdf:
        ap.error("need either blank_pdf (diff mode) or --color (color mode)")
    if args.grid and args.color:
        ap.error("--grid is a diff-mode-only refinement, incompatible with --color")

    answer_color = None
    if args.color:
        hexs = args.color.lstrip('#')
        answer_color = tuple(int(hexs[i:i+2], 16) for i in (0, 2, 4))

    build_document(args.blank_pdf, args.solution_pdf, args.title, args.output,
                    answer_color=answer_color, color_tolerance=args.color_tolerance, grid=args.grid)
