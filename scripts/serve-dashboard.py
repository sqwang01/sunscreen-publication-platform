#!/usr/bin/env python3
"""Serve the pipeline dashboard locally with an *editable* Pipeline board.

`open dashboard.html` is read-only. This script serves the same dashboard on
http://127.0.0.1:8765 with a Status dropdown and a Next-action field on every
board card. Changing either writes straight back to ideas/backlog.csv (atomic
replace) and logs the change in this terminal. Every other tab is unchanged and
still read-only; nothing here touches the committed index.html or the generated
dashboard.html.

    python3 scripts/serve-dashboard.py [--port 8765] [--no-browser]

Standard library only. Ctrl-C to stop. Review edits with `git diff ideas/backlog.csv`.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import json
import os
import sys
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BACKLOG = REPO / "ideas" / "backlog.csv"

# Only `status` and `next_action` are writable from the board.
EDITABLE_FIELDS = ("status", "next_action")

# Load the hyphenated sibling module (not importable by name).
_spec = importlib.util.spec_from_file_location(
    "build_dashboard", HERE / "build-dashboard.py"
)
bd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bd)


def render_page() -> bytes:
    """Fresh editable dashboard HTML, rebuilt from the flat files on every load."""
    return bd.build_html(REPO / "dashboard.html", editable=True).encode("utf-8")


def update_backlog(idea_id: str, patch: dict) -> dict:
    """Apply {field: value} to the row whose id == idea_id.

    Rewrites only the one changed line so `git diff` stays minimal; every other
    row keeps its bytes. Returns {field: [old, new]} for fields that actually
    changed. Raises KeyError for an unknown id, ValueError for a bad field/value.
    """
    bad = [k for k in patch if k not in EDITABLE_FIELDS]
    if bad:
        raise ValueError("field(s) not editable: " + ", ".join(sorted(bad)))
    if "status" in patch and patch["status"] not in bd.LIFECYCLE:
        raise ValueError(f"unknown status: {patch['status']!r}")

    raw = BACKLOG.read_text(encoding="utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    trailing = raw.endswith(nl)
    lines = raw.split(nl)
    if trailing:
        lines.pop()

    records = list(csv.reader(lines))
    if len(records) != len(lines) or not records:
        raise ValueError("backlog.csv has an unexpected shape; edit it by hand")

    header = records[0]
    missing = [k for k in patch if k not in header]
    if missing:
        raise ValueError("column(s) not in backlog.csv: " + ", ".join(missing))

    tgt = next(
        (i for i in range(1, len(records))
         if records[i] and records[i][0].strip() == idea_id),
        None,
    )
    if tgt is None:
        raise KeyError(idea_id)

    row = dict(zip(header, records[tgt]))
    changed: dict = {}
    for k, v in patch.items():
        v = "" if v is None else str(v).strip()
        old = (row.get(k) or "").strip()
        if v != old:
            row[k] = v
            changed[k] = [old, v]

    if changed:
        buf = io.StringIO()
        csv.writer(buf, lineterminator="").writerow([row.get(h, "") for h in header])
        lines[tgt] = buf.getvalue()
        out = nl.join(lines) + (nl if trailing else "")
        tmp = BACKLOG.with_name(BACKLOG.name + ".tmp")
        tmp.write_text(out, encoding="utf-8")
        os.replace(tmp, BACKLOG)
    return changed


class Handler(BaseHTTPRequestHandler):
    server_version = "SunscreenDash/1.0"

    def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html", "/dashboard.html"):
            try:
                self._send(200, render_page(), "text/html; charset=utf-8")
            except Exception as e:  # noqa: BLE001
                self._send(500, f"build failed: {e}".encode(), "text/plain")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] != "/api/idea":
            self._send(404, json.dumps({"ok": False, "error": "not found"}).encode())
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(n) or b"{}")
            idea_id = str(payload.get("id", "")).strip()
            patch = payload.get("patch") or {}
            if not idea_id:
                raise ValueError("missing id")
            if not isinstance(patch, dict) or not patch:
                raise ValueError("missing patch")
            changed = update_backlog(idea_id, patch)
        except KeyError as e:
            self._send(404, json.dumps({"ok": False, "error": f"no idea {e}"}).encode())
            return
        except (ValueError, json.JSONDecodeError) as e:
            self._send(400, json.dumps({"ok": False, "error": str(e)}).encode())
            return
        except Exception as e:  # noqa: BLE001
            self._send(500, json.dumps({"ok": False, "error": str(e)}).encode())
            return

        stamp = datetime.now().strftime("%H:%M:%S")
        if changed:
            for k, (old, new) in changed.items():
                print(f"[{stamp}] {idea_id}  {k}: {old or '-'} -> {new or '-'}")
        else:
            print(f"[{stamp}] {idea_id}  (no change)")
        self._send(200, json.dumps({"ok": True, "changed": changed}).encode())

    def log_message(self, *_):  # quiet the default per-request line
        pass


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true",
                    help="don't open a browser window")
    args = ap.parse_args()

    if not BACKLOG.exists():
        sys.exit(f"backlog not found: {BACKLOG}")

    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"editable dashboard: {url}")
    print(f"  edits -> {BACKLOG.relative_to(REPO)}  (review with: git diff ideas/backlog.csv)")
    print("  Ctrl-C to stop")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
