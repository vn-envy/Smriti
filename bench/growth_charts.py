"""Render offline growth speed/storage charts from a validated summary.

Only rows already present in the summary are plotted. The script refuses
partial, blocked, legacy, or otherwise invalid source artifacts before making
the output directory, so missing 3k/9k/36.5k checkpoints cannot be silently
interpolated.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


TARGET_DAYS = {3000: 30, 9000: 90, 36500: 365}


def _load_plotting():
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError("growth charts require matplotlib; install it in an offline analysis environment") from exc
    return plt


def _validate_summary(summary: dict[str, Any]) -> None:
    reports = summary.get("reports")
    if not isinstance(reports, list) or len(reports) != 3:
        raise ValueError("summary must contain exactly three growth reports")
    for report in reports:
        validity = report.get("validity", {})
        if validity.get("status") != "complete" or validity.get("headline_valid") is not True:
            raise ValueError(
                f"refusing to chart {report.get('track', {}).get('adapter')}: "
                f"source status={validity.get('status')!r}, headline_valid={validity.get('headline_valid')!r}"
            )
        rows = report.get("checkpoint_table")
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"report {report.get('track', {}).get('adapter')} has no measured checkpoints")


def _label(report: dict[str, Any]) -> str:
    track = report["track"]
    adapter = str(track.get("adapter"))
    config = str(track.get("configuration", ""))
    if track.get("kind") == "lexical":
        suffix = " (ANALYZE maintained)" if track.get("gbrain_analyze") else " (default)"
        return "GBrain lexical/no embedding" + suffix
    if adapter == "mem0":
        return "Mem0 semantic / Ollama nomic / local Qdrant (spaCy absent)"
    return "Smriti semantic / Ollama nomic" if "nomic" in config.lower() else "Smriti semantic"


def _short_label(report: dict[str, Any]) -> str:
    """Keep legends readable; full adapter/configuration details stay in the footer."""
    track = report["track"]
    if track.get("kind") == "lexical":
        return "GBrain lexical maintained" if track.get("gbrain_analyze") else "GBrain lexical default"
    return "Mem0 semantic" if str(track.get("adapter")) == "mem0" else "Smriti semantic"


def _series(report: dict[str, Any], field: str) -> tuple[list[int], list[float]]:
    xs: list[int] = []
    ys: list[float] = []
    for row in report.get("checkpoint_table", []):
        x, y = row.get("documents"), row.get(field)
        if isinstance(x, int) and isinstance(y, (int, float)) and y >= 0:
            xs.append(x)
            ys.append(float(y))
    return xs, ys


def _add_days_axis(plt, ax, measured_documents: set[int]):
    exact = [(documents, days) for documents, days in TARGET_DAYS.items() if documents in measured_documents]
    if not exact:
        return None
    top = ax.twiny()
    top.set_xscale("log")
    top.set_xlim(ax.get_xlim())
    top.set_xticks([documents for documents, _ in exact])
    top.set_xticklabels([f"{days} d" for _, days in exact])
    top.set_xlabel("Calendar-day reference (*100 adds/day; exact measured checkpoints only)")
    return top


def _annotate(fig, reports: list[dict[str, Any]]) -> None:
    labels = [_label(report) for report in reports]
    fig.text(
        0.01,
        0.01,
        " | ".join(labels) + "\nLocal API paid cost is shared across tested local routes ($0); hardware/electricity remains unmeasured. No interpolation is plotted.",
        ha="left",
        va="bottom",
        fontsize=8,
    )


def _normalize_svg(path: Path) -> None:
    """Keep generated vector artifacts clean for repository whitespace checks."""
    text = path.read_text(encoding="utf-8")
    path.write_text("\n".join(line.rstrip() for line in text.splitlines()) + "\n", encoding="utf-8")


def render(summary: dict[str, Any], output_dir: str) -> list[str]:
    _validate_summary(summary)
    plt = _load_plotting()
    reports = summary["reports"]
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    colors = {"smriti-nomic": "#2563eb", "mem0": "#16a34a", "gbrain": "#dc2626"}
    paths: list[str] = []

    latency_fig, latency_ax = plt.subplots(figsize=(12, 7))
    measured_documents: set[int] = set()
    for report in reports:
        track = report["track"]
        adapter = str(track.get("adapter"))
        xs, p50 = _series(report, "warm_query_ms_p50")
        _, p95 = _series(report, "warm_query_ms_p95")
        measured_documents.update(xs)
        color = colors.get(adapter, "#6b7280")
        label = _short_label(report)
        style = "--" if track.get("kind") == "lexical" else "-"
        latency_ax.plot(xs, p50, color=color, linestyle=style, marker="o", label=f"{label} p50 (nearest-rank)")
        if len(p95) == len(xs):
            latency_ax.plot(xs, p95, color=color, linestyle=":", marker="x", label=f"{label} p95 (nearest-rank)")
    latency_ax.set_xscale("log")
    latency_ax.set_yscale("log")
    latency_ax.set_xlabel("Corpus documents (log scale)")
    latency_ax.set_ylabel("Warm query latency (ms; nearest-rank p50/p95, log scale)")
    latency_ax.set_title("Growth query latency: measured corpus checkpoints")
    latency_ax.grid(True, which="both", alpha=0.25)
    latency_ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=2, borderaxespad=0)
    _add_days_axis(plt, latency_ax, measured_documents)
    _annotate(latency_fig, reports)
    latency_fig.tight_layout(rect=(0, 0.18, 1, 0.94))
    for extension in ("svg", "png"):
        path = out / f"growth-query-latency.{extension}"
        latency_fig.savefig(path, dpi=160, bbox_inches="tight")
        if extension == "svg":
            _normalize_svg(path)
        paths.append(str(path))
    plt.close(latency_fig)

    storage_fig, storage_ax = plt.subplots(figsize=(12, 7))
    measured_documents = set()
    for report in reports:
        track = report["track"]
        adapter = str(track.get("adapter"))
        xs, ys = _series(report, "storage_mb")
        measured_documents.update(xs)
        color = colors.get(adapter, "#6b7280")
        style = "--" if track.get("kind") == "lexical" else "-"
        storage_ax.plot(xs, ys, color=color, linestyle=style, marker="o", label=_short_label(report))
    storage_ax.set_xscale("log")
    storage_ax.set_yscale("log")
    storage_ax.set_xlabel("Corpus documents (log scale)")
    storage_ax.set_ylabel("On-disk storage (MB, log scale)")
    storage_ax.set_title("Growth storage: measured corpus checkpoints")
    storage_ax.grid(True, which="both", alpha=0.25)
    storage_ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=3, borderaxespad=0)
    _add_days_axis(plt, storage_ax, measured_documents)
    _annotate(storage_fig, reports)
    storage_fig.tight_layout(rect=(0, 0.18, 1, 0.94))
    for extension in ("svg", "png"):
        path = out / f"growth-storage.{extension}"
        storage_fig.savefig(path, dpi=160, bbox_inches="tight")
        if extension == "svg":
            _normalize_svg(path)
        paths.append(str(path))
    plt.close(storage_fig)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", required=True, help="validated bench.growth_report JSON")
    parser.add_argument("--out-dir", required=True, help="audit output directory")
    args = parser.parse_args()
    summary = json.loads(Path(args.summary).read_text())
    for path in render(summary, args.out_dir):
        print(path)


if __name__ == "__main__":
    main()
