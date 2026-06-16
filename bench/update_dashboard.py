"""Roll benchmark results into smriti-dashboard.html.

Reads the JSON files written by bench.run (and the run_all.sh pass), then
rewrites the benchmark panel of the dashboard with SMRITI's real numbers —
replacing the "your run goes here" placeholder bar.

Usage:
    python -m bench.update_dashboard                       # uses newest bench_results/*/
    python -m bench.update_dashboard bench_results/20260616_120000
    python -m bench.update_dashboard --dashboard smriti-dashboard.html out.json ...

Only the longmemeval_s (full-haystack) results land on the public chart —
the oracle/evidence-only split is easy mode and is NOT comparable to the
published Zep / mem0 / Hindsight bars, so it is deliberately ignored here.

It looks for these result files in the results dir (any subset works):
    lme_s_full.json        -> SMRITI LongMemEval-S (full)   [charted]
    lme_s_lite.json        -> SMRITI LongMemEval-S (lite)   [charted, optional]
    locomo_full.json       -> SMRITI LoCoMo (full)          [charted]
Anything matching "oracle" is skipped. Individual JSON paths may also be
passed as positional args (oracle files among them are still skipped).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import sys

# static published reference bars (the targets to clear)
REFERENCE_BARS = [
    ("Hindsight", "LongMemEval", 91.4, "var(--teal)"),
    ("Zep", "LongMemEval", 63.8, "var(--teal)"),
    ("mem0", "LongMemEval", 49.0, "var(--teal)"),
]


def _acc(path: str):
    """Return accuracy as a percent (float) from a bench result JSON, or None."""
    try:
        with open(path) as f:
            d = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    s = d.get("summary", d)
    acc = s.get("accuracy")
    return round(acc * 100, 1) if isinstance(acc, (int, float)) else None


def gather(results_dir: str, extra_paths) -> dict:
    """Map a logical run name -> accuracy percent.

    Only longmemeval_s and locomo results are charted; oracle is excluded
    because evidence-only is easy mode and not comparable to the reference
    bars.
    """
    named = {
        "lite_lme_s": os.path.join(results_dir, "lme_s_lite.json"),
        "full_lme_s": os.path.join(results_dir, "lme_s_full.json"),
        "locomo": os.path.join(results_dir, "locomo_full.json"),
    }
    out = {k: _acc(p) for k, p in named.items()}
    # allow direct JSON paths: classify by filename hints, skipping oracle
    for p in extra_paths:
        low = p.lower()
        if "oracle" in low:
            print(f"  skipping {p} (oracle split — not comparable, not charted)")
            continue
        a = _acc(p)
        if a is None:
            continue
        if "locomo" in low:
            out["locomo"] = a
        elif "lite" in low:
            out["lite_lme_s"] = a
        else:
            out["full_lme_s"] = a
    return {k: v for k, v in out.items() if v is not None}


def _bar(name, sub, pct, color, *, smriti=False, pct_text=None):
    pct_int = int(round(pct)) if pct is not None else 0
    label = pct_text if pct_text is not None else f"{pct:.1f}%"
    if smriti:
        return (
            f'        <div class="bar-row" data-pct="{pct_int}" id="smriti-bar">\n'
            f'          <div class="nm" style="color:var(--amber)">{name}<small>{sub}</small></div>\n'
            f'          <div class="track" style="border-color:var(--amber-dim)">\n'
            f'            <div class="fill" style="background:var(--amber)"></div>\n'
            f'          </div>\n'
            f'          <div class="pct" style="color:var(--amber)">{label}</div>\n'
            f'        </div>'
        )
    return (
        f'        <div class="bar-row" data-pct="{pct_int}">\n'
        f'          <div class="nm">{name}<small>{sub}</small></div>\n'
        f'          <div class="track"><div class="fill" style="background:{color}"></div></div>\n'
        f'          <div class="pct">{label}</div>\n'
        f'        </div>'
    )


def build_bars(scores: dict) -> str:
    rows = [_bar(n, s, p, c) for n, s, p, c in REFERENCE_BARS]

    lite, full = scores.get("lite_lme_s"), scores.get("full_lme_s")
    if lite is not None or full is not None:
        headline = full if full is not None else lite
        parts = []
        if lite is not None:
            parts.append(f"lite {lite:.1f}%")
        if full is not None:
            parts.append(f"full {full:.1f}%")
        rows.append(_bar("SMRITI", "LongMemEval-S · your run",
                         headline, "var(--amber)", smriti=True,
                         pct_text=" · ".join(parts)))
    else:
        # no LongMemEval numbers yet — keep an honest placeholder bar
        rows.append(
            '        <div class="bar-row" data-pct="0" id="smriti-bar">\n'
            '          <div class="nm" style="color:var(--amber)">SMRITI<small>your run goes here</small></div>\n'
            '          <div class="track" style="border-color:var(--amber-dim)">\n'
            '            <div class="fill" style="background:repeating-linear-gradient(90deg,var(--amber),var(--amber) 6px,transparent 6px,transparent 12px)"></div>\n'
            '          </div>\n'
            '          <div class="pct" style="color:var(--amber)">— · —</div>\n'
            '        </div>'
        )

    if scores.get("locomo") is not None:
        rows.append(_bar("SMRITI", "LoCoMo · your run", scores["locomo"],
                         "var(--amber)", pct_text=f"{scores['locomo']:.1f}%"))

    return "\n".join(rows)


def update(dashboard: str, scores: dict) -> None:
    with open(dashboard, encoding="utf-8") as f:
        html = f.read()

    bars_html = build_bars(scores)
    # replace the inner content of <div class="bars" id="bars"> ... </div>
    pattern = re.compile(
        r'(<div class="bars" id="bars">\n).*?(\n      </div>\n\n      <div class="target">)',
        re.DOTALL,
    )
    if not pattern.search(html):
        sys.exit("ERROR: could not locate the #bars block in the dashboard — "
                 "was the HTML edited? Aborting without changes.")
    html = pattern.sub(lambda m: m.group(1) + bars_html + m.group(2), html)

    # make the reveal animation honor data-pct for the SMRITI bar too
    html = html.replace("(r.id==='smriti-bar'?100:pct)", "pct")

    backup = dashboard + ".bak"
    shutil.copy2(dashboard, backup)
    with open(dashboard, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Updated {dashboard} (backup at {backup})")


def main() -> None:
    p = argparse.ArgumentParser(description="Inject benchmark results into the dashboard")
    p.add_argument("paths", nargs="*", help="results dir and/or individual result JSONs")
    p.add_argument("--dashboard", default="smriti-dashboard.html")
    args = p.parse_args()

    results_dir, extra = "", []
    for pth in args.paths:
        if pth.endswith(".json"):
            extra.append(pth)
        elif os.path.isdir(pth):
            results_dir = pth
    if not results_dir and not extra:
        dirs = sorted(glob.glob("bench_results/*"), reverse=True)
        results_dir = dirs[0] if dirs else ""
        if not results_dir:
            sys.exit("No results found. Pass a results dir or JSON paths, "
                     "or run bench/run_all.sh first.")

    scores = gather(results_dir, extra)
    if not scores:
        sys.exit(f"No usable accuracy numbers found in {results_dir or extra}.")
    print("Scores found:", {k: f"{v}%" for k, v in scores.items()})
    update(args.dashboard, scores)


if __name__ == "__main__":
    main()
