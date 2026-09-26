"""Helpers for the Colab notebooks in this folder.

``DriveResults`` zips a run's outputs into one file in the user's Google Drive
and shares that file read-only by link, so the lab box can fetch it over plain
HTTPS (it holds scores, encoder features, timings and logs: no credentials,
no personal data; the texts are public LongMemEval turns). ``run`` streams a
long command's output into the notebook and re-uploads the results every few
minutes, so progress survives a runtime disconnect and can be watched remotely.
"""
import os
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import time
import zipfile


class DriveResults:
    def __init__(self, name: str):
        from google.colab import auth
        from googleapiclient.discovery import build
        auth.authenticate_user()
        self.drive = build("drive", "v3", cache_discovery=False)
        self.name = name
        self.file_id = None
        self.paths = []

    def add(self, *paths: str) -> None:
        self.paths.extend(p for p in paths if p not in self.paths)

    def push(self) -> None:
        from googleapiclient.http import MediaFileUpload
        zpath = os.path.join("/content", self.name)
        tmp = tempfile.mkdtemp()
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
            for root in self.paths:
                files = ([os.path.join(d, f) for d, _, fs in os.walk(root) for f in fs]
                         if os.path.isdir(root) else [root] if os.path.exists(root) else [])
                base = os.path.dirname(root.rstrip("/"))
                for f in files:
                    if f.endswith(("-wal", "-shm", "-journal")):
                        continue
                    src = f
                    if f.endswith(".sqlite"):          # consistent copy of a live database
                        src = os.path.join(tmp, os.path.basename(f))
                        with sqlite3.connect(f, timeout=60) as a, sqlite3.connect(src) as b:
                            a.backup(b)
                    z.write(src, os.path.relpath(f, base))
        shutil.rmtree(tmp, ignore_errors=True)
        media = MediaFileUpload(zpath, mimetype="application/zip", resumable=True)
        if self.file_id is None:
            f = self.drive.files().create(body={"name": self.name}, media_body=media,
                                          fields="id").execute()
            self.file_id = f["id"]
            self.drive.permissions().create(fileId=self.file_id,
                                            body={"type": "anyone", "role": "reader"}).execute()
        else:
            self.drive.files().update(fileId=self.file_id, media_body=media).execute()
        size = os.path.getsize(zpath) / 1e6
        print(f"[{time.strftime('%H:%M:%S')}] uploaded {self.name} ({size:.1f} MB), "
              f"Drive file id {self.file_id}", flush=True)


def run(cmd: str, results: DriveResults = None, every: int = 300, env: dict = None) -> None:
    """Run ``cmd`` in a shell, stream its output, push ``results`` every ``every`` s."""
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1, env={**os.environ, **(env or {})})

    def pump():
        for line in proc.stdout:
            print(line, end="", flush=True)
    t = threading.Thread(target=pump, daemon=True)
    t.start()
    last = time.time()
    while proc.poll() is None:
        time.sleep(5)
        if results is not None and time.time() - last >= every:
            try:
                results.push()
            except Exception as e:                    # an upload hiccup never kills the run
                print("upload failed, will retry:", e, flush=True)
            last = time.time()
    t.join(timeout=10)
    if results is not None:
        results.push()
    if proc.returncode:
        raise RuntimeError(f"command failed ({proc.returncode}): {cmd}")


def wait_http(url: str, timeout: int = 1800, log: str = None, proc_name: str = "",
              proc: subprocess.Popen = None) -> None:
    """Poll ``url`` until it answers 200; show the log tail while waiting.
    Fails fast, with the log tail, if ``proc`` exits first."""
    import urllib.request
    t0 = time.time()
    while time.time() - t0 < timeout:
        if proc is not None and proc.poll() is not None:
            tail = open(log, errors="replace").read()[-3000:] if log and os.path.exists(log) else ""
            raise RuntimeError(f"{proc_name or url} exited with code {proc.returncode}:\n{tail}")
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                if r.status == 200:
                    print(f"{proc_name or url} is up after {time.time() - t0:.0f}s", flush=True)
                    return
        except Exception:
            pass
        if log and os.path.exists(log):
            with open(log, errors="replace") as f:
                tail = f.read().splitlines()[-1:] or [""]
            print(f"[{time.time() - t0:4.0f}s] {tail[0][:160]}", flush=True)
        time.sleep(20)
    raise TimeoutError(f"{url} did not come up in {timeout}s; see {log}")
