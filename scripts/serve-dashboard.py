#!/usr/bin/env python3
"""Serve the pipeline dashboard locally with an *editable* Pipeline board.

`open dashboard.html` is read-only. This script serves the same dashboard on
http://127.0.0.1:8765 with a Status dropdown and a Next-action field on every
board card. Changing either writes straight back to ideas/backlog.csv (atomic
replace) and logs the change in this terminal. The Latest-digest tab also gets
an "Add to backlog" button per ranked idea, which appends a scored row parsed
from the digest. Every other tab is unchanged and still read-only.

    python3 scripts/serve-dashboard.py [--port 8765] [--no-browser] [--publish]

With --publish, a burst of edits is followed (after ~10s of quiet) by a rebuild
of index.html plus a git commit + push, so the change reaches the deployed
Vercel site on its own. Without it, edits stay local and you publish by hand.

Standard library only. Ctrl-C to stop. Review edits with `git diff ideas/backlog.csv`.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BACKLOG = REPO / "ideas" / "backlog.csv"
INDEX = REPO / "index.html"
DIGESTS = REPO / "digests"

# Only `status` and `next_action` are writable from the board.
EDITABLE_FIELDS = ("status", "next_action")

# New backlog rows promoted from a digest get ids I-1, I-2, … (EX-* are demos).
_ID_RE = re.compile(r"^I-(\d+)$")

# Seconds of no edits before --publish rebuilds + commits + pushes.
PUBLISH_QUIET = 10.0

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


def append_idea(digest_stem: str, idea_n: int) -> dict:
    """Append idea #idea_n from digests/<digest_stem>.md as a new backlog.csv row.

    Re-parses the digest server-side (the browser only sends which idea it wants),
    maps it via build-dashboard's digest_idea_to_row, assigns the next free I-N
    id, and appends one line. Refuses a title already present in the backlog.
    Returns {"id", "working_title"}. Raises KeyError (no such idea) / ValueError.
    """
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", digest_stem or ""):
        raise ValueError("bad digest name")
    dpath = DIGESTS / f"{digest_stem}.md"
    if not dpath.exists():
        raise ValueError(f"no digest {digest_stem}")

    ideas = bd.parse_digest_ideas(dpath.read_text(encoding="utf-8"))
    idea = next((x for x in ideas if x["n"] == idea_n), None)
    if idea is None:
        raise KeyError(f"Idea {idea_n} in {digest_stem}")

    fields = bd.digest_idea_to_row(idea, digest_stem,
                                   today=datetime.now().date().isoformat())

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

    want = bd.norm_title(fields.get("working_title"))
    if not want:
        raise ValueError("idea has no working title to add")
    used: set[int] = set()
    for rec in records[1:]:
        row = dict(zip(header, rec))
        if bd.norm_title(row.get("working_title")) == want:
            raise ValueError(f"already in backlog as {row.get('id') or '?'}")
        m = _ID_RE.match((row.get("id") or "").strip())
        if m:
            used.add(int(m.group(1)))

    fields["id"] = f"I-{max(used) + 1 if used else 1}"

    buf = io.StringIO()
    csv.writer(buf, lineterminator="").writerow([fields.get(h, "") for h in header])
    lines.append(buf.getvalue())
    out = nl.join(lines) + (nl if trailing else "")
    tmp = BACKLOG.with_name(BACKLOG.name + ".tmp")
    tmp.write_text(out, encoding="utf-8")
    os.replace(tmp, BACKLOG)
    return {"id": fields["id"], "working_title": fields.get("working_title", "")}


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(REPO), *args],
        capture_output=True, text=True,
    )


class Publisher:
    """Debounced 'rebuild index.html, commit, push' so local edits reach Vercel.

    Disabled unless --publish is passed. Each recorded edit (re)starts a timer;
    once edits stop for PUBLISH_QUIET seconds one commit covers the whole burst.
    Only ideas/backlog.csv and index.html are staged, so unrelated working-tree
    changes are never swept in. A failed push leaves the commit local and says so.
    """

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self._lock = threading.Lock()
        self._pending: list[str] = []
        self._timer: threading.Timer | None = None

    def _arm(self, *notes: str) -> None:
        """Queue changelog notes and (re)start the debounce timer. Caller holds no lock."""
        with self._lock:
            self._pending.extend(notes)
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(PUBLISH_QUIET, self._publish)
            self._timer.daemon = True
            self._timer.start()

    def record(self, idea_id: str, changed: dict) -> None:
        if not self.enabled or not changed:
            return
        self._arm(*(
            f"{idea_id} {old or '-'}→{new or '-'}" if k == "status"
            else f"{idea_id} next_action"
            for k, (old, new) in changed.items()
        ))

    def record_added(self, idea_id: str) -> None:
        if not self.enabled:
            return
        self._arm(f"{idea_id} added")

    def flush(self) -> None:
        """Publish any pending burst now (called on shutdown)."""
        if not self.enabled:
            return
        with self._lock:
            if self._timer:
                self._timer.cancel()
                self._timer = None
        self._publish()

    def _publish(self) -> None:
        with self._lock:
            items, self._pending = self._pending, []
            self._timer = None
        if not items:
            return
        msg = "backlog: " + "; ".join(items)
        try:
            INDEX.write_text(bd.build_html(INDEX, editable=False), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            print(f"  publish skipped — index.html rebuild failed: {e}")
            return
        add = _git("add", "ideas/backlog.csv", "index.html")
        if add.returncode != 0:
            print(f"  publish failed at `git add`: {add.stderr.strip()}")
            return
        if _git("diff", "--cached", "--quiet").returncode == 0:
            print("  nothing to publish")
            return
        commit = _git("commit", "-m", msg)
        if commit.returncode != 0:
            print(f"  publish failed at `git commit`: {commit.stderr.strip()}")
            return
        push = _git("push")
        if push.returncode != 0:
            print(f"  committed locally but push failed: {push.stderr.strip()}\n"
                  f"  run `git push` yourself when ready")
        else:
            print(f"  published → {msg}  (Vercel will redeploy)")


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
        route = self.path.split("?", 1)[0]
        if route not in ("/api/idea", "/api/promote"):
            self._send(404, json.dumps({"ok": False, "error": "not found"}).encode())
            return
        if route == "/api/promote":
            self._do_promote()
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
            self.server.publisher.record(idea_id, changed)
        else:
            print(f"[{stamp}] {idea_id}  (no change)")
        self._send(200, json.dumps({"ok": True, "changed": changed}).encode())

    def _do_promote(self) -> None:
        """POST /api/promote {digest, idea} -> append a new ideas/backlog.csv row."""
        try:
            n = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(n) or b"{}")
            digest = str(payload.get("digest", "")).strip()
            try:
                idea_n = int(payload.get("idea"))
            except (TypeError, ValueError):
                raise ValueError("missing/bad idea number")
            if not digest:
                raise ValueError("missing digest")
            result = append_idea(digest, idea_n)
        except KeyError as e:
            self._send(404, json.dumps({"ok": False, "error": f"not found: {e}"}).encode())
            return
        except (ValueError, json.JSONDecodeError) as e:
            self._send(400, json.dumps({"ok": False, "error": str(e)}).encode())
            return
        except Exception as e:  # noqa: BLE001
            self._send(500, json.dumps({"ok": False, "error": str(e)}).encode())
            return

        stamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{stamp}] {result['id']}  added from {digest} Idea {idea_n}: "
              f"{result['working_title']}")
        self.server.publisher.record_added(result["id"])
        self._send(200, json.dumps({"ok": True, **result}).encode())

    def log_message(self, *_):  # quiet the default per-request line
        pass


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true",
                    help="don't open a browser window")
    ap.add_argument("--publish", action="store_true",
                    help="after each edit burst, rebuild index.html + git commit + push "
                         "so the change reaches the deployed Vercel site")
    args = ap.parse_args()

    try:  # flush log lines as they happen, even when piped to a file
        sys.stdout.reconfigure(line_buffering=True)
    except AttributeError:
        pass

    if not BACKLOG.exists():
        sys.exit(f"backlog not found: {BACKLOG}")
    if args.publish and _git("rev-parse", "--is-inside-work-tree").returncode != 0:
        sys.exit("--publish needs a git repo here")

    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    srv.publisher = Publisher(args.publish)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"editable dashboard: {url}")
    print(f"  edits -> {BACKLOG.relative_to(REPO)}  (review with: git diff ideas/backlog.csv)")
    if args.publish:
        print(f"  --publish ON: index.html rebuild + commit + push, "
              f"{int(PUBLISH_QUIET)}s after the last edit")
    print("  Ctrl-C to stop")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping — flushing any pending publish")
    finally:
        srv.publisher.flush()
        srv.server_close()


if __name__ == "__main__":
    main()
