# Review of "Paper Extraction Pipeline (paperx): Build and Test Plan"

Reviewed 2026-11-17 against the plan in `Downloads/paperx-build-plan.md`, and checked against what actually happened when parts of it were built on this machine (see "Exploration results" below).

## Summary

The plan is sound. Its central rule is right: an error is acceptable if flagged, never if silent. So are the two-tool architecture, the per-paper archive keyed to Zotero, and the held-out split. Most of what follows tightens definitions so that a Phase 2 or Phase 4 exit can be judged without argument, plus five issues that block or change the build.

## Blocking or design-changing issues

1. **GROBID cannot run here as specified.** No Java and no Docker on this machine, and GROBID does not run natively on Windows. Options: install Docker Desktop (needs WSL2, an admin step), run GROBID on a lab Linux box, or score references from the layout parser plus Crossref. The plan should name the fallback. Note: MinerU already labels reference entries (`ref_text`), so the parser-plus-Crossref path gives GROBID a real competitor in the bake-off.
2. **Claude verification: resolved by using the Claude Code CLI.** No API key is needed. paperx runs `claude -p` under your existing Claude Team login, with read access limited to the one crop image. An API-key path remains as an option (`PAPERX_VERIFIER=api`) for machines without Claude Code. Usage counts against the Claude Team plan's limits; nothing is billed separately. (The CLI also reports a `total_cost_usd`, which is only an estimate of what the same tokens would cost on the API.) Measured: about 6k tokens per check.
3. **Crossref lookup conflicts with the data-handling rule.** "Paper content goes to no third-party service except Claude", but the architecture sends every reference string to Crossref or OpenAlex. That is public bibliographic text, so it is probably fine, but the rule should say so explicitly. The implementation sends a generic User-Agent and no email address.
4. **MinerU has changed shape since the plan was written.** Version 4.x is now a "document library" with a server, a `--remote` cloud parse option, telemetry, and an optional hosted-LLM image-analysis setting (`dashscope.aliyuncs.com` appears in its config). paperx calls the local `mineru-kit parse` with telemetry off, `--remote` off and image analysis off, but the plan's hosted-service rule should name these switches. A version bump could change a default.
5. **Verifier independence.** If Claude wins the Phase 2 bake-off as an extractor (the plan includes it as a baseline), Claude would then verify Claude's own output, and their errors would be correlated. The plan should say that verification uses a different model or a different input (for example, verify against the rendered LaTeX image, not the source) whenever Claude is the extractor. The exploration found the same problem between parsers: MinerU and Docling both turned the check marks in an ES&T table into the same junk glyph, so the cross-parser check reported 100% agreement on a wrong table. Agreement is not verification.

## Definitions to tighten

- **Equations bar ("render to match the page")** has no metric. Suggest: render the extracted LaTeX and compare it with the crop using a character-level measure such as CDM (character detection matching, from the formula-benchmark literature), plus human review of disagreements. Also say whether `\tag{}` equation numbers count, and whether chemical reaction schemes typeset as equations count. ES&T and photochemistry papers have many.
- **Figures bar ("100% of numbered figures")** should define multi-panel figures (one figure, not ten panels; MinerU splits them), schemes, plates, and supplementary figures. paperx counts a figure as one numbered caption and checks the count against every "Figure N" and "Scheme N" cited in the text.
- **Tables bar:** say how spanning header cells are scored (repeated in each column, or once), and whether footnote markers (a, b, *) belong to the cell. Both choices change the exact-cell score by several points.
- **Body-text bar, measured on 2 sampled pages:** the parsers must output text per page for this to work. paperx writes `<!-- page N -->` markers into `paper.md` for this, and for search. The plan should require page anchors in `paper.md`; Phase 5's "returns the right page" needs them too.
- **References bar:** "correct venue" needs a rule for abbreviations (Environ. Sci. Technol. vs. Environmental Science & Technology). Suggest: compare against Crossref's container-title and its ISO abbreviation.
- **Re-run skip rule:** the cache key should include the paperx version, the parser settings, and the verification prompt and model, not just the tool versions. Otherwise a prompt change will not trigger re-verification.

## Smaller points

