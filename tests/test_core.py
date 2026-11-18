from paperx.parsers import html_table_rows, md_table_rows
from paperx.reconcile import caption_label, group_figures, split_references
from paperx.refs import match
from paperx.score import body_score, table_score
from paperx.verify import latex_agreement, table_agreement


def test_body_score_penalizes_order():
    truth = "the quick brown fox jumps over the lazy dog"
    assert body_score(truth, truth) == 1.0
    swapped = "jumps over the lazy dog the quick brown fox"
    assert body_score(swapped, truth) < 0.7


def test_body_score_hyphenation_and_ligature():
    assert body_score("signiﬁcant hydrau-\nlic", "significant hydraulic") == 1.0


def test_table_score_exact_cells():
    t = [["a", "1.0"], ["b", "2.5"]]
    assert table_score(t, t) == 1.0
    assert table_score([["a", "1.0"], ["b", "2.6"]], t) == 0.75


def test_html_rows_expand_spans():
    rows = html_table_rows('<table><tr><th colspan="2">H</th></tr><tr><td rowspan="2">x</td><td>1</td></tr>'
                           "<tr><td>2</td></tr></table>")
    assert rows == [["H", "H"], ["x", "1"], ["x", "2"]]


def test_md_rows_skip_separator():
    assert md_table_rows("| a | b |\n| --- | --- |\n| 1 | 2<sub>3</sub> |") == [["a", "b"], ["1", "2_3"]]


def test_caption_label():
    assert caption_label("Figure 3. Ratio of") == ("figure", "3")
    assert caption_label("Fig. 12 Map") == ("figure", "12")
    assert caption_label("Table 1. Summary") == ("table", "1")
    assert caption_label("Scheme 2. Structure") == ("scheme", "2")
    assert caption_label("The figure shows") == (None, None)


def test_group_figures_merges_panels():
    items = [
        {"kind": "figure", "page": 3, "bbox": [10, 10, 50, 50], "caption": ""},
        {"kind": "figure", "page": 3, "bbox": [60, 10, 100, 50], "caption": ""},
        {"kind": "figure", "page": 3, "bbox": [10, 60, 100, 100], "caption": "Figure 1. Panels"},
    ]
    out = group_figures(items, [])
    figs = [o for o in out if o["kind"] == "figure"]
    assert len(figs) == 1 and figs[0]["bbox"] == [10, 10, 100, 100] and figs[0]["panels"] == 3


def test_split_numbered_references():
    refs = split_references(["(1) Smith, A. Title one. J. X 2001, 1, 2. (2) Jones, B. Title two. J. Y 2002, 3, 4."])
    assert len(refs) == 2 and refs[1].startswith("(2)")


def test_match_requires_title_and_year():
    ref = "Page, S. E. Assessing the contribution of free hydroxyl radical. Environ. Sci. Technol. 2011, 45, 2818."
    good = {"title": ["Assessing the Contribution of Free Hydroxyl Radical"], "issued": {"date-parts": [[2011]]}}
    wrong_year = {"title": ["Assessing the Contribution of Free Hydroxyl Radical"], "issued": {"date-parts": [[1995]]}}
    assert match(ref, [good])[0] is good
    assert match(ref, [wrong_year])[0] is None


def test_crosscheck_agreement():
    assert table_agreement([["k", "1.5", "2e-3"]], [["k", "1.5", "2e-3"]]) == 1.0
    assert table_agreement([["k", "1.5"]], [["k", "1.6"]]) == 0.0
    assert latex_agreement(r"a = \frac{\mathrm{k}}{b} \tag{2}", r"a=\frac{k}{b}") > 0.95


def test_panel_captions_merge_into_numbered_figure():
    items = [
        {"kind": "figure", "page": 7, "bbox": [10, 10, 50, 50], "caption": "(a)"},
        {"kind": "figure", "page": 7, "bbox": [60, 10, 100, 50], "caption": "(b)"},
        {"kind": "figure", "page": 7, "bbox": [10, 60, 100, 100], "caption": "(c) Fig. 3. Prediction of models"},
    ]
    figs = [o for o in group_figures(items, []) if o["kind"] == "figure"]
    assert len(figs) == 1 and figs[0]["panels"] == 3
    assert figs[0]["caption"].startswith("Fig. 3.") and caption_label(figs[0]["caption"]) == ("figure", "3")


