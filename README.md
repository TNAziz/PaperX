# PaperX

PaperX turns technical-paper PDFs into a verified, searchable archive. It extracts body text, tables, equations, references and chart data. It checks every table, equation and chart against the page image with Claude, corrects failures automatically, and flags anything it cannot verify. It never passes an error silently. Chart data can be packaged as cited validation datasets for model and simulation studies.

> **Status: research prototype.** Developed and tested on Windows 11 with an NVIDIA GPU (RTX 3080 Ti, 12 GB), on about 25 environmental-engineering papers. It has not yet been scored against hand-corrected ground truth. Treat its output as a strong first draft whose weak spots are flagged.

## What it does

| Component | Output | How it is checked |
| --- | --- | --- |
| Body text | `paper.md` with headings and page markers; tables, figures and equations as placeholders (`[[T1]]`, `[[F2]]`, `[[EQ3]]`) | Running headers removed; full-text search index |
| Tables | `T1.csv` with caption, page and bounding box | Claude compares the 200-dpi page crop with the CSV. Failures are re-extracted from the image and must pass a fresh check. Garbled-glyph detection; cross-check against a second parser |
| Equations | LaTeX with equation numbers | Compiled with `pdflatex`, plus the same visual check and correction loop |
| Figures | `F1.png` with caption, number and panel count | Every figure number cited in the text must be found. Multi-panel figures are merged, and garbled captions are re-read from the page |
| Chart data (optional) | `F1.data.csv`: every series, with axes, units, log or inverted scales, and error bars | The data are re-plotted with matplotlib, and a fresh Claude call compares the re-plot with the original side by side |
| References | `references.bib` | Each entry matched to a DOI through Crossref; unmatched entries are flagged |

Every paper gets one folder, named by its Zotero item key when the PDF is in your Zotero library (matched by file hash, read-only). Each folder holds a `verify_report.json` listing every check that ran and every flag raised, with page locations.

## Accuracy so far

**Chart data, on charts drawn from known data** (`bench/figdata_bench.py`). Every point was found on every chart.

| Chart | Median error | Largest error |
| --- | --- | --- |
| Model curve with observed points | 0.1% | 1.0% |
| 25-point scatter | 0.0% | 0.2% |
| Grouped bars with error bars | 0.0% | 0.2% |
| Log-scale decay | 0.09% | 0.38% |
| Two-panel figure | 0.0% | 0.4% |
| Three overlapping curves, no markers | 0.24% | 1.5% |

Errors are percentages of the axis range (on log axes, of the decades shown).

**On real papers** (journal articles, a supplementary-information file, two scanned documents and a textbook chapter):
- **Tables and equations:** 157 of 168 verified across a random 14-paper batch (40 of them after auto-correction), and 68 of 68 in three contact-tank papers.
- **Charts:** 26 of 27 verified across the pilot and three contact-tank papers. These include twin-y-axis bioreactor plots, a vertical lake profile with three x axes and inverted depth, and residence-time curves with six overlapping series. The one failure, a scanned plot with no tick marks, was flagged.

The verification step caught real errors that would otherwise have gone in silently. Examples:
- "399 ± 540" read as the single number "3996540"
- "+" signs encoded as "þ"
- lost decimal points in chemical-formula subscripts (N.4 read as N4)
- stray absolute-value bars added around equations

## Requirements

