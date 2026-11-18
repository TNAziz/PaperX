# Licenses

Read from the installed package metadata on 2026-11-17. Model weights are licensed separately from code. Check them before sharing.

| Component | Version | Code license | Weights / notes | Blocks sharing with students or other labs? |
| --- | --- | --- | --- | --- |
| paperx (this repo) | 0.1.0 | Not yet chosen | | Pick one (MIT or Apache-2.0 fit the dependencies below) |
| pypdfium2 (rendering, text) | 5.15.2 | BSD-3-Clause / Apache-2.0 | PDFium is BSD | No. Chosen over PyMuPDF to avoid AGPL |
| Docling, docling-core, docling-ibm-models, docling-parse | 2.150.1 | MIT | Layout (Heron), TableFormer, CodeFormulaV2 models from `docling-project` on Hugging Face. Check each model card | No, pending model-card check |
| MinerU | 4.2.3 | "MinerU Open Source License": Apache-2.0 plus extra terms | A commercial license is needed above 100M monthly users or US$20M monthly revenue. Anyone offering it as an online service must credit MinerU visibly | No for lab and student use. Attribution applies only if paperx is offered as a hosted service |
| Marker (marker-pdf), surya-ocr, pdftext | 2.2.0 / 0.23.0 / 0.7.1 | Apache-2.0 (code; changed from GPL in earlier versions) | Surya and Marker model weights have historically carried a modified OpenRAIL-M license, free for research and for organizations under US$5M revenue. **Not re-verified for 2.x weights** | Probably not for a university lab; confirm the weights license |
| RapidOCR (via Docling) | 3.10.0 | Apache-2.0 | | No |
| GROBID | not installed | Apache-2.0 | | No |
| anthropic (Python SDK) | 2.9.0 | Apache-2.0 | Claude API use is under Anthropic's commercial terms | No, but each user needs their own API key |
| rapidfuzz, httpx, Pillow | | MIT / BSD / HPND | | No |

The plan listed PyMuPDF as AGPL. paperx does not use it, and neither do the three parser environments as installed. The MinerU terms in the plan ("custom terms") now resolve to Apache-2.0 plus the thresholds above.