- **Zotero keys.** A PDF is an attachment item with its own key; the plan means the parent item key. One parent can have several PDFs (paper plus supplementary information). 667 of 2,604 PDF attachments here are not mappable (352 files missing, the rest linked or not readable), and much of `Research Articles` is outside Zotero. paperx keys by parent item when the hash matches, else `X` + hash prefix, and flags it.
- **Held-out set of 3** gives very noisy estimates, and with one paper per slot for scanned, arXiv and long documents, one of those slots will have no development example. Stratify, or hold out a fourth paper.
- **"Spending more than a day on a phase"** works as a stop rule. Add a token or dollar ceiling for Phase 2, which runs four extractors, one of them Claude on every page.
- **Phase numbering.** The list items are numbered 1 to 7 but called Phase 0 to 6. Fine, but "Phases 2 and 6 end with a review" is easy to misread.
- **Licenses.** Marker's code is now Apache-2.0 (earlier GPL). Its weights terms need re-checking. MinerU's "custom terms" are Apache-2.0 plus revenue/user thresholds that do not touch a university lab. See `LICENSES.md`.
- **Windows specifics** worth adding to the engineering rules: keep environments and the archive out of Google Drive, stage PDFs under short paths, and set `PYTHONUTF8=1`. Details in `ENV.md`.

## Open questions, answered from this machine

| Question | Default in plan | What the survey found |
| --- | --- | --- |
| Machine and GPU | the Claude Code machine; CPU if no GPU | RTX 3080 Ti, 12 GB: all three parsers run in GPU mode |
| Where `archive/` lives | beside the Zotero data directory | `C:\Users\tnaziz\paperx-archive` (outside Drive, which matters, see ENV.md) |
| Who corrects ground truth | graduate student + spot check | still open |
| Accuracy bars right? | as written | still open; see "Definitions to tighten" |
| Hosted parser for benchmark only? | no | still open |

## Exploration results

On 2026-11-17, a working prototype (`paperx extract | rebuild | search | sync-zotero`) was built and run on 7 papers from `Research Articles`. They were chosen to cover the plan's slots: ACS two-column, an equation-light CFD paper, a table-heavy RSC review, a scanned 1994 conference paper, an ASCE equation-heavy paper, a 35-page arXiv preprint, and a 53-page WER literature review. This is **not** the Phase 1 test set: Tarek has not picked papers, and there is no hand-corrected ground truth. So the numbers below are counts and checks against what each PDF says about itself, not accuracy scores.

Configuration: MinerU 4.2.3 as the primary parser, Docling 2.150.1 as the cross-check, Crossref for references, and Claude visual verification through the Claude Code CLI (model `claude-opus-5-5`).

| Paper (archive key) | Pages | Figures found / cited | Tables | Display eqs (compile) | Refs DOI-verified | Parse time, MinerU / Docling |
| --- | --- | --- | --- | --- | --- | --- |
| Page et al. 2011, ES&T (SKUTQ4W9) | 8 | 3/3 figures; Scheme 1 missing (flagged) | 1 | 6 (6/6) | 39/41 | 26 s / 29 s |
| Ta & Hague 2004, Ozone Sci. Eng. (LNDE4TEI) | 10 | 12/12 | 0 | 0 | 5/12 (conference papers; correctly rejected) | 20 s / 24 s |
| Bond et al. 2012, codigestion review (VJTQ2WE6) | 7 | 1/1 | 3/3 | 1 (1/1) | 14/22 | 26 s / 29 s |
| Reichert 1994, Aquasim, **scanned** (L49T4ZI5) | 10 | 23/23 | 1 | 3 (3/3) | 8/14 | 46 s / 39 s |
| Li et al. 2024, ASCE (X662D1ED, not in Zotero) | 17 | 9/9 | 1/1 | 10 (10/10) | 68/85 | 69 s / 44 s |
| Shatarah 2025, arXiv (8FWL9E67) | 35 | 9/9 | 2 | 8 (8/8) | 45/62 | 47 s / 37 s |
| Evans et al. 2009, WER review (VVESGA5J) | 53 | none | 0 | 0 | 241/258 | 57 s / 28 s |

What this shows:

- **Parser choice.** MinerU beat Docling on every component we can check without ground truth. Its equation LaTeX was correct and numbered (Docling dropped letters, e.g. `quenh` for `quench`, and lost equation numbers). It labeled reference entries (Docling tagged them as generic list items) and separated running headers and page numbers (Docling drops them silently). On the codigestion review it read years that Docling turned into private-use junk characters. Docling was faster on long documents. **Marker has not had a fair trial.** Version 2.x expects its Surya model server in Docker, and without Docker it falls back to full-page OCR with no figure detection (0 figures found on every paper). Docker would unblock both Marker and GROBID.
- **Silent errors the checks caught.**
  - Both parsers turned "+" into "þ" in the ES&T table, and the cross-parser check agreed 100% on that wrong table. Only the glyph check caught it.
  - A missed Scheme 1 was caught by checking scheme numbers cited in the text against those extracted.
  - On the scanned paper, captions came out as plain text and figures as loose pieces. This was found by checking the OCR text, and fixed by caption-anchored grouping.
  - Multi-panel figures split into sub-panels ("(a)", "(b)" ... "(d) Fig. 3.") were found and fixed.
  - The table cross-check initially reported false disagreements because spanning cells repeated across columns. This is the scoring question raised above.
