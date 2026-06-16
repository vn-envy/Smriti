"""Dataset downloader for the SMRITI benchmark harness.

Zero third-party deps — stdlib urllib only, same as the rest of SMRITI.
Fetches the LongMemEval (cleaned) and LoCoMo datasets into ./data/.

Usage:
    python -m bench.download                 # oracle + locomo (small, fast)
    python -m bench.download --all            # every LongMemEval split + locomo
    python -m bench.download longmemeval_s    # one named dataset
    python -m bench.download --list           # show what's available
    python -m bench.download --out mydata     # custom output directory

LongMemEval-cleaned: https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned
LoCoMo:              https://github.com/snap-research/locomo
"""
from __future__ import annotations

import argparse
import os
import sys
import urllib.request

_HF = "https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/main"
_LOCOMO = "https://raw.githubusercontent.com/snap-research/locomo/main/data"

# name -> (url, output filename). Output names match what bench/run.py expects.
DATASETS = {
    "longmemeval_oracle": (f"{_HF}/longmemeval_oracle.json", "longmemeval_oracle.json"),
    "longmemeval_s": (f"{_HF}/longmemeval_s_cleaned.json", "longmemeval_s_cleaned.json"),
    "longmemeval_m": (f"{_HF}/longmemeval_m_cleaned.json", "longmemeval_m_cleaned.json"),
    "locomo": (f"{_LOCOMO}/locomo10.json", "locomo10.json"),
}

# sensible default: the two small datasets you can run a full pass on quickly
DEFAULT = ["longmemeval_oracle", "locomo"]


def _progress(done: int, total: int, name: str) -> None:
    if total > 0:
        pct = done * 100 // total
        bar = "#" * (pct // 4)
        sys.stdout.write(f"\r  {name:<28} [{bar:<25}] {pct:3d}%  ({done >> 20} MB)")
    else:
        sys.stdout.write(f"\r  {name:<28} {done >> 20} MB")
    sys.stdout.flush()


def download_one(name: str, out_dir: str, force: bool = False) -> str:
    if name not in DATASETS:
        raise KeyError(f"unknown dataset {name!r}; choices: {', '.join(DATASETS)}")
    url, fname = DATASETS[name]
    dest = os.path.join(out_dir, fname)

    if os.path.exists(dest) and not force:
        print(f"  {name:<28} already present ({dest}), skipping — use --force to re-download")
        return dest

    os.makedirs(out_dir, exist_ok=True)
    tmp = dest + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": "smriti-bench/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            done = 0
            with open(tmp, "wb") as f:
                while True:
                    chunk = resp.read(1 << 16)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    _progress(done, total, name)
        sys.stdout.write("\n")
        os.replace(tmp, dest)
    except Exception as e:  # noqa: BLE001 - surface a clean message, clean up partial
        if os.path.exists(tmp):
            os.remove(tmp)
        raise RuntimeError(
            f"failed to download {name} from {url}: {e}\n"
            f"  You can fetch it manually and drop it at {dest}."
        ) from e
    return dest


def main() -> None:
    p = argparse.ArgumentParser(description="Download SMRITI benchmark datasets")
    p.add_argument("names", nargs="*", help=f"datasets to fetch (default: {', '.join(DEFAULT)})")
    p.add_argument("--all", action="store_true", help="download every available dataset")
    p.add_argument("--list", action="store_true", help="list available datasets and exit")
    p.add_argument("--out", default="data", help="output directory (default: data/)")
    p.add_argument("--force", action="store_true", help="re-download even if the file exists")
    args = p.parse_args()

    if args.list:
        print("Available datasets:")
        for name, (url, fname) in DATASETS.items():
            print(f"  {name:<22} -> {fname}")
        print(f"\nDefault set: {', '.join(DEFAULT)}")
        return

    if args.all:
        names = list(DATASETS)
    elif args.names:
        names = args.names
    else:
        names = DEFAULT

    print(f"Downloading {len(names)} dataset(s) into {args.out}/ ...")
    paths = []
    for name in names:
        paths.append(download_one(name, args.out, force=args.force))
    print("\nDone. Files ready:")
    for pth in paths:
        size = os.path.getsize(pth) >> 20 if os.path.exists(pth) else 0
        print(f"  {pth}  ({size} MB)")
    print("\nNext: python -m bench.run --bench longmemeval "
          f"--data {os.path.join(args.out, 'longmemeval_oracle.json')} --mode lite --limit 50")


if __name__ == "__main__":
    main()
