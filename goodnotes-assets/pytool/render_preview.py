#!/usr/bin/env python3
"""Render a visual preview of where the generated blue cover-strokes would land,
by drawing rectangles on the solution PDF page (in PDF space) and rasterizing.
This is NOT how GoodNotes renders it exactly, but validates position/size sanity."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fitz
import strokes as S

SCALE = 11/6

def preview(goodnotes_extract_dir, note_file_name, pdf_path, out_png):
    doc = fitz.open(pdf_path)
    page = doc[0]
    tpls = S.extract_templates(f"{goodnotes_extract_dir}/notes/{note_file_name}")
    for t in tpls:
        p1x, p1y = t.p1[0]/SCALE, t.p1[1]/SCALE
        p2x, p2y = t.p2[0]/SCALE, t.p2[1]/SCALE
        half_h = (t.width/SCALE)/2
        x0, x1 = min(p1x,p2x), max(p1x,p2x)
        y0, y1 = min(p1y,p2y)-half_h, max(p1y,p2y)+half_h
        rect = fitz.Rect(x0,y0,x1,y1)
        page.draw_rect(rect, color=(0,0,1), fill=(0.2,0.5,1), fill_opacity=0.5, width=0)
    pix = page.get_pixmap(matrix=fitz.Matrix(2,2))
    pix.save(out_png)
    print(f"wrote {out_png}, {len(tpls)} strokes drawn")

if __name__ == '__main__':
    import sys
    preview(*sys.argv[1:5])