def test_scanned_caption_text_groups_pieces():
    items = [
        {"kind": "figure", "page": 2, "bbox": [52, 325, 183, 371]},
        {"kind": "figure", "page": 2, "bbox": [52, 376, 91, 421]},
        {"kind": "text", "page": 2, "bbox": [101, 397, 184, 408], "text": "biofilm reactor compartment"},
        {"kind": "text", "page": 2, "bbox": [51, 472, 186, 505], "text": "Fig. 1: Compartment types available."},
        {"kind": "text", "page": 2, "bbox": [190, 320, 444, 470], "text": "Fig. 1 shows the compartments. " * 5},
    ]
    out = group_figures(items, [])
    figs = [o for o in out if o["kind"] == "figure"]
    assert len(figs) == 1 and figs[0]["caption"].startswith("Fig. 1:") and figs[0]["panels"] == 2
    assert [o["kind"] for o in out if o.get("text", "").startswith("biofilm")] == ["_figure_label"]
    assert [o["kind"] for o in out if o.get("text", "").startswith("Fig. 1 shows")] == ["text"]


# ---------------------------------------------------------------- auto-correction loop (no network)

import json as _json

import pypdfium2 as _pdfium
from PIL import Image as _Image

from paperx import verify as _verify


def _fake_archive(tmp_path, csv_text):
    (tmp_path / "tables").mkdir()
    (tmp_path / "raw").mkdir()
    doc = _pdfium.PdfDocument.new()
    doc.new_page(612, 792)
    doc.save(str(tmp_path / "raw" / "source.pdf"))
    doc.close()
    (tmp_path / "tables" / "T1.csv").write_text(csv_text, encoding="utf-8")
    _Image.new("RGB", (10, 10), "white").save(tmp_path / "tables" / "T1.png")
    (tmp_path / "tables" / "T1.json").write_text(_json.dumps({"id": "T1", "number": "1", "page": 1, "bbox": [0, 0, 1, 1]}))
    (tmp_path / "equations.json").write_text("[]")


class _Fake:
    backend, version, model, cost_usd, used_in, used_out, calls, cache_hits = "fake", "", "fake", 0.0, 0, 0, 0, 0

    def __init__(self, good):
        self.good = good

    def check(self, png, kind, extracted):
        if extracted.strip() == self.good:
            return {"status": "pass", "reason": "matches", "errors": []}
        return {"status": "fail", "reason": "plus signs wrong", "errors": [{"location": "B1", "extracted": "þ", "correct": "+"}]}

    def correct(self, png, kind, extracted, errors):
        return {"corrected": self.fix, "changes": ["þ -> +"]}


def test_autocorrect_applies_only_after_fresh_pass(tmp_path, monkeypatch):
    _fake_archive(tmp_path, "a,þ\nb,2\n")
    f = _Fake(good="a,+\nb,2")
    f.fix = "a,+\nb,2"
    monkeypatch.setattr(_verify, "make_verifier", lambda: (f, ""))
    flags = [{"item": "T1", "severity": "error", "reason": "suspect glyphs"}]
    _verify.run(tmp_path, flags, autocorrect=True)
    assert (tmp_path / "tables" / "T1.csv").read_text(encoding="utf-8").strip() == "a,+\nb,2"
    assert (tmp_path / "tables" / "T1.extracted.csv").read_text(encoding="utf-8") == "a,þ\nb,2\n"
    meta = _json.loads((tmp_path / "tables" / "T1.json").read_text())
    assert meta["verification"]["status"] == "pass_after_correction" and meta["corrected"]
    assert not [x for x in flags if x["severity"] == "error"]  # earlier glyph error is resolved


def test_autocorrect_keeps_original_when_recheck_fails(tmp_path, monkeypatch):
    _fake_archive(tmp_path, "a,þ\nb,2\n")
    f = _Fake(good="a,+\nb,2")
    f.fix = "a,+\nb,3"  # a wrong "fix" never passes
    monkeypatch.setattr(_verify, "make_verifier", lambda: (f, ""))
    flags = []
    _verify.run(tmp_path, flags, autocorrect=True)
    assert (tmp_path / "tables" / "T1.csv").read_text(encoding="utf-8") == "a,þ\nb,2\n"
    assert (tmp_path / "tables" / "T1.correction_attempt.csv").exists()
    meta = _json.loads((tmp_path / "tables" / "T1.json").read_text())
    assert meta["verification"]["status"] == "fail" and not meta.get("corrected")
    assert [x for x in flags if x["severity"] == "error" and x["item"] == "T1"]


