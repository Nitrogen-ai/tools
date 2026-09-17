#!/usr/bin/env python3
"""Diff a blank worksheet PDF against its solution (Lösungsblatt) PDF to find
newly-added text runs and their bounding boxes (PDF top-left-origin points),
clustered into per-line spans."""
import fitz
import difflib
from collections import Counter

def page_words(page):
    # (x0,y0,x1,y1, text, block, line, word_no)
    return page.get_text("words")

def diff_page(blank_page, sol_page):
    bw = [w[4] for w in page_words(blank_page)]
    sw_full = page_words(sol_page)
    sw = [w[4] for w in sw_full]
    sm = difflib.SequenceMatcher(None, bw, sw, autojunk=False)
    added_word_indices = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ('insert', 'replace'):
            added_word_indices.extend(range(j1, j2))
    # cluster consecutive added-word indices that are on the same line (block,line) into spans
    spans = []
    cur = None
    for idx in added_word_indices:
        w = sw_full[idx]
        x0, y0, x1, y1, text, block, line, wordno = w
        key = (block, line)
        if cur and cur['key'] == key and idx == cur['last_idx'] + 1:
            cur['x1'] = x1
            cur['y0'] = min(cur['y0'], y0)
            cur['y1'] = max(cur['y1'], y1)
            cur['text'] += ' ' + text
            cur['last_idx'] = idx
        else:
            if cur:
                spans.append(cur)
            cur = {'key': key, 'x0': x0, 'y0': y0, 'x1': x1, 'y1': y1, 'text': text, 'last_idx': idx}
    if cur:
        spans.append(cur)
    return spans

def _drawing_sig(d):
    """A rounded (position, color) fingerprint for a vector drawing, stable enough to
    match the same shared/decorative drawing (table borders, background fills, box
    outlines) across a blank and solution PDF exported from the same template, even
    with tiny floating-point differences, while still distinguishing genuinely new
    content (answer strokes/arrows/spectra) drawn at a different position or color."""
    r = d['rect']
    color = d.get('color') or d.get('fill')
    color_r = tuple(round(c, 2) for c in color) if color else None
    return (round(r.x0, 1), round(r.y0, 1), round(r.x1, 1), round(r.y1, 1), d.get('type'), color_r)

def diff_drawings(blank_page, sol_page, pad=1.5, neutral_spread=None, cluster=True):
    """Answers are sometimes drawn as vector graphics rather than text (e.g. sketched
    spectra as colored bars, occupied-orbital arrows in a Pauling/orbital diagram) -
    diff_page() above only sees PDF text and misses these entirely. This diffs the
    two pages' vector drawings by a rounded position+color signature (matching shared/
    template drawings present on both pages, however many repeats of each), collects
    whatever's left over as "new" (answer-only) drawings, and clusters them into
    bounding-box spans the same shape as diff_page()'s, so both feed the same cover-
    stroke builder downstream.

    `neutral_spread` and `cluster=False` exist for **grid mode** (`generate_goodnotes.py
    --grid`), a document shape distinct from a typical worksheet: a table/timetable/
    seating-chart whose colored cells sit edge-to-edge across whole rows and whose
    structural header/row-label cells use a neutral mid-grey fill rather than near-
    white. See generate_goodnotes.py's `--grid` help and CLAUDE.md's "Grid mode" for
    the full rationale; both params default to the original worksheet behavior so
    every existing call site is unaffected."""
    blank_sigs = Counter(_drawing_sig(d) for d in blank_page.get_drawings())
    new_rects = []
    for d in sol_page.get_drawings():
        # Near-white fills (page/cell/table background) are common to differ slightly
        # between a blank and solution export of the same template (e.g. a table's
        # background box rendered fractionally differently once a cell has content)
        # without being answer content at all - and being white already, covering one
        # in white would be redundant even if it were real content. Skipping them also
        # avoids one specific failure mode: an unmatched background box can span a
        # huge area and, once merged with genuinely new nearby drawings below, would
        # balloon a small answer cluster into one giant cover over unrelated content.
        fill = d.get('fill')
        if d.get('type') == 'f' and fill and all(c > 0.95 for c in fill):
            continue
        # Grid mode only (neutral_spread is not None): also exclude neutral/grayscale
        # fills (r==g==b within neutral_spread), not just near-white ones - a table's
        # structural header/row-label cells can use a mid-grey fill (e.g. ~0.86,0.86,
        # 0.86) that the near-white-only check above (>0.95) doesn't catch, wrongly
        # flagging them as "new" content to cover. A worksheet's genuine answer colors
        # are not expected to be neutral grays, so this threshold cleanly separates the
        # two without hand-listing specific colors. None (the default) in ordinary
        # diff mode, so no behavior change for existing worksheets.
        if neutral_spread is not None and d.get('type') == 'f' and fill and (max(fill) - min(fill)) < neutral_spread:
            continue
        sig = _drawing_sig(d)
        if blank_sigs[sig] > 0:
            blank_sigs[sig] -= 1
            continue
        new_rects.append(d['rect'])

    if not cluster:
        # Grid mode only: a table's colored cells are already exact, individual
        # rectangles - merging touching/overlapping ones (as below) fuses whole rows of
        # edge-to-edge cells into one oversized bounding box that overshoots into
        # unrelated, uncovered cells sitting between the merged ones. Emit one span per
        # rect directly instead. Confirmed against the Klassenplan 9-1 timetable: with
        # clustering on (even with neutral_spread set), default clustering collapsed
        # 26 individual colored lesson cells into 1 giant bounding box spanning nearly
        # the whole table (connected through the grey label column touching every row);
        # this preserves all 26 as precise, independent spans.
        return [{'key': None, 'x0': r.x0, 'y0': r.y0, 'x1': r.x1, 'y1': r.y1, 'text': ''}
                for r in new_rects]

    # Merge padded-overlapping rects into connected clusters (union-find), so e.g. the
    # several path segments making up one arrow glyph, or one arrow among several in
    # the same table cell, collapse into one cover span instead of dozens of tiny ones.
    n = len(new_rects)
    parent = list(range(n))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    def union(i, j):
        pi, pj = find(i), find(j)
        if pi != pj:
            parent[pi] = pj
    padded = [fitz.Rect(r.x0 - pad, r.y0 - pad, r.x1 + pad, r.y1 + pad) for r in new_rects]
    for i in range(n):
        for j in range(i + 1, n):
            if padded[i].intersects(padded[j]):
                union(i, j)
    clusters = {}
    for i in range(n):
        clusters.setdefault(find(i), []).append(new_rects[i])

    spans = []
    for rects in clusters.values():
        x0 = min(r.x0 for r in rects)
        y0 = min(r.y0 for r in rects)
        x1 = max(r.x1 for r in rects)
        y1 = max(r.y1 for r in rects)
        spans.append({'key': None, 'x0': x0, 'y0': y0, 'x1': x1, 'y1': y1, 'text': ''})
    return spans

if __name__ == '__main__':
    import sys
    blank_path, sol_path = sys.argv[1], sys.argv[2]
    blank = fitz.open(blank_path)
    sol = fitz.open(sol_path)
    for pno in range(sol.page_count):
        bp = blank[pno] if pno < blank.page_count else None
        sp = sol[pno]
        print(f"=== page {pno} ===")
        if bp is None:
            print("  (no corresponding blank page)")
            continue
        spans = diff_page(bp, sp)
        for s in spans:
            print(f"  [{s['x0']:.2f},{s['y0']:.2f} -> {s['x1']:.2f},{s['y1']:.2f}]  {s['text']!r}")
