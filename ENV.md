# Environment survey (Phase 0)

Surveyed 2026-11-17 on the machine Claude Code runs on.

| Item | Value |
| --- | --- |
| OS | Windows 11 Education 10.0.26200 |
| CPU | Intel Core i7-11700K, 8 cores / 16 threads |
| RAM | 31.9 GB |
| GPU | NVIDIA GeForce RTX 3080 Ti, 12 GB VRAM, driver 560.94 (CUDA 12.6 runtime via PyTorch wheels; no system CUDA toolkit needed) |
| Python | System 3.13.0; paperx environments use uv-managed CPython 3.12.13 |
| uv | 0.11.15 |
| Disk | C: 1.9 TB, 1.2 TB free |
| Zotero data directory | `C:\Users\tnaziz\Zotero` (zotero.sqlite present; 2,604 PDF attachments, mostly in `storage/`) |
| LaTeX | MiKTeX 25.12 (pdflatex), used for the equation compile check |
| Java / Docker | **Not installed.** GROBID needs one of them (see below) |
| Tesseract | Not installed (not needed: all three parsers ship their own OCR) |
| Claude access | Claude Code CLI 2.1.310 at `~\.local\bin\claude`, logged in with a Claude Team account (log in with `claude auth login`). No `ANTHROPIC_API_KEY`; paperx's verification uses the CLI |

Network reachability (HTTP status, time):

| Endpoint | Result |
| --- | --- |
| PyPI | 200, 1.1 s |
| Hugging Face | 200, 0.2 s |
| Crossref API | 200, 2.4 s (rate-limits bursts: use sequential requests) |
| OpenAlex API | 200, 0.5 s |
| PyTorch wheel index | 200, 0.3 s |

## Mode decision per tool

| Tool | Mode | Notes |
| --- | --- | --- |
| MinerU 4.2.3 | GPU | Local `mineru-kit parse` (hybrid layout + local VLM via llama.cpp). Telemetry disabled with `MINERU_TELEMETRY_DISABLED=1`; `--remote` never used; image analysis disabled. |
| Docling 2.150.1 | GPU | TableFormer accurate mode, CodeFormula enrichment for LaTeX |
| Marker 2.2.0 | GPU | Needs `PYTHONUTF8=1` on Windows and a short input path (crashes on paths over 260 characters) |
| GROBID | Blocked | Needs Java 21 or Docker. Neither is installed. Phase 2 reference scoring uses the layout parser's reference list plus Crossref until this is resolved |
| Claude verification | Claude Code CLI | `claude -p` per table or equation; about 7 s and 6k tokens per check |

## Where things live

| Path | What | Synced to Google Drive? |
| --- | --- | --- |
| `My Drive\Research Articles\PaperX\` | Code only | Yes (small) |
| `C:\Users\tnaziz\.paperx\envs\{main,docling,marker,mineru}` | One uv environment per tool, about 4 to 6 GB each | No |
| `C:\Users\tnaziz\.paperx\cache`, `zotero_map.json` | Crossref cache, Zotero hash map | No |
| `C:\Users\tnaziz\.cache\huggingface` | Model weights | No |
| `C:\Users\tnaziz\paperx-archive\` | Default archive (beside the Zotero data directory) | No |

Two Windows-specific findings that shaped this layout:

1. **Do not put environments or the archive in Google Drive.** Drive holds file handles while it syncs. A re-run failed with `Access is denied` when it tried to replace an archive folder that Drive was still uploading.
2. **The Claude desktop app virtualizes `%LOCALAPPDATA%`.** Files written there by a process launched from the app land in `AppData\Local\Packages\Claude_...\LocalCache\` and are invisible to other programs. Hence `~\.paperx` instead of `%LOCALAPPDATA%\paperx`. A first copy of the environments was created under the virtualized path before this was found. It is unused and can be deleted (`AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Local\paperx`, 5.3 GB).