def test_caption_needs_repair():
    from paperx.verify import caption_needs_repair

    box = [0, 0, 10, 10]
    assert caption_needs_repair({"caption": "人(() hyphil-TrOCsdetected.Dataarereported", "caption_bbox": box}, ("table",))
    assert caption_needs_repair({"caption": "Summary of findings for all five isolates and both probes", "caption_bbox": box}, ("table",))
    assert not caption_needs_repair({"caption": "David Sedlak", "caption_bbox": box}, ("figure", "scheme"))  # a name label
    assert not caption_needs_repair({"caption": "Table 2 Concentrations of biocides", "caption_bbox": box}, ("table",))
    assert not caption_needs_repair({"caption": "garbled 人", "caption_bbox": None}, ("table",))  # nothing to crop


def test_supplementary_numbering():
    from paperx.reconcile import _missing

    assert caption_label("**Figure S2:** Irradiance") == ("figure", "S2")
    full = "as in Figure 2 of the main text. Figure S1 shows ... Figure S2 shows ... Figure S3"
    # SI file: only the S-series counts; S2 is missing, main-paper "Figure 2" is ignored
    f = _missing("figure", r"\bFig(?:ure)?s?\.?\s*(S?)(\d{1,3})", ["S1", "S3"], full, "figures", "x")
    assert len(f) == 1 and "'S2'" in f[0]["reason"]
    # main paper citing its supplement: S-numbers are ignored
    full2 = "Figure 1 and Figure 2; see also Figure S5"
    assert _missing("figure", r"\bFig(?:ure)?s?\.?\s*(S?)(\d{1,3})", ["1", "2"], full2, "figures", "x") == []


def test_merged_captions_split_between_figures():
    from paperx.reconcile import split_captions

    two = "Figure 4. Gene copies per gram. Bars are standard error. Figure 5. Results of a PCA (n = 9)."
    assert split_captions(two) == ["Figure 4. Gene copies per gram. Bars are standard error.",
                                   "Figure 5. Results of a PCA (n = 9)."]
    assert split_captions("Figure 2. As in Figure 1, values are means.") == ["Figure 2. As in Figure 1, values are means."]
    items = [
        {"kind": "figure", "page": 5, "bbox": [158, 66, 334, 265], "caption": "(a) (b)"},
        {"kind": "figure", "page": 5, "bbox": [336, 74, 467, 260], "caption": "(c) (d)"},
        {"kind": "figure", "page": 5, "bbox": [86, 337, 275, 486], "caption": two},
    ]
    figs = [o for o in group_figures(items, []) if o["kind"] == "figure"]
    assert [caption_label(f["caption"]) for f in figs] == [("figure", "4"), ("figure", "5")]
    assert figs[0]["bbox"] == [158, 66, 467, 265] and figs[1]["bbox"] == [86, 337, 275, 486]


def test_springer_side_caption_and_legends():
    items = [
        {"kind": "text", "page": 5, "bbox": [48, 56, 160, 158], "text": "Fig. 2   A Selected strains growth curves"},
        {"kind": "figure", "page": 5, "bbox": [183, 55, 545, 264], "caption": "--A. blazei --A. bisporus"},
        {"kind": "figure", "page": 5, "bbox": [183, 298, 538, 526], "caption": "B -A. blazei -A. bisporus"},
    ]
    figs = [o for o in group_figures(items, []) if o["kind"] == "figure"]
    assert len(figs) == 1 and caption_label(figs[0]["caption"]) == ("figure", "2") and figs[0]["panels"] == 2
    assert figs[0]["legend"].startswith("--A. blazei")


def test_caption_repair_only_when_numbers_missing():
    from paperx.verify import caption_needs_repair

    q = {"caption": "1.1 In which faculty at the university are you currently enrolled?", "caption_bbox": [0, 0, 1, 1]}
    assert not caption_needs_repair(q, ("figure", "scheme"), numbers_missing=False)
    assert caption_needs_repair(q, ("figure", "scheme"), numbers_missing=True)
    garbled = {"caption": "人(() hyphil", "caption_bbox": [0, 0, 1, 1]}
    assert caption_needs_repair(garbled, ("table",), numbers_missing=False)


def test_chapter_numbering():
    from paperx.reconcile import _missing

    assert caption_label("Figure 33.4 Dissolved oxygen sag") == ("figure", "33.4")
    full = "as in Figure 33.1 and Fig. 33.2; Figure 33.3 shows"
    assert _missing("figure", r"\bFig(?:ure)?s?\.?\s*(S?)(\d{1,3}(?:\.\d{1,3})?)", ["33.1", "33.3"], full, "figures", "x")[0]["reason"].count("33.2") == 1
    assert _missing("figure", r"\bFig(?:ure)?s?\.?\s*(S?)(\d{1,3}(?:\.\d{1,3})?)", ["33.1", "33.2", "33.3"], full, "figures", "x") == []


