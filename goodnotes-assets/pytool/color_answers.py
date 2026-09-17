#!/usr/bin/env python3
"""Find answer spans in a single PDF by text color, for worksheets where the
solutions are already baked into one PDF as differently-colored text (e.g.
pink/magenta answer key text), instead of a separate blank-vs-solution pair.
"""

def _color_distance(c1, c2):
    r1, g1, b1 = c1
    r2, g2, b2 = c2
    return ((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2) ** 0.5

def find_colored_spans(page, target_rgb, tolerance=40):
    """target_rgb: (r,g,b) 0-255. Returns spans clustered per PDF text line,
    same shape as diff_pdfs.diff_page()'s output: dicts with x0,y0,x1,y1,text."""
    d = page.get_text("dict")
    spans = []
    for block in d["blocks"]:
        for line in block.get("lines", []):
            line_spans = []
            for span in line["spans"]:
                c = span["color"]
                rgb = ((c >> 16) & 255, (c >> 8) & 255, c & 255)
                if _color_distance(rgb, target_rgb) <= tolerance:
                    line_spans.append(span)
            if not line_spans:
                continue
            x0 = min(s["bbox"][0] for s in line_spans)
            y0 = min(s["bbox"][1] for s in line_spans)
            x1 = max(s["bbox"][2] for s in line_spans)
            y1 = max(s["bbox"][3] for s in line_spans)
            text = ''.join(s["text"] for s in line_spans)
            spans.append({'x0': x0, 'y0': y0, 'x1': x1, 'y1': y1, 'text': text})
    return spans

def detect_dominant_accent_color(page, exclude_near_black=True, exclude_near_white=True):
    """Best-effort auto-detect: the most common non-black/non-white text color,
    useful for a first look at an unfamiliar worksheet's answer-key color."""
    d = page.get_text("dict")
    counts = {}
    for block in d["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                c = span["color"]
                rgb = ((c >> 16) & 255, (c >> 8) & 255, c & 255)
                if exclude_near_black and max(rgb) < 80:
                    continue
                if exclude_near_white and min(rgb) > 200:
                    continue
                counts[rgb] = counts.get(rgb, 0) + len(span["text"])
    if not counts:
        return None
    return max(counts.items(), key=lambda kv: kv[1])[0]

if __name__ == '__main__':
    import sys, fitz
    path = sys.argv[1]
    doc = fitz.open(path)
    for pno in range(doc.page_count):
        page = doc[pno]
        dominant = detect_dominant_accent_color(page)
        print(f"page {pno}: dominant accent color guess = {dominant}")
