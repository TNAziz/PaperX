"""Figure-data accuracy benchmark: charts drawn from known data, read back by paperx.figdata.

Run:  ~/.paperx/envs/main/Scripts/python.exe bench/figdata_bench.py [--only NAME ...]
Writes bench/figdata/<name>.png (the chart), <name>.truth.json, <name>.result.json,
<name>.replot.png and bench/figdata/REPORT.md.

Error is measured relative to the axis span: |y_read - y_true| / (y_max - y_min) on a linear
axis, and |log10 y_read - log10 y_true| / decades on a log axis. For continuous curves drawn
without markers, the reference is the true curve evaluated at the x the model reported.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
OUT = HERE / "figdata"

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from PIL import Image  # noqa: E402

from paperx import figdata  # noqa: E402
from paperx.verify import make_verifier  # noqa: E402

plt.rcParams.update({"font.family": "serif", "font.size": 8, "axes.linewidth": 0.8})
rng = np.random.default_rng(7)


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / f"{name}.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def chart_do_sag():
    x = np.array([0, 5, 10, 15, 20, 25, 30, 40, 50, 60])
    obs = np.round(9.0 - 4.2 * (np.exp(-0.06 * x) - np.exp(-0.25 * x)) / 0.62 + rng.normal(0, 0.15, x.size), 2)
    xc = np.linspace(0, 60, 121)
    model = lambda t: 9.0 - 4.2 * (np.exp(-0.06 * t) - np.exp(-0.25 * t)) / 0.62  # noqa: E731
    fig, ax = plt.subplots(figsize=(3.4, 2.5))
    ax.plot(x, obs, "ko", ms=3.5, label="Observed")
    ax.plot(xc, model(xc), "k-", lw=1, label="Streeter-Phelps model")
    ax.set(xlabel="Distance downstream (km)", ylabel="Dissolved oxygen (mg/L)", xlim=(0, 60), ylim=(0, 10))
    ax.legend(frameon=False)
    save(fig, "do_sag")
    return {"caption": "Figure 3. Observed and modeled dissolved oxygen downstream of the outfall.",
            "panels": [{"y_scale": "linear", "y_span": [0, 10], "x_span": [0, 60], "series": [
                {"name": "Observed", "kind": "points", "x": x.tolist(), "y": obs.tolist()},
                {"name": "Streeter-Phelps model", "kind": "curve", "fn": "do_sag"}]}]}


def chart_scatter():
    meas = np.round(rng.uniform(2, 48, 25), 1)
    pred = np.round(meas * rng.normal(1.0, 0.12, 25) + rng.normal(0, 1.5, 25), 1)
    fig, ax = plt.subplots(figsize=(3.0, 3.0))
    ax.plot(meas, pred, "s", mfc="none", mec="k", ms=4, label="Calibration runs")
    ax.plot([0, 50], [0, 50], "k--", lw=0.8, label="1:1")
    ax.set(xlabel="Measured TSS (mg/L)", ylabel="Predicted TSS (mg/L)", xlim=(0, 50), ylim=(0, 50))
    ax.legend(frameon=False, loc="upper left")
    save(fig, "scatter")
    return {"caption": "Figure 5. Predicted versus measured total suspended solids.",
            "panels": [{"y_scale": "linear", "y_span": [0, 50], "x_span": [0, 50], "series": [
                {"name": "Calibration runs", "kind": "points", "x": meas.tolist(), "y": pred.tolist()}]}]}


def chart_bars():
    cats = ["Control", "Sand", "Biochar", "Compost"]
    series = {"NO3-N": [4.2, 3.1, 1.8, 2.6], "NH4-N": [1.1, 0.9, 0.5, 1.4], "TP": [0.42, 0.30, 0.18, 0.65]}
    err = {k: [round(v * 0.12 + 0.05, 2) for v in vals] for k, vals in series.items()}
    fig, ax = plt.subplots(figsize=(3.6, 2.6))
    w = 0.25
    for i, (k, vals) in enumerate(series.items()):
        ax.bar(np.arange(4) + (i - 1) * w, vals, w, yerr=err[k], capsize=2, label=k,
               color=["0.2", "0.55", "0.85"][i], edgecolor="k", lw=0.5)
    ax.set_xticks(range(4), cats)
    ax.set(ylabel="Effluent concentration (mg/L)", ylim=(0, 5))
    ax.legend(frameon=False)
    save(fig, "bars")
    return {"caption": "Figure 2. Mean effluent nutrient concentrations by filter medium (error bars: SD).",
            "panels": [{"y_scale": "linear", "y_span": [0, 5], "series": [
                {"name": k, "kind": "bars", "x": cats, "y": vals,
                 "y_low": [round(v - e, 3) for v, e in zip(vals, err[k])],
                 "y_high": [round(v + e, 3) for v, e in zip(vals, err[k])]} for k, vals in series.items()]}]}


def chart_log():
    t = np.array([0, 2, 4, 8, 12, 24, 36, 48])
    a = np.round(850 * np.exp(-0.11 * t), 2)
    b = np.round(620 * np.exp(-0.05 * t), 2)
    fig, ax = plt.subplots(figsize=(3.4, 2.5))
    ax.semilogy(t, a, "ko-", ms=3.5, lw=0.8, label="UV/H$_2$O$_2$")
    ax.semilogy(t, b, "k^--", ms=3.5, lw=0.8, label="UV only")
    ax.set(xlabel="Time (h)", ylabel="Concentration (µg/L)", xlim=(0, 50), ylim=(1, 1000))
    ax.legend(frameon=False)
    save(fig, "log_decay")
    return {"caption": "Figure 4. Degradation of the target compound under two treatments.",
            "panels": [{"y_scale": "log", "y_span": [1, 1000], "x_span": [0, 50], "series": [
                {"name": "UV/H2O2", "kind": "points", "x": t.tolist(), "y": a.tolist()},
                {"name": "UV only", "kind": "points", "x": t.tolist(), "y": b.tolist()}]}]}


def chart_two_panel():
    d = np.arange(1, 13)
    q = np.round(12 + 6 * np.sin(d / 2.0) + rng.normal(0, 0.6, 12), 1)
    qe = np.round(rng.uniform(0.6, 1.6, 12), 1)
    sites = ["S1", "S2", "S3", "S4", "S5"]
    load = [3.4, 5.9, 2.2, 7.6, 4.8]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(6.4, 2.4))
    a1.errorbar(d, q, yerr=qe, fmt="ko-", ms=3, lw=0.8, capsize=2)
    a1.set(xlabel="Month", ylabel="Flow (m$^3$/s)", xlim=(0, 13), ylim=(0, 25), title="(a)")
    a2.bar(sites, load, color="0.6", edgecolor="k", lw=0.5)
    a2.set(ylabel="TN load (kg/d)", ylim=(0, 10), title="(b)")
    save(fig, "two_panel")
    return {"caption": "Figure 6. (a) Monthly mean flow with standard deviation; (b) total nitrogen load by site.",
            "panels": [
                {"y_scale": "linear", "y_span": [0, 25], "x_span": [0, 13], "series": [
                    {"name": "*", "kind": "points", "x": d.tolist(), "y": q.tolist(),
                     "y_low": (q - qe).round(2).tolist(), "y_high": (q + qe).round(2).tolist()}]},
                {"y_scale": "linear", "y_span": [0, 10], "series": [
                    {"name": "*", "kind": "bars", "x": sites, "y": load}]}]}


def _curves():
    return {"Reactor 1": lambda t: 2 + 6 * (1 - np.exp(-t / 4)),
            "Reactor 2": lambda t: 2 + 5.5 * (1 - np.exp(-t / 7)) + 0.4 * np.sin(t / 2),
            "Reactor 3": lambda t: 2 + 6.5 * t ** 2 / (25 + t ** 2)}


def chart_dense():
    t = np.linspace(0, 24, 200)
    fig, ax = plt.subplots(figsize=(3.4, 2.5))
    for (name, f), ls in zip(_curves().items(), ["-", "--", ":"]):
        ax.plot(t, f(t), "k" + ls, lw=1, label=name)
    ax.set(xlabel="Time (h)", ylabel="Biomass (g/L)", xlim=(0, 24), ylim=(0, 10))
    ax.legend(frameon=False, loc="lower right")
    save(fig, "dense_curves")
    return {"caption": "Figure 7. Biomass growth in three reactors.",
            "panels": [{"y_scale": "linear", "y_span": [0, 10], "x_span": [0, 24], "series": [
                {"name": n, "kind": "curve", "fn": "dense:" + n} for n in _curves()]}]}


CHARTS = {"do_sag": chart_do_sag, "scatter": chart_scatter, "bars": chart_bars, "log_decay": chart_log,
          "two_panel": chart_two_panel, "dense_curves": chart_dense}


def curve_fn(key):
    if key == "do_sag":
        return lambda t: 9.0 - 4.2 * (np.exp(-0.06 * t) - np.exp(-0.25 * t)) / 0.62
    return _curves()[key.split(":", 1)[1]]


# ------------------------------------------------------------------ scoring


def rel_err(yr, yt, panel):
    lo, hi = panel["y_span"]
    if panel["y_scale"] == "log":
        if yr <= 0 or yt <= 0:
            return 1.0
        return abs(math.log10(yr) - math.log10(yt)) / (math.log10(hi) - math.log10(lo))
    return abs(yr - yt) / (hi - lo)


def _match_series(name, extracted, used):
    if name == "*":
        cands = [s for s in extracted if id(s) not in used]
        return cands[0] if cands else None
    norm = lambda s: "".join(c for c in s.lower() if c.isalnum())  # noqa: E731
    for s in extracted:
        if id(s) not in used and (norm(s["name"]) == norm(name) or norm(name) in norm(s["name"])
                                  or norm(s["name"]) in norm(name)):
            return s
    return None


def score(truth, data):
    errs, err_bars, found, total, extra = [], [], 0, 0, 0
    panels = data.get("panels") or []
    for i, tp in enumerate(truth["panels"]):
        ep = panels[i] if i < len(panels) else {"series": []}
        used = set()
        for ts in tp["series"]:
            es = _match_series(ts["name"], ep.get("series") or [], used)
            if es is None:
                total += len(ts.get("x", [])) or 5
                continue
            used.add(id(es))
            pts = es["points"]
            if ts["kind"] == "curve":
                f = curve_fn(ts["fn"])
                total += len(pts)
                for p in pts:
                    if figdata._is_num(p["x"]):
                        found += 1
                        errs.append(rel_err(p["y"], float(f(figdata._num(p["x"]))), tp))
                continue
            for j, (x, y) in enumerate(zip(ts["x"], ts["y"])):
                total += 1
                if ts["kind"] == "bars":
                    cand = [p for p in pts if str(p["x"]).strip().lower() == str(x).strip().lower()]
                else:
                    xs = tp["x_span"][1] - tp["x_span"][0]
                    cand = [p for p in pts if figdata._is_num(p["x"]) and abs(figdata._num(p["x"]) - x) <= 0.03 * xs]
                    cand.sort(key=lambda p: abs(figdata._num(p["x"]) - x))
                if not cand:
                    continue
                p = cand[0]
                found += 1
                errs.append(rel_err(p["y"], y, tp))
                for key in ("y_low", "y_high"):
                    if key in ts and p.get(key) is not None:
                        err_bars.append(rel_err(p[key], ts[key][j], tp))
            extra += max(0, len(pts) - len(ts["x"])) if ts["kind"] != "curve" else 0
        extra += sum(len(s["points"]) for s in ep.get("series") or [] if id(s) not in used)
    q = lambda v, f: round(f(v) * 100, 2) if v else None  # noqa: E731
    return {"points_found": found, "points_total": total, "extra_points": extra,
            "median_err_pct": q(errs, statistics.median), "p90_err_pct": q(errs, lambda v: sorted(v)[int(0.9 * (len(v) - 1))]),
            "max_err_pct": q(errs, max), "errbar_median_pct": q(err_bars, statistics.median)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    v, why = make_verifier()
    if v is None:
        sys.exit(why)
    rows = []
    for name, make in CHARTS.items():
        if a.only and name not in a.only:
            continue
        truth = make()
        (OUT / f"{name}.truth.json").write_text(json.dumps(truth, indent=1, default=str), encoding="utf-8")
        before = v.used_in + v.used_out
        rec = figdata.digitize(v, Image.open(OUT / f"{name}.png").convert("RGB"), truth["caption"])
        tokens = v.used_in + v.used_out - before
        if rec.get("replot") is not None:
            rec["replot"].save(OUT / f"{name}.replot.png")
        (OUT / f"{name}.result.json").write_text(json.dumps({k: rec[k] for k in rec if k != "replot"}, indent=1,
                                                            default=str), encoding="utf-8")
        s = score(truth, rec.get("data") or {}) if rec.get("data") else {}
        rows.append({"chart": name, "status": rec["status"], "rounds": len(rec.get("steps", [])), "tokens": tokens, **s})
        print(json.dumps(rows[-1]), flush=True)
    cols = ["chart", "status", "rounds", "points_found", "points_total", "extra_points", "median_err_pct",
            "p90_err_pct", "max_err_pct", "errbar_median_pct", "tokens"]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(str(r.get(c, "")) for c in cols) + " |" for r in rows]
    (OUT / "REPORT.md").write_text("Errors are % of the y-axis span (log axes: % of decades shown).\n\n"
                                   + "\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