- **Claude visual verification (36 tables and display equations): 27 pass, 9 fail, 0 uncertain.** I checked two of the failures against the page images myself, and both were real. Each failure names the cell or term, the extracted value and the correct value. The failures:
  - **ES&T Table 1:** "+" extracted as "þ", a split header, and lost subscripts.
  - **Codigestion Table 2:** the OFMSW formula lost its decimal points (N.4 S.3 Na.2 became N₄ S₃ Na₂, ten times too large).
  - **Codigestion Table 3:** a lost footnote marker.
  - **arXiv Table 2:** blackboard-bold and calligraphic symbols lost.
  - **arXiv and ASCE equations, five in all:** MinerU wrapped the equation in a spurious `\left| … \right.`, or set NN in roman instead of bold.
  
  None of the equation failures was caught by the LaTeX compile check, because the wrong LaTeX is still valid. The decimal-point error was caught only as a vague cross-parser disagreement. The visual check is the only one of the four checks that found these errors precisely.
- **Auto-correct and recheck: all 9 failures fixed, each in one round.** For a failed item, Claude writes a corrected CSV or LaTeX from the image. A second, fresh Claude call then compares that version with the image, without seeing the earlier error list. The correction replaces the parser output only if it passes that recheck, and if it is valid (it parses as CSV, or the LaTeX compiles). Otherwise the original stays, flagged, with the attempt saved beside it (up to 2 rounds). Corrected items keep the parser's original (`Tn.extracted.csv`, or `latex_extracted` in `equations.json`). They are marked `pass_after_correction`, and carry an info flag listing what was fixed.
  - **Final state:** 36 of 36 items verified (27 pass, 9 pass after correction). The only open errors across the 7 papers are the missing Scheme 1, which correction cannot fix, because it is a missing figure, not a wrong value.
  - **Spot-checks against the page images:** the corrected arXiv symbol table and ASCE equation 4 were right. In equation 4 the stray outer bars were removed and the real |**f**[…]|² bars kept. The edits were confined to the cells that were wrong.
  - **Caveat:** the same model writes and checks each correction. The fresh-call design reduces correlated errors but does not remove them. Phase 6 should include a person reviewing a sample of the corrected items specifically.
  - **Usage:** 358k tokens of Claude plan usage for the whole set (36 checks, 9 corrections, 9 rechecks), about 7 seconds per call.
- **Throughput.** Parsing takes 1 to 7 seconds per page on the RTX 3080 Ti. Crossref, not parsing, is the bottleneck: about 1.5 seconds per reference without a contact email, so the 258-reference review took 9 minutes. Options: OpenAlex (faster, no key), or Crossref's "polite pool" (needs a contact email, which needs your OK).
- **Zotero.** 6 of 7 papers mapped to their Zotero parent item by file hash. The ASCE paper is not in Zotero and was keyed `X662D1ED`.
- **Search.** Phrase searches returned the right paper, page and passage (Phase 5 exit criterion met on this set).

## Second batch: 14 more papers (2026-11-17)

Fourteen papers were drawn at random from 13 subfolders of `Research Articles`: 226 pages in all, 2 of them scanned (Cooper et al. 1989; a Chapra textbook chapter). They include a supplementary-information file, your own grease-abatement paper, a 29-page PFAS terminology review, and a survey-instrument education paper. Configuration was the same full pipeline. The run took 63 minutes and used 1.29 million tokens of Claude plan usage.

Results:

| | First run (200k cap) | After re-verifying at 500k cap |
| --- | --- | --- |
| Tables and display equations | 168 | 168 |
| Verified as extracted | 68 | 117 |
| Verified after auto-correction | 30 | 40 |
| Still failing after 2 correction rounds | 2 | 3 |
| Uncertain (image unclear or cropped) | 5 | 8 |
| Not checked: token cap reached | 63, in 5 papers | 0 |
| References DOI-verified | 847 of 1,058 | 847 of 1,058 |