# ---------------------------------------------------------------- figure data (no network)

_FIG = {"panels": [
    {"panel": "a", "title": "DO sag", "chart_type": "line_scatter",
     "x_axis": {"label": "Distance", "unit": "km", "scale": "linear", "min": 0, "max": 50},
     "y_axis": {"label": "DO", "unit": "mg/L", "scale": "linear", "min": 0, "max": 10},
     "series": [{"name": "observed", "points": [{"x": "0", "y": 8.1, "y_low": 7.9, "y_high": 8.3},
                                                {"x": "20", "y": 5.2, "y_low": None, "y_high": None}]}],
     "read_precision": "±0.1 mg/L", "notes": ""},
    {"panel": "b", "title": "Gene copies", "chart_type": "bar",
     "x_axis": {"label": "Treatment", "unit": "", "scale": "categorical", "min": None, "max": None},
     "y_axis": {"label": "copies", "unit": "per g", "scale": "log", "min": 1e4, "max": 1e14},
     "series": [{"name": "NAH", "points": [{"x": "Grass", "y": 1e6, "y_low": 5e5, "y_high": 2e6},
                                           {"x": "Clover", "y": 3e7, "y_low": None, "y_high": None}]}],
     "read_precision": "half a decade", "notes": ""}]}


def test_figdata_replot_and_csv(tmp_path):
    from paperx import figdata

    im = figdata.replot(_FIG)
    assert im.width > 200 and im.height > 200
    pair = figdata.side_by_side(im, im)
    assert pair.width > im.width
    n = figdata.write_csv(_FIG, tmp_path / "F1.data.csv", "F1", "pass")
    lines = (tmp_path / "F1.data.csv").read_text(encoding="utf-8").splitlines()
    assert n == 4 and lines[0].startswith("# F1") and lines[1].startswith("figure,panel,series")
    assert "Grass" in lines[4] and "500000.0" in lines[4]  # old-format panels are still read


def test_figdata_correct_then_pass():
    import copy

    from paperx import figdata
    from PIL import Image

    good = _FIG
    bad = copy.deepcopy(_FIG)
    bad["panels"][0]["series"][0]["points"][1]["y"] = 9.9

    class V:
        backend, version, model, cost_usd, used_in, used_out, calls, cache_hits = "fake", "", "f", 0.0, 0, 0, 0, 0

        def __init__(self):
            self.n_extract = 0

        def _ask(self, png, prompt, schema, system=None):
            if schema is figdata.CLASSIFY_SCHEMA:
                return {"kind": "chart", "chart_types": ["line"], "n_panels": 2, "extractable": True, "reason": ""}
            if schema is figdata.DATA_SCHEMA:
                self.n_extract += 1
                return copy.deepcopy(bad if self.n_extract == 1 else good)
            # check: pass only once the data are the good version
            ok = self.n_extract >= 2
            return {"status": "pass" if ok else "fail", "reason": "",
                    "errors": [] if ok else [{"location": "a/observed x=20", "extracted": "9.9", "correct": "5.2"}]}

    rec = figdata.digitize(V(), Image.new("RGB", (300, 200), "white"), "Figure 1. Test")
    assert rec["status"] == "pass_after_correction" and rec["data"]["panels"][0]["series"][0]["points"][1]["y"] == 5.2


def test_figdata_second_y_axis(tmp_path):
    import copy

    from paperx import figdata

    d = copy.deepcopy(_FIG)
    p = d["panels"][0]
    p["y2_axis"] = {"label": "Glucose", "unit": "g/L", "scale": "linear", "min": 0, "max": 14}
    p["series"].append({"name": "Glucose", "y_axis": "right",
                        "points": [{"x": "0", "y": 12.0, "y_low": None, "y_high": None},
                                   {"x": "40", "y": 4.0, "y_low": None, "y_high": None}]})
    assert figdata.replot(d).width > 200
    figdata.write_csv(d, tmp_path / "f.csv", "F1", "pass")
    rows = (tmp_path / "f.csv").read_text(encoding="utf-8").splitlines()
    assert any(r.startswith("F1,a,Glucose,0,Distance,km,12.0,Glucose,g/L") for r in rows)  # right-hand axis
    assert any(r.startswith("F1,a,observed,0,Distance,km,8.1,DO,mg/L") for r in rows)


