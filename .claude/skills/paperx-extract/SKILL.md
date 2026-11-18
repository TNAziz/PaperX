---
name: paperx-extract
description: Extract the text, tables, equations, references and chart data from a technical paper PDF with paperx, verify them against the page images, and package the numbers as a validation dataset with provenance. Use when Tarek points at a paper (a PDF path, a filename in Research Articles, or a Zotero item) and asks to extract it, pull its data or figures, digitize its plots, or build validation data for a model or simulation.
---

# Extract a paper with paperx

paperx lives in `C:\Users\tnaziz\My Drive\Research Articles\PaperX`. Its environments are in
`C:\Users\tnaziz\.paperx\envs`, and the archive is `C:\Users\tnaziz\paperx-archive`.
Read `PaperX/README.md` if anything below is unclear.

```
PX=/c/Users/tnaziz/.paperx/envs/main/Scripts/paperx.exe
PY=/c/Users/tnaziz/.paperx/envs/main/Scripts/python.exe
export PYTHONIOENCODING=utf-8
```

## 1. Find the PDF

- If Tarek gives a path, use it. If he gives a title, author or year, search
  `C:\Users\tnaziz\My Drive\Research Articles` (and its subfolders) by filename. Confirm the match
  with him if more than one file fits.
- Never modify, move or rename the source PDF. paperx copies it.
- If the paper may be in Zotero but the archive key comes back as `X...`, run `$PX sync-zotero` once,
  then retry.

## 2. Run the pipeline (in the background; 3 to 15 minutes per paper)

```
$PX extract "<pdf>" --parser mineru --crosscheck docling --figure-data
```

The output ends with the archive folder, `C:\Users\tnaziz\paperx-archive\<KEY>`. For a paper already
in the archive, `$PX figdata <KEY>` reads chart data without re-running the rest. `$PX rebuild <KEY>
--figure-data` re-assembles from the saved parser output and reuses saved Claude answers.

Verification runs through the Claude Code CLI under Tarek's Claude Team login; there is no API key.
If it reports the CLI is not logged in, ask him to run `claude auth login` in a terminal. Usage counts
against his plan. One paper uses up to 500k tokens (`PAPERX_TOKEN_CAP`). Each chart uses about
20 to 40k tokens.

## 3. Review before reporting

```
$PY -m paperx.report --keys <KEY>
```

Then, in `<KEY>/verify_report.json`, look at every flag with severity `error` or `warn`. For the
figures Tarek cares about, open `figures/Fn.replot.png` (original on the left, re-plot of the
extracted data on the right). Check by eye that the series line up before you say the data is good.
`figures/Fn.data.json` has the axes, units, scale and reading precision.

Status meanings:
- `pass`: verified as extracted.
- `pass_after_correction`: Claude re-read the item from the image and a fresh check passed it. The
  parser's original is kept (`Tn.extracted.csv`, or `latex_extracted`).
- `fail` or `uncertain`: not trustworthy. Say so plainly, show which item it is, and offer to look at it.
- `not_a_chart`: photos, diagrams and maps have no data to extract.

## 4. Package the numbers for validation work

```
$PX dataset <KEY> [<KEY> ...] -o "<folder Tarek names, or PaperX/datasets/<short-name>>"
```

This writes `figure_data.csv` (chart values with citation, DOI, figure, panel, axis units and scale,
error-bar ends, reading precision and verification status), `tables/`, `provenance.json` and a
`README.md`. Only verified items are included unless `--include-unverified` is given.

## 5. Report to Tarek

In plain language, say:
- **Results:** what was extracted (counts of tables, equations, figures and chart series) and where it is.
- **Not verified:** which items could not be verified, and why.
- **Trust:** chart values are read from images and are approximate. Give the reading precision for the
  series he asked about, and point him to the re-plot images.

Never present a value as exact if it came from a chart. Never fill gaps with values from memory or
from other papers: report what the figure shows, and say what it doesn't show.

## Data handling

Paper content goes only to Claude, for verification. Reference strings go to Crossref. Do not enable
MinerU's remote parsing or image analysis, or any hosted parser, without Tarek's OK.
