"""Run Docling on one PDF and write paperx's common items.json.

Usage (inside the docling env):  python run.py <pdf> <outdir> [--device cuda|cpu]

Writes to <outdir>:
  native/doc.json, native/doc.md   untouched Docling output
  items.json                       common schema read by paperx (see src/paperx/schema.py)
  img/                             figure and table crops
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from importlib.metadata import version
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("outdir")
    ap.add_argument("--device", default="cuda")
    a = ap.parse_args()

    from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling_core.types.doc import (
        DocItemLabel,
        ImageRefMode,
        PictureItem,
        SectionHeaderItem,
        TableItem,
        TextItem,
        TitleItem,
    )

    out = Path(a.outdir).resolve()
    (out / "native").mkdir(parents=True, exist_ok=True)
    (out / "img").mkdir(exist_ok=True)

    opts = PdfPipelineOptions()
    opts.do_ocr = True
    opts.do_table_structure = True
    opts.table_structure_options.mode = TableFormerMode.ACCURATE
    opts.do_formula_enrichment = True
    opts.generate_picture_images = True
    opts.generate_table_images = True
    opts.images_scale = 2.0
    opts.accelerator_options = AcceleratorOptions(
        device=AcceleratorDevice.CUDA if a.device == "cuda" else AcceleratorDevice.CPU
    )
    conv = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})

    t0 = time.time()
    doc = conv.convert(a.pdf).document
    elapsed = time.time() - t0

    doc.save_as_json(out / "native" / "doc.json", image_mode=ImageRefMode.REFERENCED)
    doc.save_as_markdown(out / "native" / "doc.md", image_mode=ImageRefMode.PLACEHOLDER)

    pages = {}
    for no, p in doc.pages.items():
        pages[no] = {"page": no, "width": p.size.width, "height": p.size.height}

    def box(item):
        if not item.prov:
            return None, None
        pr = item.prov[0]
        h = pages[pr.page_no]["height"]
        b = pr.bbox.to_top_left_origin(page_height=h)
        return pr.page_no, [round(b.l, 1), round(b.t, 1), round(b.r, 1), round(b.b, 1)]

    kind_map = {
        DocItemLabel.TITLE: "heading",
        DocItemLabel.SECTION_HEADER: "heading",
        DocItemLabel.TEXT: "text",
        DocItemLabel.PARAGRAPH: "text",
        DocItemLabel.LIST_ITEM: "list",
        DocItemLabel.CAPTION: "caption",
        DocItemLabel.FOOTNOTE: "footnote",
        DocItemLabel.PAGE_HEADER: "header",
        DocItemLabel.PAGE_FOOTER: "footer",
        DocItemLabel.FORMULA: "equation",
        DocItemLabel.REFERENCE: "reference",
        DocItemLabel.CODE: "text",
    }

    items = []
    ntab = nfig = 0
    for item, level in doc.iterate_items(with_groups=False, included_content_layers=None):
        page, bbox = box(item)
        rec = {"page": page, "bbox": bbox}
        if isinstance(item, TableItem):
            ntab += 1
            try:
                df = item.export_to_dataframe(doc=doc)
                rows = [list(map(str, df.columns))] + [[str(c) for c in r] for r in df.values.tolist()]
            except Exception as e:  # keep going, but say so
                rows, rec["error"] = [], f"table export failed: {e}"
            img = item.get_image(doc)
            if img is not None:
                p = f"img/table_{ntab}.png"
                img.save(out / p)
                rec["image"] = p
            rec.update(kind="table", rows=rows, html=item.export_to_html(doc=doc),
                       caption=item.caption_text(doc))
        elif isinstance(item, PictureItem):
            nfig += 1
            img = item.get_image(doc)
            if img is not None:
                p = f"img/figure_{nfig}.png"
                img.save(out / p)
                rec["image"] = p
            rec.update(kind="figure", caption=item.caption_text(doc))
        elif isinstance(item, (TitleItem, SectionHeaderItem)):
            rec.update(kind="heading", text=item.text, level=getattr(item, "level", 1) + (0 if isinstance(item, TitleItem) else 1))
        elif isinstance(item, TextItem):
            kind = kind_map.get(item.label, "text")
            rec.update(kind=kind, text=item.text)
            if kind == "equation":
                rec["latex"] = item.text
                rec["display"] = True
        else:
            continue
        items.append(rec)

    result = {
        "tool": "docling",
        "tool_version": version("docling"),
        "versions": {k: version(k) for k in ("docling", "docling-core", "docling-ibm-models", "torch")},
        "settings": {"table_mode": "accurate", "formula_enrichment": True, "device": a.device, "images_scale": 2.0},
        "seconds": round(elapsed, 2),
        "pages": list(pages.values()),
        "items": items,
    }
    (out / "items.json").write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"docling: {len(items)} items, {ntab} tables, {nfig} figures, {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