def test_figdata_profile_axes(tmp_path):
    """Vertical profile: depth on an inverted y axis, two x axes along the top, one along the bottom."""
    from paperx import figdata

    ax = lambda i, d, pos, lab, unit, lo, hi, inv=False: {"id": i, "direction": d, "position": pos, "label": lab,  # noqa: E731
                                                          "unit": unit, "scale": "linear", "min": lo, "max": hi,
                                                          "inverted": inv}
    pts = lambda pairs: [{"x": str(x), "y": y, "y_low": None, "y_high": None} for x, y in pairs]  # noqa: E731
    d = {"panels": [{"panel": "1", "title": "Profiles", "chart_type": "line",
                     "axes": [ax("x1", "x", "bottom", "Optical density", "", 0, 1.5),
                              ax("x2", "x", "top", "Light intensity", "klx", 0, 16),
                              ax("x3", "x", "top", "Temperature", "degC", 12, 28),
                              ax("y1", "y", "left", "Depth", "m", 0, 2, True)],
                     "series": [{"name": "OD", "x_axis": "x1", "y_axis": "y1", "points": pts([(1.35, 0), (0.1, 2)])},
                                {"name": "Light", "x_axis": "x2", "y_axis": "y1", "points": pts([(9, 0), (0.1, 1)])},
                                {"name": "Temp", "x_axis": "x3", "y_axis": "y1", "points": pts([(21, 0), (14, 2)])}],
                     "read_precision": "", "notes": ""}]}
    assert figdata.replot(d).width > 200
    figdata.write_csv(d, tmp_path / "p.csv", "F2", "pass")
    rows = (tmp_path / "p.csv").read_text(encoding="utf-8").splitlines()
    assert any(r.startswith("F2,1,Temp,21,Temperature,degC,0,Depth,m") for r in rows)
    xa, ya = figdata.series_axes(d["panels"][0], d["panels"][0]["series"][1])
    assert xa["unit"] == "klx" and ya["inverted"] is True


def test_clean_caption_mdpi_layers():
    from paperx.reconcile import clean_caption

    garbled = "Classic Design i 7. E(t) d F(t) l t (E ti (7) d (8)) bt i d f t i l ti f l iFigure 7. E(t) and F(t) plots (Equations (7) and (8))"
    assert clean_caption(garbled) == "Figure 7. E(t) and F(t) plots (Equations (7) and (8))"
    assert clean_caption("gure 10. E(t) and F(t) plots obtained from tracer simulations") .startswith("Figure 10.")
    doubled = "Figure 5. Contact tank baffle configuration for baffles without slotsFigure 5. Contact tank baffle configuration"
    assert clean_caption(doubled) == "Figure 5. Contact tank baffle configuration for baffles without slots"
    assert clean_caption("((a)") == "(a)"
    assert clean_caption("(d) Fi 9. T i l l it it d d t ti di t ib ti i th t t t k ith fi itFigure 9. Typical velocity").startswith("Figure 9. Typical")
    assert clean_caption("Figure 2. As in Figure 1, the mean values.") == "Figure 2. As in Figure 1, the mean values."
    assert clean_caption("(d) Figure 6. Velocity magnitude") == "(d) Figure 6. Velocity magnitude"


def test_clean_caption_truncated_repeat():
    from paperx.reconcile import clean_caption

    assert clean_caption("Figure 16. Convergence trend for the reliability parameter r(X).ure 16. Convergence trend") == \
        "Figure 16. Convergence trend for the reliability parameter r(X)."
    assert clean_caption("Figure 3. Flow at 16 m. Velocity is 2.") == "Figure 3. Flow at 16 m. Velocity is 2."


def test_springer_panel_prefixed_and_side_captions():
    from paperx.reconcile import CAPTION_TEXT_RE

    assert caption_label("(b) Fig. 4 Grid sensitivity. a Velocity along the line") == ("figure", "4")
    assert CAPTION_TEXT_RE.match("Fig. 6 Normalized cumulative residence time distribution at the outlet")
    assert not CAPTION_TEXT_RE.match("Fig. 6 shows that the cumulative distribution rises sharply")
    items = [
        {"kind": "figure", "page": 6, "bbox": [51, 55, 295, 232], "caption": "(a)"},
        {"kind": "figure", "page": 6, "bbox": [301, 55, 543, 232], "caption": "(b) Fig. 4 Grid sensitivity. a Velocity"},
        {"kind": "text", "page": 7, "bbox": [48, 473, 163, 503], "text": "Fig. 6 Normalized cumulative residence time"},
        {"kind": "figure", "page": 7, "bbox": [231, 472, 545, 713], "caption": ""},
    ]
    figs = [o for o in group_figures(items, []) if o["kind"] == "figure"]
    assert [caption_label(f["caption"]) for f in figs] == [("figure", "4"), ("figure", "6")]
    assert figs[0]["panels"] == 2