Re-verifying the five capped papers used 1.49 million tokens of plan usage. All their items were checked again under the updated verifier wording. The largest single paper was the Chapra chapter: 459k tokens for 66 items, close to the new 500k cap.

Notable catches, all corrected and confirmed by a fresh check:
- **Your grease-abatement paper:** a table average "399 ± 540" was extracted as the single number "3996540". The same table lost a "<" in "<5.1", and "°C" became "6C".
- **Stormwater review:** text from the rest of the row was merged into a median-concentration cell, replacing "<RL".
- **Fungal bioreactor paper:** a merged table header put columns in the wrong place.

**The token cap is now the main limit.** It was reached on the PFAS review (5 large tables), the survey paper (questionnaire tables full of checkboxes), the Cooper scan (29 equations), the Chapra chapter (63 equations) and the pesticide reactor paper (20 items). Each check uses about 6k tokens, and a correction round about 2 to 3 times that, so 200k covers roughly 25 to 30 items. The pipeline stopped and flagged as specified, so nothing went unflagged. **Decision (Tarek, 2026-11-17): the default cap is raised to 500k tokens per paper.** It is still configurable with `PAPERX_TOKEN_CAP`. The five capped papers were re-verified under the new cap; results are below.

Layouts that broke figure and caption matching, and what was fixed. Each fix has a unit test; there are now 20 tests.
1. **Landscape table printed sideways** on a portrait page, with a garbled caption. New **caption repair**: a caption that is garbled is re-read by Claude from the page image, and so is an unnumbered caption when the paper is missing a numbered item. Completeness is then recomputed.
2. **Supplementary files** number figures S1, S2…, and MinerU wrapped captions in Markdown bold (`**Figure S2:**`). The completeness check now uses the document's own numbering series, so an SI file is not charged with the main paper's Figure 2.
3. **Two captions merged into one block** where a caption sits between two figures (ES&T, Figures 4 and 5). Merged captions are now split.
4. **Springer captions** ("Fig. 2" with special spaces and no period), with chart legends taken for captions. Both handled.
5. **Textbook chapter numbering** (Figure 33.4) is now understood.

Other changes:
- **Answer cache.** Claude's answers are saved, keyed by image, prompt and model, so `paperx rebuild` only pays for items that changed.
- **`paperx recheck`** recomputes the completeness flags without parsing or calling Claude.
- **Font styling.** The verifier now ignores italic or bold on ordinary words. Bold and script letters in math symbols still count.
- **Prompt version.** The verifier prompt's version is recorded with each paper (`claude_tokens.prompt_version`). Papers verified before the styling change have no version recorded.

Remaining open errors after re-verification, 9 in all, each flagged with its page region:
- **Numbered items not found (5):**
  - PFAS review, Table 2: its caption is really its footnote.
  - Survey paper, Tables 1 and 2: the layout is a questionnaire.
  - Cooper scan, Figure 6.
  - Chapra chapter, Figures 33.1, 33.5 and 33.6.
- **Still failing after 2 correction rounds (3):**
  - Cooper equation 3: a two-way equilibrium arrow, with +H₂O above and −H₂O below, extracted as a single arrow.
  - Chapra equation 51: the crop cuts off part of the equation.
  - Passive-sampler Table 3: bullet symbols.
- **No reference list:** the Chapra chapter. That's normal for a textbook chapter, and should be downgraded for documents identified as chapters.

The Chapra chapter has no reference list, as expected for a textbook chapter. The check currently reports that as an error. It should be downgraded for documents identified as chapters.

## Figure data: pilot (2026-11-17)

This is new scope beyond the plan. Tarek wants chart data from earlier papers as validation data for simulation studies. `paperx figdata` and `extract --figure-data` work in five steps:
1. classify each figure
2. extract each panel's axes and series
3. re-plot the data with matplotlib
4. a fresh Claude call compares the original and the re-plot side by side
5. on failure, correct and recheck, up to 2 rounds

`paperx dataset` packages verified chart values and tables with full provenance.

**Benchmark: six charts drawn from known data.** The charts are `bench/figdata_bench.py`: DO-sag points with a model curve, a scatter, grouped bars with error bars, a log-scale decay, a two-panel figure, and three overlapping curves without markers. Every true point was found on every chart.

| Chart | Status | Median error | Worst error |
| --- | --- | --- | --- |
| DO sag | pass | 0.1% | 1.0% |
| Scatter | pass | 0.0% | 0.2% |
| Bars with error bars | pass | 0.0% | 0.2% |
| Log-scale decay | pass | 0.09% | 0.38% |
| Two panels | pass | 0.0% | 0.4% |
| Overlapping curves | pass | 0.24% | 1.5% |

