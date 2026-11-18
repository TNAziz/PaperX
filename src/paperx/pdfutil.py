"""PDF helpers built on pypdfium2 (Apache-2.0/BSD). Never writes to the source PDF."""
from __future__ import annotations

import hashlib
import re
from functools import lru_cache
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Pdf:
    """Read-only view of a PDF: page sizes, page text, and region rendering."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.doc = pdfium.PdfDocument(str(self.path))
        self.n = len(self.doc)
        self._pages: dict[int, Image.Image] = {}

    def size(self, page: int) -> tuple[float, float]:
        """(width, height) in points for 1-based page."""
        return self.doc[page - 1].get_size()

    def text(self, page: int) -> str:
        return self.doc[page - 1].get_textpage().get_text_range()

    def render_page(self, page: int, dpi: int = 200) -> Image.Image:
        key = (page, dpi)
        if key not in self._pages:
            self._pages[key] = self.doc[page - 1].render(scale=dpi / 72).to_pil().convert("RGB")
        return self._pages[key]

    def render_region(self, page: int, bbox: list[float], dpi: int = 200, pad: float = 4) -> Image.Image:
        """Crop a region given in points, top-left origin."""
        img = self.render_page(page, dpi)
        s = dpi / 72
        x0, y0, x1, y1 = bbox
        box = (max(0, (x0 - pad) * s), max(0, (y0 - pad) * s), min(img.width, (x1 + pad) * s), min(img.height, (y1 + pad) * s))
        return img.crop(tuple(int(v) for v in box))

    def has_text_layer(self, pages: int = 3) -> bool:
        k = min(self.n, pages)
        return sum(len(self.text(i + 1).strip()) for i in range(k)) / max(k, 1) > 200

    def close(self):
        self._pages.clear()
        self.doc.close()


DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>,;]+)", re.I)


def find_doi(text: str) -> str | None:
    m = DOI_RE.search(text)
    if not m:
        return None
    return m.group(1).rstrip(".)]}")