- Python 3.11 or later, and [uv](https://docs.astral.sh/uv/)
- An NVIDIA GPU is strongly recommended. The parsers run on CPU but much more slowly.
- For verification, one of:
  - [Claude Code](https://claude.com/claude-code) installed and logged in (`claude auth login`); checks count against your Claude plan's usage
  - an Anthropic API key
- Optional: a LaTeX distribution (`pdflatex`) for the equation compile check; Zotero for item-key mapping

Parsers used: [MinerU](https://github.com/opendatalab/MinerU) as the primary layout parser, [Docling](https://github.com/docling-project/docling) as a cross-check, and [Marker](https://github.com/datalab-to/marker) as an option. Each runs in its own environment, so their dependencies never conflict.

## Install

Keep the environments and the archive outside any cloud-synced folder (Google Drive, OneDrive, Dropbox). Sync clients lock files while uploading.

```bash
git clone https://github.com/TNAziz/PaperX.git
cd PaperX
export UV_LINK_MODE=copy
UV_PROJECT_ENVIRONMENT=~/.paperx/envs/main uv sync --python 3.12
for t in mineru docling marker; do
  (cd tools/$t && UV_PROJECT_ENVIRONMENT=~/.paperx/envs/$t uv sync --python 3.12)
done
```

On Windows, the CLI is `~/.paperx/envs/main/Scripts/paperx.exe`; on Linux and macOS, `~/.paperx/envs/main/bin/paperx`. Models download on first use (several GB). Each parser environment pulls CUDA 12.6 builds of PyTorch; edit `tools/*/pyproject.toml` for another CUDA version or for CPU.

## Use

```bash
paperx sync-zotero                                  # optional: map PDFs to Zotero item keys
paperx extract paper.pdf --figure-data              # full pipeline, including chart data
paperx extract *.pdf --no-claude                    # no verification; everything flagged unverified
paperx search "residence time distribution"         # full-text search of the archive
paperx figdata KEY --figures F5 F7                  # chart data for a paper already in the archive
paperx dataset KEY1 KEY2 -o datasets/my-validation  # package verified data with provenance
paperx rebuild KEY                                  # re-assemble from saved parser output (no re-parse)
python -m paperx.report                             # results table for the whole archive
```

`extract` skips a paper when its file hash, parser and tool versions are unchanged (`--force` to re-run), and `--reuse-raw` resumes an interrupted run. Claude's answers are cached by image and prompt, so a rebuild only pays for items that changed.

### Validation datasets

`paperx dataset` writes:
- **`figure_data.csv`:** every verified chart value, with citation, DOI, figure and panel, page, axis labels, units, scale and direction, error-bar ends, the model's reading precision, and verification status.
- **`tables/`:** the verified tables.
- **`replots/`:** each original chart beside its re-plot, for checking by eye.
- **`provenance.json`:** source hashes, tool versions, and per-panel notes such as overlapping curves or detection-limit markers.

Chart values are approximate. Check the re-plots before relying on a series, and cite the original source of any data a paper re-plots from another study.

### Claude Code skill

`.claude/skills/paperx-extract/SKILL.md` teaches Claude Code the whole workflow: find the PDF, run the pipeline, review flags and re-plots, and package the dataset. In a Claude Code session opened on this folder you can then say "extract the data from <paper>". The paths in the skill point to the author's machine; edit them for yours.

## Configuration (environment variables)

| Variable | Default | Meaning |
| --- | --- | --- |
| `PAPERX_HOME` | `~/.paperx` | Environments, caches, Zotero map |
| `PAPERX_ARCHIVE` | `paperx-archive` beside the Zotero data folder | Archive root |
| `PAPERX_ZOTERO_DIR` | `~/Zotero` | Zotero data directory (read-only) |
| `PAPERX_VERIFIER` | `cli` | `cli` (Claude Code login) or `api` (`ANTHROPIC_API_KEY`) |
| `PAPERX_CLAUDE_MODEL` | `claude-opus-5-5` | Model used for verification |
| `PAPERX_TOKEN_CAP` | `500000` | Claude tokens per paper; items beyond the cap are flagged unverified |
| `PAPERX_AUTOCORRECT` | `1` | Re-extract failed items from the image, then recheck |
| `PAPERX_CORRECT_ROUNDS` | `2` | Correction rounds per item |
| `PAPERX_CLAUDE_CACHE` | `1` | Reuse stored answers for identical requests |

## Data handling

- **What leaves the machine:** paper content goes only to Claude, as cropped images of tables, equations, captions and charts. Reference strings go to Crossref, with a generic User-Agent and no contact details.
- **MinerU:** runs fully locally, with telemetry disabled, no remote parsing, and its optional image analysis turned off.
- **Zotero:** read through a temporary copy of `zotero.sqlite`.
- **Source PDFs:** copied into the archive and never modified.

## Limitations

- Tuned on environmental-engineering papers (ACS, Elsevier, RSC, Springer, MDPI, ASCE, arXiv). Other publishers' layouts may need further caption rules.
- Chart reading struggles with axes that have no tick labels, very dense scatter, and 3-D or contour plots. These are flagged, not guessed.
- The same model family writes corrections and checks them. A fresh call reduces correlated errors but does not remove them, so spot-check corrected items.
- GROBID and a fair Marker comparison both need Docker, which was not available during development.

## Repository layout

```
src/paperx/      pipeline: parsers.py, reconcile.py, verify.py, figdata.py, refs.py, dataset.py, index.py, zotero.py, cli.py
tools/<parser>/  isolated environment definitions for MinerU, Docling and Marker
bench/           chart-data accuracy benchmark (synthetic charts with known data)
tests/           unit tests (no network): python -m pytest -q
PLAN_REVIEW.md   design review and results log from development
ENV.md           development machine survey and Windows-specific notes
LICENSES.md      third-party licenses and model-weight terms
```

## License

PaperX's own code is released under the [MIT License](LICENSE). Third-party components keep their own licenses; see [LICENSES.md](LICENSES.md). In particular, MinerU's license adds usage thresholds to Apache-2.0, and Marker's model weights have separate terms.