Errors are percentages of the y-axis range; on log axes, of the decades shown. About 18k tokens per chart (27k for the dense curves).

**Pilot on 15 real figures from 7 papers.** 2 were correctly classified as not charts: a dialog-box screenshot and a velocity-vector field. Of the 13 charts:
- **7 passed on the first check:** the bioretention lag-time bars, the log-scale gene-copy bars (all 22 values I checked by eye were within ±0.1 decade), the fungal growth curves, the four-panel glucose/DO figure with a second y axis, the ES&T catalase panels, a CFD residence-time figure, and the Cooper peroxide decay (scanned).
- **5 passed after correction:** the PCA biplot, Aquasim Figure 19 (scanned), the CFD residence-time curves with a second y axis, the Cooper absorption spectra (scanned), and the 1981 vertical-profile plot (depth inverted, three x axes). I checked the last by hand against its tick marks: temperature 22.0 °C, optical density 1.34, light 8.0 klx at the top of the profile, all matching.
- **1 failed, correctly flagged:** Aquasim Figure 22. Its time axis has no ticks, only two date labels, so timing cannot be read reliably. Digitize it by hand if it is needed.

What the pilot changed in the design, each with a test:
- **Axes.** A chart can list any number of axes (bottom, top, left, right; linear, log or categorical; inverted), and each series names the axes it is read against. This was needed for twin-y bioreactor plots and limnology profiles.
- **Curves.** Curves without markers are sampled at 20 to 40 points, denser where they bend. The check judges the sampled points, not the straight lines drawn between them.
- **Records.** Detection-limit marks and axis caveats (for example, unevenly spaced ticks) are kept in each panel's `notes`.

The benchmark, pilot and re-runs used 1.34 million tokens of Claude plan usage. A typical chart uses 20 to 40k tokens, and up to about 90k for a multi-panel figure that needs correction rounds.

**Packaged result:** `PaperX/datasets/pilot-figure-data/`. It holds 601 chart values from the 12 verified charts, plus 13 verified tables, with citation, DOI, figure, page, axis units, scale and direction, reading precision and verification status on every row. In Claude Code, the `paperx-extract` skill runs the whole workflow when you point at a paper.

## Validation papers: contact tanks (2026-11-17)

Tarek's three papers, kept in `PaperX/validation papers/`:
- Aral 2022 (Water)
- Tafarojnoruz et al. 2025 (Fluids)
- Han et al. 2024 (Environmental Science and Pollution Research)

All were run with `--figure-data` and packaged in `PaperX/datasets/contact-tank-validation/`. All 68 tables and equations were verified (12 after correction), and all 14 charts were verified (3 after correction). The 1,688 chart values include E(θ) and F(θ) curves for every tank configuration, field and CFD chlorine residuals, and grid-sensitivity profiles. The only open item is Aral's Figure 11, a baffle schematic that MinerU did not detect; it holds no data.

Two new caption problems were fixed along the way, each with a test:
- MDPI PDFs carry a hidden duplicate text layer, so captions arrived garbled, repeated or truncated. A new `clean_caption()` handles this.
- Springer captions with a leading panel letter ("(b) Fig. 4 Grid…") or a side caption without punctuation ("Fig. 6 Normalized…") were not recognized. Both are now.

`extract --reuse-raw` resumes an interrupted run without re-parsing. These runs used about 0.9 million tokens of plan usage, including the first, interrupted run.

Provenance note: the experimental points ("EXP") in Han et al. Figures 5 and 6 are Kim et al. (2010) tracer data re-plotted from that paper. Cite Kim et al. (2010) when using them.

## Recommended next steps

1. For simulation validation, pick 3 to 5 key figures and digitize them by hand, for example with WebPlotDigitizer. Comparing them with paperx's values measures accuracy on your own figure types before you rely on it.
2. Watch plan usage on large batches: at a 500k cap, one long paper can use as much as a whole short batch. Consider a per-page cap if rate limits bite.
3. Decide on Docker Desktop (WSL2). It unblocks GROBID and a fair Marker trial for the Phase 2 bake-off.
4. Pick the 10 Phase 1 papers and assign the ground-truth correction. Settle the definitions above (equation metric, spanning cells, multi-panel figures, schemes) before labeling, because they change how labels are written.
5. Answer the open questions: hosted-parser benchmark, accuracy bars, Crossref vs. OpenAlex.
