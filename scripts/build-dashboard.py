#!/usr/bin/env python3
"""Build a static, self-contained dashboard.html from the pipeline's flat files.

Read-only viewer. Standard library only - no pip install, no server.
Re-run whenever you edit any of:
  ideas/backlog.csv   journals/journals.csv   taxonomy/topics.yaml   digests/*.md

    python3 scripts/build-dashboard.py [-o OUTPUT]

Panels: Pipeline board | Latest digest | Topic white-space | Journal targeting.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
from datetime import date, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TODAY = date.today()

# ideas/backlog.csv `status` lifecycle, in board order. Anything else is appended.
LIFECYCLE = ["idea", "pitched", "drafting", "submitted", "revision",
             "accepted", "published", "parked", "killed"]

STATUS_LABEL = {s: s.capitalize() for s in LIFECYCLE}


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def esc(s) -> str:
    return html.escape("" if s is None else str(s))


def days_since(datestr: str):
    datestr = (datestr or "").strip()
    if not datestr:
        return None
    try:
        d = datetime.strptime(datestr[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    return (TODAY - d).days


def age_class(n) -> str:
    """Traffic-light bucket for an age in days (None = never)."""
    if n is None:
        return "never"
    if n > 90:
        return "old"
    if n > 30:
        return "stale"
    return "fresh"


def strip_frontmatter(text: str) -> str:
    """Drop a leading --- ... --- YAML block so it isn't rendered as an <hr>."""
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            rest = text[end + 4:]
            return rest[1:] if rest.startswith("\n") else rest
    return text


# --------------------------------------------------------------------------- #
# loaders
# --------------------------------------------------------------------------- #
def load_backlog() -> list[dict]:
    path = REPO / "ideas" / "backlog.csv"
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    for r in rows:
        note = (r.get("notes") or "").strip().lower()
        r["_example"] = note.startswith("example row")
        try:
            r["_score"] = float(r.get("weighted_total") or 0)
        except ValueError:
            r["_score"] = 0.0
    return rows


def load_journals() -> list[dict]:
    path = REPO / "journals" / "journals.csv"
    return list(csv.DictReader(path.open(newline="", encoding="utf-8")))


def load_briefs() -> dict[str, str]:
    """ideas/briefs/<ID>.md -> rendered HTML, keyed by idea id. Skips TEMPLATE.md."""
    d = REPO / "ideas" / "briefs"
    out: dict[str, str] = {}
    if not d.is_dir():
        return out
    for p in sorted(d.glob("*.md")):
        if p.stem == "TEMPLATE":
            continue
        body = strip_frontmatter(p.read_text(encoding="utf-8"))
        out[p.stem] = render_md(body)
    return out


def load_topics() -> list[dict]:
    """Minimal parser for taxonomy/topics.yaml - just the fields the matrix needs."""
    text = (REPO / "taxonomy" / "topics.yaml").read_text(encoding="utf-8")
    topics: list[dict] = []
    cur: dict | None = None
    in_topics = False
    for raw in text.splitlines():
        if re.match(r"^topics:\s*$", raw):
            in_topics = True
            continue
        if not in_topics:
            continue
        m = re.match(r"^\s*-\s+id:\s*(.+?)\s*$", raw)
        if m:
            if cur:
                topics.append(cur)
            cur = {"id": m.group(1).strip(), "label": "",
                   "last_reviewed": "", "known_reviews": 0}
            continue
        if cur is None:
            continue
        m = re.match(r"^\s{2,}(label|last_reviewed|known_reviews):\s*(.*)$", raw)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if key == "known_reviews":
            if val in ("", "[]"):
                cur["known_reviews"] = 0
            else:
                items = re.findall(r'"(?:[^"\\]|\\.)*"', val)
                cur["known_reviews"] = len(items) if items else (1 if val.strip("[] ") else 0)
        else:
            cur[key] = val.strip().strip("\"'")
    if cur:
        topics.append(cur)
    return topics


def find_digests() -> list[Path]:
    d = REPO / "digests"
    if not d.is_dir():
        return []
    files = [p for p in d.glob("*.md") if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.md", p.name)]
    return sorted(files, reverse=True)


def digest_window(text: str) -> str:
    for line in text.splitlines()[:12]:
        m = re.match(r"\s*Window covered:\s*(.+)$", line)
        if m:
            return m.group(1).strip()
    return ""


def digest_topic_counts(text: str, topic_ids: list[str]) -> dict[str, int]:
    """Count ranked-idea `- **Topic:** <slug>` mentions per topic id."""
    counts = {t: 0 for t in topic_ids}
    for line in text.splitlines():
        m = re.match(r"^\s*[-*]\s*\*\*Topic:\*\*\s*(.+)$", line)
        if not m:
            continue
        seg = m.group(1)
        for t in topic_ids:
            if re.search(r"(?<![\w-])" + re.escape(t) + r"(?![\w-])", seg):
                counts[t] += 1
    return counts


# --------------------------------------------------------------------------- #
# tiny markdown -> HTML (headings, hr, blockquote, lists, pipe tables, inline)
# --------------------------------------------------------------------------- #
def _inline(s: str) -> str:
    s = html.escape(s, quote=False)
    codes: list[str] = []

    def stash(m):
        codes.append(m.group(1))
        return f"\x00{len(codes) - 1}\x00"

    s = re.sub(r"`([^`]+)`", stash, s)
    s = re.sub(
        r"\[([^\]]+)\]\(([^)\s]+)\)",
        lambda m: f'<a href="{html.escape(m.group(2), quote=True)}" '
                  f'target="_blank" rel="noopener">{m.group(1)}</a>',
        s,
    )
    s = re.sub(r"\*\*([^*]+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w*])\*([^*\n]+?)\*(?![\w*])", r"<em>\1</em>", s)
    s = re.sub(r"\x00(\d+)\x00", lambda m: f"<code>{codes[int(m.group(1))]}</code>", s)
    return s


def _split_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def _is_block_start(line: str) -> bool:
    return bool(
        re.match(r"^#{1,6}\s+", line)
        or re.match(r"^ {0,3}(-{3,}|\*{3,}|_{3,})\s*$", line)
        or re.match(r"^ {0,3}>", line)
        or re.match(r"^\s*([-*+]|\d+\.)\s+", line)
        or re.match(r"^\s*\|.*\|\s*$", line)
    )


def _render_list(items: list[list]) -> str:
    if not items:
        return ""
    indents = sorted({it[0] for it in items})
    level = {v: k for k, v in enumerate(indents)}
    out: list[str] = []
    stack: list[str] = []
    cur = -1
    for indent, tag, content in items:
        lv = level[indent]
        if lv > cur:
            for _ in range(lv - cur):
                out.append(f"<{tag}><li>")
                stack.append(tag)
            cur = lv
        elif lv < cur:
            for _ in range(cur - lv):
                out.append(f"</li></{stack.pop()}>")
            out.append("</li><li>")
            cur = lv
        else:
            out.append("</li><li>")
        out.append(_inline(content))
    while stack:
        out.append(f"</li></{stack.pop()}>")
    return "".join(out)


def render_md(md: str) -> str:
    lines = md.replace("\r\n", "\n").split("\n")
    n = len(lines)
    i = 0
    out: list[str] = []
    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1
            continue

        m = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if m:
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{_inline(m.group(2))}</h{lvl}>")
            i += 1
            continue

        if re.match(r"^ {0,3}(-{3,}|\*{3,}|_{3,})\s*$", line):
            out.append("<hr>")
            i += 1
            continue

        if re.match(r"^ {0,3}>", line):
            buf = []
            while i < n and lines[i].strip() and re.match(r"^ {0,3}>", lines[i]):
                buf.append(re.sub(r"^ {0,3}>\s?", "", lines[i]))
                i += 1
            out.append("<blockquote>" + render_md("\n".join(buf)) + "</blockquote>")
            continue

        if ("|" in line and i + 1 < n
                and re.match(r"^\s*\|?[\s:\-|]+\|[\s:\-|]*$", lines[i + 1])
                and "-" in lines[i + 1]):
            header = _split_row(line)
            i += 2
            body = []
            while i < n and lines[i].strip() and "|" in lines[i]:
                body.append(_split_row(lines[i]))
                i += 1
            t = ["<table><thead><tr>"]
            t += [f"<th>{_inline(c)}</th>" for c in header]
            t.append("</tr></thead><tbody>")
            for row in body:
                t.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in row) + "</tr>")
            t.append("</tbody></table>")
            out.append("".join(t))
            continue

        if re.match(r"^\s*([-*+]|\d+\.)\s+", line):
            items: list[list] = []
            while i < n:
                lm = re.match(r"^(\s*)([-*+]|\d+\.)\s+(.*)$", lines[i])
                if lm:
                    indent = len(lm.group(1))
                    typ = "ol" if lm.group(2)[:-1].isdigit() else "ul"
                    items.append([indent, typ, lm.group(3)])
                    i += 1
                elif lines[i].strip() == "":
                    j = i + 1
                    while j < n and lines[j].strip() == "":
                        j += 1
                    if j < n and re.match(r"^\s*([-*+]|\d+\.)\s+", lines[j]):
                        i = j
                    else:
                        break
                elif items and re.match(r"^\s+\S", lines[i]) and not _is_block_start(lines[i]):
                    items[-1][2] += " " + lines[i].strip()
                    i += 1
                else:
                    break
            out.append(_render_list(items))
            continue

        buf = [line]
        i += 1
        while i < n and lines[i].strip() and not _is_block_start(lines[i]):
            buf.append(lines[i])
            i += 1
        out.append("<p>" + _inline(" ".join(x.strip() for x in buf)) + "</p>")
    return "\n".join(out)


def decorate_digest(s: str) -> str:
    """Post-process rendered digest HTML: slug h2 anchors for the TOC, wrap each
    ranked-idea section in a card, and turn [GAP?] / [NOISE ...] into pills."""
    def h2(m):
        inner = m.group(1)
        text = re.sub(r"<[^>]+>", "", inner)
        slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "sec"
        return f'<h2 id="d-{slug}">{inner}</h2>'

    s = re.sub(r"<h2>(.*?)</h2>", h2, s, flags=re.S)
    s = s.replace("<table>", '<div class="tbl-scroll"><table>').replace("</table>", "</table></div>")
    s = re.sub(r"<h3>(Idea\s*\d+.*?)</h3>", r'<h3 class="idea-h">\1</h3>', s)
    s = re.sub(r'(<h3 class="idea-h">.*?)(?=<h3|<h2|<hr\s*/?>|$)',
               r'<div class="idea">\1</div>', s, flags=re.S)
    s = s.replace("[GAP?]", '<span class="mk mk-gap">GAP?</span>')
    s = re.sub(r"\[NOISE PATTERN[^\]]*\]",
               '<span class="mk mk-noise">NOISE PATTERN</span>', s)
    s = s.replace("[NOISE]", '<span class="mk mk-noise">NOISE</span>')
    return s


# --------------------------------------------------------------------------- #
# panel builders
# --------------------------------------------------------------------------- #
def score_class(v: float) -> str:
    if v <= 0:
        return "s-none"
    if v >= 4.0:
        return "s-gl"
    if v >= 3.0:
        return "s-dev"
    if v >= 2.0:
        return "s-park"
    return "s-kill"


def build_pipeline(backlog: list[dict], briefs: dict[str, str] | None = None) -> str:
    briefs = briefs or {}
    groups: dict[str, list[dict]] = {}
    for r in backlog:
        st = (r.get("status") or "idea").strip().lower()
        groups.setdefault(st, []).append(r)

    order = [s for s in LIFECYCLE if s in groups] + [s for s in groups if s not in LIFECYCLE]
    cols = []
    for st in order:
        rows = sorted(groups[st], key=lambda r: r["_score"], reverse=True)
        cards = []
        for r in rows:
            v = r["_score"]
            journals = " → ".join(
                j for j in (r.get("target_journal_1"), r.get("target_journal_2"),
                            r.get("target_journal_3")) if j
            )
            ex = '<span class="tag tag-ex">example</span>' if r["_example"] else ""
            bhtml = briefs.get((r.get("id") or "").strip())
            brief = (
                '<details class="brief"><summary>Abstract &amp; significance</summary>'
                f'<div class="brief-body">{bhtml}</div></details>'
            ) if bhtml else ""
            cards.append(f"""
          <article class="card {score_class(v)}">
            <div class="card-top">
              <span class="card-id">{esc(r.get('id'))}</span>
              <span class="card-score">{esc(r.get('weighted_total') or '–')}</span>
            </div>
            <h4>{esc(r.get('working_title'))}</h4>
            <div class="card-meta">{esc(r.get('topic_id'))} &middot; {esc(r.get('proposed_article_type'))}</div>
            {f'<div class="card-j">▸ {esc(journals)}</div>' if journals else ''}
            {f'<div class="card-next"><b>Next:</b> {esc(r.get("next_action"))}</div>' if r.get('next_action') else ''}
            {ex}
            {brief}
          </article>""")
        cols.append(f"""
        <section class="col">
          <header><span>{esc(STATUS_LABEL.get(st, st.capitalize()))}</span><span class="n">{len(rows)}</span></header>
          <div class="col-body">{''.join(cards) or '<p class="empty">—</p>'}</div>
        </section>""")
    return f'<div class="board">{"".join(cols)}</div>'


def build_whitespace(topics: list[dict], backlog: list[dict], dcounts: dict[str, int]) -> str:
    by_topic: dict[str, list[str]] = {}
    for r in backlog:
        if r["_example"]:
            continue
        by_topic.setdefault((r.get("topic_id") or "").strip(), []).append(
            r.get("working_title") or r.get("id") or "")

    rows = []
    for t in topics:
        n = days_since(t["last_reviewed"])
        ac = age_class(n)
        when = t["last_reviewed"] or "never"
        if n is not None:
            when = f"{t['last_reviewed']} &middot; {n}d"
        ideas = by_topic.get(t["id"], [])
        idea_cell = f'<span title="{esc(chr(10).join(ideas))}">{len(ideas)}</span>' if ideas else "0"
        dc = dcounts.get(t["id"], 0)
        rows.append(f"""
        <tr>
          <td><div class="t-label">{esc(t['label'])}</div><code>{esc(t['id'])}</code></td>
          <td class="c age-{ac}">{when}</td>
          <td class="c">{t['known_reviews']}</td>
          <td class="c">{idea_cell}</td>
          <td class="c">{'<b>' + str(dc) + '</b>' if dc else '0'}</td>
        </tr>""")
    return f"""
      <p class="hint">White space = <span class="age-old">last reviewed &gt;90d / never</span> ·
        few known reviews · no backlog idea yet. "In latest digest" counts ranked-idea
        <code>**Topic:**</code> mentions.</p>
      <div class="scroll">
        <table class="grid">
          <thead><tr>
            <th>Topic</th><th>Last reviewed</th><th>Known reviews</th>
            <th>Backlog ideas</th><th>In latest digest</th>
          </tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>"""


def build_journals(journals: list[dict]) -> str:
    types = sorted({(j.get("article_type") or "").strip() for j in journals if j.get("article_type")})
    opts = "".join(f'<option value="{esc(x)}">{esc(x)}</option>' for x in types)

    def cell(val: str, label: str) -> str:
        v = (val or "").strip()
        if v.upper() == "TBD" or v == "":
            return (f'<td class="tbd" data-label="{esc(label)}">'
                    f'<span class="chip chip-tbd">TBD</span></td>')
        return f'<td data-label="{esc(label)}">{esc(v)}</td>'

    body = []
    for j in journals:
        checked = (j.get("guidelines_last_checked") or "").strip()
        n = days_since(checked)
        stale = n is None or n > 90
        has_tbd = any((j.get(k) or "").strip().upper() in ("", "TBD")
                      for k in ("body_words", "references_max", "figures_tables_max"))
        oa = (j.get("oa_model") or "").strip()
        apc = (j.get("apc_usd") or "").strip()
        apc_cls = ' class="apc"' if "gold" in oa.lower() else ""
        apc_cell = f'<td{apc_cls} data-label="APC">{esc(apc or "–")}</td>'
        if stale:
            chk_cell = ('<td data-label="IFA checked">'
                        f'<span class="chip chip-stale">{esc(checked or "never")}</span></td>')
        else:
            chk_cell = f'<td data-label="IFA checked">{esc(checked or "never")}</td>'
        notes = (j.get("notes") or "").strip()
        note_short = notes if len(notes) <= 130 else notes[:127] + "…"
        search = " ".join([j.get("journal", ""), j.get("article_type", ""),
                           j.get("publisher", ""), j.get("society", ""), notes]).lower()
        body.append(f"""
        <tr data-type="{esc(j.get('article_type'))}" data-tbd="{int(has_tbd)}"
            data-stale="{int(stale)}" data-search="{esc(search)}">
          <td class="jname" data-label="Journal">{esc(j.get('journal'))}<span class="pub">{esc(j.get('publisher'))}</span></td>
          <td data-label="Article type">{esc(j.get('article_type'))}</td>
          <td class="c" data-label="Unsol.">{esc(j.get('unsolicited'))}</td>
          {cell(j.get('body_words'), 'Body w')}
          {cell(j.get('abstract_words'), 'Abs w')}
          {cell(j.get('references_max'), 'Refs')}
          {cell(j.get('figures_tables_max'), 'Figs/Tbl')}
          <td data-label="Checklist">{esc(j.get('reporting_guideline'))}</td>
          {apc_cell}
          <td class="c" data-label="Fit">{esc(j.get('photoprotection_fit'))}</td>
          {chk_cell}
          <td class="note" data-label="Notes" title="{esc(notes)}">{esc(note_short)}</td>
        </tr>""")

    body.append('<tr data-empty class="hidden">'
                '<td class="empty-row" colspan="12">No journals match these filters.</td></tr>')

    return f"""
      <div class="filters">
        <input type="search" id="jq" placeholder="Search journal / notes / publisher…">
        <select id="jtype"><option value="">All article types</option>{opts}</select>
        <label><input type="checkbox" id="jtbd"> only rows with TBD specs</label>
        <label><input type="checkbox" id="jstale"> only stale IFA (&gt;90d / never)</label>
        <span id="jcount" class="jcount"></span>
      </div>
      <div class="scroll" id="jscroll">
        <table class="grid" id="jtable">
          <thead><tr>
            <th>Journal</th><th>Article type</th><th>Unsol.</th><th>Body w</th>
            <th>Abs w</th><th>Refs</th><th>Figs/Tbl</th><th>Checklist</th>
            <th>APC</th><th>Fit</th><th>IFA checked</th><th>Notes</th>
          </tr></thead>
          <tbody>{''.join(body)}</tbody>
        </table>
      </div>"""


# --------------------------------------------------------------------------- #
# page
# --------------------------------------------------------------------------- #
CSS = """
*{box-sizing:border-box}
:root{
  --bg:#f6f7f9; --panel:#fff; --ink:#1c2024; --muted:#5b636e; --line:#e3e6ea;
  --accent:#2563eb; --gl:#15803d; --dev:#2563eb; --park:#b45309; --kill:#dc2626;
  --old:#dc2626; --stale:#b45309; --fresh:#15803d; --never:#8b929c;
  --chip-bg:rgba(127,127,127,.14);
  --warn-bg:#fef6e7; --warn-line:#f3d9a4; --warn-ink:#8a5a00;
  --gap-bg:#fdecec;
  --radius:10px;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0f1216; --panel:#161a20; --ink:#e6e8eb; --muted:#98a1ac; --line:#262c34;
  --accent:#5b9bff; --gl:#4ade80; --dev:#5b9bff; --park:#f0b866; --kill:#f87171;
  --old:#f87171; --stale:#f0b866; --fresh:#4ade80; --never:#7b828c;
  --chip-bg:rgba(255,255,255,.10);
  --warn-bg:#2a2213; --warn-line:#4a3c1c; --warn-ink:#e6c07a;
  --gap-bg:#2c1a1a;
}}
:root[data-theme="dark"]{
  --bg:#0f1216; --panel:#161a20; --ink:#e6e8eb; --muted:#98a1ac; --line:#262c34;
  --accent:#5b9bff; --gl:#4ade80; --dev:#5b9bff; --park:#f0b866; --kill:#f87171;
  --old:#f87171; --stale:#f0b866; --fresh:#4ade80; --never:#7b828c;
  --chip-bg:rgba(255,255,255,.10);
  --warn-bg:#2a2213; --warn-line:#4a3c1c; --warn-ink:#e6c07a;
  --gap-bg:#2c1a1a;
}
html,body{margin:0;overflow-x:clip}
body{background:var(--bg);color:var(--ink);
  font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
a{color:var(--accent)}
code{font:12.5px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;
  background:var(--chip-bg);padding:.06em .35em;border-radius:4px}

.stale-banner{background:var(--warn-bg);border-bottom:1px solid var(--warn-line);
  color:var(--warn-ink);padding:8px 20px;font-size:12.5px}
.stale-banner code{background:rgba(127,127,127,.18)}

header.top{position:sticky;top:0;z-index:20;background:var(--panel);
  border-bottom:1px solid var(--line);padding:14px 20px 0}
.top-row{display:flex;justify-content:space-between;align-items:flex-start;gap:16px}
h1{font-size:17px;margin:0 0 2px}
.sub{color:var(--muted);font-size:12px;margin-bottom:12px}
.controls{display:flex;gap:6px;flex:0 0 auto}
.ctl{appearance:none;border:1px solid var(--line);background:var(--bg);color:var(--muted);
  font-size:12px;padding:5px 10px;border-radius:7px;cursor:pointer}
.ctl:hover{color:var(--ink)}
.ctl:focus-visible{outline:2px solid var(--accent);outline-offset:1px}

.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px}
.tile{border:1px solid var(--line);border-radius:var(--radius);padding:9px 12px;background:var(--bg)}
.tile .big{font-size:19px;font-weight:700;line-height:1.1}
.tile .lbl{font-size:10.5px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);margin-top:3px}
.tile .det{font-size:11px;color:var(--muted);margin-top:2px}

nav{display:flex;gap:4px;overflow-x:auto}
nav button{appearance:none;border:1px solid var(--line);border-bottom:none;
  background:transparent;color:var(--muted);padding:9px 15px;font-size:13px;
  border-radius:8px 8px 0 0;cursor:pointer;white-space:nowrap;flex:0 0 auto}
nav button.on{background:var(--bg);color:var(--ink);font-weight:600}
nav button:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}

main{padding:18px 20px 60px;max-width:1180px}
.panel[hidden]{display:none}
.panel:focus{outline:none}
h2.ptitle{font-size:13px;margin:0 0 14px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
.hint,.note-p{font-size:12px;color:var(--muted);margin:0 0 12px}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:var(--radius);background:var(--panel)}

/* board */
.board{display:flex;gap:12px;overflow-x:auto;padding-bottom:8px;
  scroll-snap-type:x proximity;-webkit-overflow-scrolling:touch}
.col{flex:0 0 270px;background:var(--panel);border:1px solid var(--line);
  border-radius:var(--radius);scroll-snap-align:start}
.col>header{display:flex;justify-content:space-between;align-items:center;
  padding:10px 12px;border-bottom:1px solid var(--line);font-weight:600;font-size:13px}
.col>header .n{color:var(--muted);font-weight:500}
.col-body{padding:10px;display:flex;flex-direction:column;gap:10px;min-height:40px}
.empty{color:var(--muted);text-align:center;margin:6px 0}
.card{border:1px solid var(--line);border-left:3px solid var(--never);
  border-radius:8px;padding:10px;background:var(--bg)}
.card.s-gl{border-left-color:var(--gl)} .card.s-dev{border-left-color:var(--dev)}
.card.s-park{border-left-color:var(--park)} .card.s-kill{border-left-color:var(--kill)}
.card-top{display:flex;justify-content:space-between;font-size:11px;color:var(--muted)}
.card-score{font-weight:700;color:var(--ink)}
.card h4{font-size:13px;margin:4px 0 6px;line-height:1.35}
.card-meta{font-size:11.5px;color:var(--muted)}
.card-j{font-size:11.5px;margin-top:6px}
.card-next{font-size:11.5px;margin-top:6px;color:var(--muted)}
.tag{display:inline-block;font-size:10px;padding:1px 6px;border-radius:999px;margin-top:8px}
.tag-ex{background:rgba(180,83,9,.18);color:var(--park)}

/* per-idea expanded brief (ideas/briefs/<id>.md) */
.brief{margin-top:8px;border-top:1px solid var(--line);padding-top:6px}
.brief>summary{cursor:pointer;font-size:11px;font-weight:600;color:var(--accent);
  list-style:none;display:flex;align-items:center;gap:4px}
.brief>summary::-webkit-details-marker{display:none}
.brief>summary::before{content:"\\25B8";font-size:9px;transition:transform .12s}
.brief[open]>summary::before{transform:rotate(90deg)}
.brief-body{font-size:11.5px;line-height:1.5;margin-top:8px;color:var(--ink)}
.brief-body h1{font-size:12.5px;margin:0 0 6px}
.brief-body h2{font-size:11.5px;margin:12px 0 4px;text-transform:uppercase;
  letter-spacing:.03em;color:var(--muted)}
.brief-body h3,.brief-body h4{font-size:11.5px;margin:10px 0 3px}
.brief-body p{margin:5px 0}
.brief-body ul,.brief-body ol{padding-left:16px;margin:5px 0}
.brief-body li{margin:2px 0}
.brief-body blockquote{margin:6px 0;padding:4px 0 4px 9px;border-left:2px solid var(--line);
  color:var(--muted);font-size:10.5px}
.brief-body hr{border:none;border-top:1px solid var(--line);margin:10px 0}
.brief-body code{font-size:10.5px}
.brief-body em{color:var(--muted)}

/* grids */
table.grid{border-collapse:collapse;width:100%;font-size:13px}
table.grid th,table.grid td{text-align:left;padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:top}
body[data-density="compact"] table.grid th,
body[data-density="compact"] table.grid td{padding:6px 10px}
table.grid th{position:sticky;top:0;background:var(--panel);font-size:11px;
  text-transform:uppercase;letter-spacing:.03em;color:var(--muted);z-index:3}
table.grid th.sortable{cursor:pointer;user-select:none;white-space:nowrap}
table.grid th.sortable:hover{color:var(--ink)}
table.grid th.sorted-asc::after{content:" \\25B2";font-size:9px}
table.grid th.sorted-desc::after{content:" \\25BC";font-size:9px}
table.grid td.c{text-align:center}
table.grid tr.hidden{display:none}
.empty-row{padding:20px !important;text-align:center;color:var(--muted)}
.t-label{font-weight:600;margin-bottom:2px}
.age-old{color:var(--old);font-weight:600}
.age-stale{color:var(--stale)}
.age-fresh{color:var(--fresh)}
.age-never{color:var(--never);font-weight:600}
.chip{display:inline-block;font-size:10.5px;font-weight:600;padding:1px 7px;
  border-radius:999px;line-height:1.5;background:var(--chip-bg);color:var(--muted)}
.chip-tbd{background:var(--warn-bg);color:var(--stale)}
.chip-stale{background:var(--gap-bg);color:var(--old)}
td.apc{color:var(--park)}
.jname{font-weight:600}
.jname .pub{display:block;font-weight:400;color:var(--muted);font-size:11px}
td.note{max-width:280px;color:var(--muted)}
.filters{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:12px}
.filters input[type=search],.filters select{padding:6px 8px;border:1px solid var(--line);
  border-radius:7px;background:var(--panel);color:var(--ink);font-size:12.5px}
.filters input[type=search]{min-width:240px}
.filters input:focus-visible,.filters select:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
.filters label{font-size:12px;color:var(--muted);display:flex;align-items:center;gap:4px}
.jcount{font-size:12px;color:var(--muted);margin-left:auto}

/* frozen first column (desktop only) */
@media (min-width:701px){
  #jtable th:first-child,#jtable td:first-child{position:sticky;left:0;background:var(--panel)}
  #jtable td:first-child{z-index:2;box-shadow:1px 0 0 var(--line)}
  #jtable th:first-child{z-index:4}
}

/* digest */
.digest-wrap{display:grid;grid-template-columns:190px minmax(0,1fr);gap:28px;
  align-items:start;max-width:1140px}
.digest-wrap>div{min-width:0}
.toc{position:sticky;top:150px;font-size:12px;border-left:2px solid var(--line);padding-left:12px}
.toc a{display:block;padding:3px 0;color:var(--muted);text-decoration:none;line-height:1.35}
.toc a:hover{color:var(--ink)}
.toc a.active{color:var(--ink);font-weight:600;border-left:2px solid var(--accent);
  margin-left:-14px;padding-left:12px}
.digest-pick{margin-bottom:14px}
.digest-pick select{padding:6px 8px;border:1px solid var(--line);border-radius:7px;
  background:var(--panel);color:var(--ink)}
.md-body{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);
  padding:22px 30px;font-size:15px;line-height:1.65}
.md-body h1{font-size:20px;margin:.2em 0 .5em}
.md-body h2{font-size:16px;margin:1.5em 0 .5em;padding-bottom:.2em;
  border-bottom:1px solid var(--line);scroll-margin-top:150px}
.md-body h3{font-size:14px;margin:1.2em 0 .4em}
.md-body h3.idea-h{margin-top:0}
.md-body .idea{border:1px solid var(--line);border-radius:var(--radius);
  padding:14px 18px;margin:16px 0;background:var(--bg)}
.md-body .tbl-scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:.6em 0}
.md-body table{border-collapse:collapse;width:100%;font-size:12.5px}
.md-body th,.md-body td{border:1px solid var(--line);padding:6px 9px;text-align:left}
.md-body blockquote{margin:.6em 0;padding:.2em 0 .2em 14px;border-left:3px solid var(--line);color:var(--muted)}
.md-body hr{border:none;border-top:1px solid var(--line);margin:1.4em 0}
.md-body ul,.md-body ol{padding-left:22px}
.md-body li{margin:.3em 0}
.mk{display:inline-block;font-size:10px;font-weight:700;letter-spacing:.03em;
  padding:1px 6px;border-radius:4px;vertical-align:middle}
.mk-gap{background:var(--gap-bg);color:var(--old)}
.mk-noise{background:var(--chip-bg);color:var(--muted)}

/* responsive */
@media (max-width:820px){.stats{grid-template-columns:repeat(2,1fr)}}
@media (max-width:700px){
  header.top{padding:12px 14px 0}
  main{padding:16px 14px 50px}
  nav{flex-wrap:wrap;overflow:visible}
  nav button{border-bottom:1px solid var(--line);border-radius:8px}
  nav button.on{border-color:var(--accent)}
  .top-row{flex-wrap:wrap}
  .digest-wrap{grid-template-columns:minmax(0,1fr);gap:14px}
  .md-body{padding:16px 16px;font-size:14.5px}
  .md-body table{table-layout:fixed;width:100%}
  .md-body th,.md-body td{overflow-wrap:anywhere}
  .toc{position:static;border-left:none;border-bottom:1px solid var(--line);
    padding:0 0 8px;display:flex;flex-wrap:wrap;gap:2px 14px}
  .toc a{padding:3px 0}
  .toc a.active{border:none;margin:0;padding:3px 0}
  #jscroll{border:none;background:transparent;overflow:visible}
  #jtable thead{display:none}
  #jtable,#jtable tbody,#jtable tr,#jtable td{display:block;width:auto}
  #jtable tr{border:1px solid var(--line);border-radius:var(--radius);
    margin:12px 0;padding:6px 4px;background:var(--panel)}
  #jtable tr.hidden{display:none}
  #jtable td{border:none;padding:3px 12px;text-align:left;overflow-wrap:anywhere}
  #jtable td::before{content:attr(data-label);display:block;font-size:10px;
    font-weight:600;text-transform:uppercase;letter-spacing:.03em;color:var(--muted)}
  #jtable td.jname{font-size:14px;padding:8px 12px 4px;white-space:normal;overflow-wrap:anywhere}
  #jtable td.jname::before{content:none}
  #jtable td.empty-row{text-align:center;color:var(--muted)}
  #jtable td.empty-row::before{content:none}
  .filters input[type=search]{min-width:0;flex:1 1 100%}
  .jcount{margin-left:0}
}
"""

JS = """
(function(){
  var root=document.documentElement, body=document.body;

  /* ---- theme (Auto / Light / Dark) ---- */
  var THEME='ss-dash-theme', tbtn=document.getElementById('themeBtn');
  var torder=['auto','light','dark'], tlabel={auto:'Auto',light:'Light',dark:'Dark'};
  function applyTheme(v){
    if(v==='auto')root.removeAttribute('data-theme');
    else root.setAttribute('data-theme',v);
    if(tbtn)tbtn.textContent=tlabel[v];
  }
  var curTheme='auto';
  try{curTheme=localStorage.getItem(THEME)||'auto';}catch(e){}
  if(torder.indexOf(curTheme)<0)curTheme='auto';
  applyTheme(curTheme);
  if(tbtn)tbtn.addEventListener('click',function(){
    curTheme=torder[(torder.indexOf(curTheme)+1)%torder.length];
    applyTheme(curTheme);
    try{localStorage.setItem(THEME,curTheme);}catch(e){}
  });

  /* ---- density ---- */
  var DENS='ss-dash-density', dbtn=document.getElementById('densityBtn');
  function applyDens(v){
    body.setAttribute('data-density',v);
    if(dbtn)dbtn.textContent=(v==='compact'?'Compact':'Comfortable');
  }
  var curDens='comfortable';
  try{curDens=localStorage.getItem(DENS)||'comfortable';}catch(e){}
  applyDens(curDens);
  if(dbtn)dbtn.addEventListener('click',function(){
    curDens=(curDens==='compact'?'comfortable':'compact');
    applyDens(curDens);
    try{localStorage.setItem(DENS,curDens);}catch(e){}
  });

  /* ---- staleness banner ---- */
  var sb=document.getElementById('staleBanner');
  if(sb){
    var gen=parseInt(sb.getAttribute('data-generated')||'0',10);
    if(gen){
      var days=Math.floor((Date.now()/1000-gen)/86400);
      if(days>=8){
        sb.innerHTML='Generated '+days+' days ago \\u2014 data may be stale. '+
          'Re-run <code>python3 scripts/build-dashboard.py</code>.';
        sb.hidden=false;
      }
    }
  }

  /* ---- tabs ---- */
  var KEY='ss-dash-tab';
  var btns=[].slice.call(document.querySelectorAll('nav [role=tab]'));
  var panels=[].slice.call(document.querySelectorAll('.panel'));
  function show(id,focus){
    if(!document.getElementById(id))return;
    btns.forEach(function(b){
      var on=b.dataset.panel===id;
      b.classList.toggle('on',on);
      b.setAttribute('aria-selected',on?'true':'false');
      b.tabIndex=on?0:-1;
    });
    panels.forEach(function(p){p.hidden=p.id!==id;});
    try{localStorage.setItem(KEY,id);}catch(e){}
    if(location.hash!=='#'+id){
      try{history.replaceState(null,'','#'+id);}catch(e){location.hash=id;}
    }
    if(focus){var t=document.getElementById('tab-'+id);if(t)t.focus();}
  }
  btns.forEach(function(b,i){
    b.addEventListener('click',function(){show(b.dataset.panel);});
    b.addEventListener('keydown',function(e){
      var n;
      if(e.key==='ArrowRight'||e.key==='ArrowDown')n=i+1;
      else if(e.key==='ArrowLeft'||e.key==='ArrowUp')n=i-1;
      else if(e.key==='Home')n=0;
      else if(e.key==='End')n=btns.length-1;
      else return;
      e.preventDefault();
      n=(n+btns.length)%btns.length;
      show(btns[n].dataset.panel,true);
    });
  });
  var start=(location.hash||'').replace('#','');
  if(!document.getElementById(start)){try{start=localStorage.getItem(KEY);}catch(e){}}
  show(document.getElementById(start)?start:btns[0].dataset.panel);
  window.addEventListener('hashchange',function(){
    var h=(location.hash||'').replace('#','');
    if(document.getElementById(h)&&h.indexOf('panel-')===0)show(h);
  });

  /* ---- sortable .grid tables ---- */
  function cellKey(td){
    var t=(td.textContent||'').trim();
    if(t===''||t==='\\u2013'||t==='-'||/^tbd$/i.test(t)||/^never$/i.test(t))
      return {n:null,s:''};
    var m=t.replace(/[,\\s]/g,'').match(/-?\\d+(\\.\\d+)?/);
    return {n:m?parseFloat(m[0]):null,s:t.toLowerCase()};
  }
  [].slice.call(document.querySelectorAll('table.grid')).forEach(function(tbl){
    if(!tbl.tHead)return;
    var ths=[].slice.call(tbl.tHead.rows[0].cells);
    ths.forEach(function(th,ci){
      th.classList.add('sortable');
      th.setAttribute('role','button');
      th.tabIndex=0;
      function sort(){
        var tb=tbl.tBodies[0];
        var rows=[].slice.call(tb.rows).filter(function(r){return !r.hasAttribute('data-empty');});
        var asc=!th.classList.contains('sorted-asc');
        ths.forEach(function(o){o.classList.remove('sorted-asc','sorted-desc');});
        th.classList.add(asc?'sorted-asc':'sorted-desc');
        var vals=rows.map(function(r){return {r:r,k:cellKey(r.cells[ci])};});
        var allNum=vals.every(function(x){return x.k.n!==null||x.k.s==='';});
        vals.sort(function(a,b){
          var A=a.k,B=b.k,r;
          if(allNum){
            var an=(A.n===null?Infinity:A.n), bn=(B.n===null?Infinity:B.n);
            r=an-bn;
          }else if(A.s===''&&B.s!==''){r=1;}
          else if(B.s===''&&A.s!==''){r=-1;}
          else{r=(A.s<B.s?-1:A.s>B.s?1:0);}
          return asc?r:-r;
        });
        vals.forEach(function(x){tb.appendChild(x.r);});
      }
      th.addEventListener('click',sort);
      th.addEventListener('keydown',function(e){
        if(e.key==='Enter'||e.key===' '){e.preventDefault();sort();}
      });
    });
  });

  /* ---- digest picker + table of contents ---- */
  var sel=document.getElementById('digestPick');
  var host=document.getElementById('digestBody');
  var toc=document.getElementById('digestToc');
  var spy=null;
  function buildToc(){
    if(!toc||!host)return;
    var hs=[].slice.call(host.querySelectorAll('h2[id]'));
    toc.innerHTML=hs.map(function(h){
      return '<a href="#'+h.id+'">'+h.textContent+'</a>';
    }).join('');
    [].slice.call(toc.querySelectorAll('a')).forEach(function(a){
      a.addEventListener('click',function(e){
        var el=document.getElementById(a.getAttribute('href').slice(1));
        if(el){e.preventDefault();el.scrollIntoView({behavior:'smooth',block:'start'});}
      });
    });
    if(spy)spy.disconnect();
    if('IntersectionObserver' in window && hs.length){
      spy=new IntersectionObserver(function(ents){
        ents.forEach(function(en){
          if(en.isIntersecting){
            [].slice.call(toc.querySelectorAll('a')).forEach(function(a){
              a.classList.toggle('active',a.getAttribute('href')==='#'+en.target.id);
            });
          }
        });
      },{rootMargin:'-140px 0px -70% 0px'});
      hs.forEach(function(h){spy.observe(h);});
    }
  }
  if(sel&&host&&window.DIGESTS){
    var render=function(){
      host.innerHTML=window.DIGESTS[sel.value]||'<p>(no digest)</p>';
      buildToc();
    };
    sel.addEventListener('change',render);
    render();
  }

  /* ---- journal filters ---- */
  var q=document.getElementById('jq'),ty=document.getElementById('jtype'),
      tb=document.getElementById('jtbd'),st=document.getElementById('jstale'),
      cnt=document.getElementById('jcount'),
      jtable=document.getElementById('jtable'),
      allTr=jtable?[].slice.call(jtable.querySelectorAll('tbody tr')):[],
      emptyRow=allTr.filter(function(r){return r.hasAttribute('data-empty');})[0],
      rows=allTr.filter(function(r){return !r.hasAttribute('data-empty');});
  function filt(){
    if(!rows.length)return;
    var s=(q.value||'').toLowerCase().trim(),t=ty.value,
        needTbd=tb.checked,needStale=st.checked,shown=0;
    rows.forEach(function(r){
      var ok=(!s||r.dataset.search.indexOf(s)>=0)
        &&(!t||r.dataset.type===t)
        &&(!needTbd||r.dataset.tbd==='1')
        &&(!needStale||r.dataset.stale==='1');
      r.classList.toggle('hidden',!ok); if(ok)shown++;
    });
    if(emptyRow)emptyRow.classList.toggle('hidden',shown!==0);
    cnt.textContent=shown+' / '+rows.length+' rows';
  }
  [q,ty,tb,st].forEach(function(el){el&&el.addEventListener('input',filt);});
  filt();
})();
"""


def build_html(out_path: Path) -> str:
    backlog = load_backlog()
    journals = load_journals()
    topics = load_topics()
    digests = find_digests()
    briefs = load_briefs()

    digest_html: dict[str, str] = {}
    latest_text = ""
    latest_window = ""
    for idx, p in enumerate(digests):
        txt = p.read_text(encoding="utf-8")
        digest_html[p.stem] = decorate_digest(render_md(txt))
        if idx == 0:
            latest_text = txt
            latest_window = digest_window(txt)

    dcounts = digest_topic_counts(latest_text, [t["id"] for t in topics])

    # header stats
    real_ideas = [r for r in backlog if not r["_example"]]
    active = [r for r in real_ideas
              if (r.get("status") or "").strip().lower() in
              ("pitched", "drafting", "submitted", "revision")]
    n_briefs = sum(1 for r in backlog if (r.get("id") or "").strip() in briefs)
    n_tbd_j = sum(
        1 for j in journals
        if any((j.get(k) or "").strip().upper() in ("", "TBD")
               for k in ("body_words", "references_max", "figures_tables_max"))
    )
    n_stale_j = sum(1 for j in journals
                    if (days_since(j.get("guidelines_last_checked")) or 999) > 90)
    n_never_topics = sum(1 for t in topics if not t["last_reviewed"])

    digest_opts = "".join(
        f'<option value="{esc(p.stem)}">{esc(p.stem)}</option>' for p in digests
    )
    digest_panel = (
        '<div class="digest-wrap">'
        '<nav class="toc" id="digestToc" aria-label="Digest contents"></nav>'
        '<div>'
        f'<div class="digest-pick">Digest: <select id="digestPick">{digest_opts}</select>'
        f'{f" &nbsp;<span class=note-p>{esc(latest_window)}</span>" if latest_window else ""}</div>'
        '<div id="digestBody" class="md-body"></div>'
        '</div></div>'
        if digests else '<p class="hint">No digests found in <code>digests/</code>.</p>'
    )

    digests_js = json.dumps(digest_html).replace("</", "<\\/")

    gen = datetime.now().strftime("%Y-%m-%d %H:%M")
    gen_epoch = int(datetime.now().timestamp())
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sunscreen Pipeline Dashboard</title>
<style>{CSS}</style>
</head>
<body>
<div id="staleBanner" class="stale-banner" data-generated="{gen_epoch}" hidden></div>
<header class="top">
  <div class="top-row">
    <div>
      <h1>Sunscreen &amp; Photoprotection Pipeline</h1>
      <div class="sub">Read-only view &middot; generated {gen} &middot; run
        <code>python3 scripts/build-dashboard.py</code> to refresh</div>
    </div>
    <div class="controls">
      <button id="densityBtn" class="ctl" type="button">Comfortable</button>
      <button id="themeBtn" class="ctl" type="button">Auto</button>
    </div>
  </div>
  <div class="stats">
    <div class="tile"><div class="big">{len(real_ideas)}</div><div class="lbl">Ideas</div><div class="det">{len(active)} active &middot; {n_briefs} expanded</div></div>
    <div class="tile"><div class="big">{len(journals)}</div><div class="lbl">Journal rows</div><div class="det">{n_tbd_j} TBD &middot; {n_stale_j} stale IFA</div></div>
    <div class="tile"><div class="big">{len(topics)}</div><div class="lbl">Topics</div><div class="det">{n_never_topics} never reviewed</div></div>
    <div class="tile"><div class="big">{len(digests)}</div><div class="lbl">Digests</div><div class="det">{f"latest {esc(digests[0].stem)}" if digests else "none"}</div></div>
  </div>
  <nav role="tablist" aria-label="Dashboard sections">
    <button role="tab" id="tab-panel-board" aria-controls="panel-board" aria-selected="false" tabindex="-1" data-panel="panel-board">Pipeline board</button>
    <button role="tab" id="tab-panel-digest" aria-controls="panel-digest" aria-selected="false" tabindex="-1" data-panel="panel-digest">Latest digest</button>
    <button role="tab" id="tab-panel-white" aria-controls="panel-white" aria-selected="false" tabindex="-1" data-panel="panel-white">Topic white-space</button>
    <button role="tab" id="tab-panel-journals" aria-controls="panel-journals" aria-selected="false" tabindex="-1" data-panel="panel-journals">Journal targeting</button>
  </nav>
</header>
<main>
  <section id="panel-board" class="panel" role="tabpanel" aria-labelledby="tab-panel-board" tabindex="0">
    <h2 class="ptitle">Pipeline board &mdash; ideas/backlog.csv by status &middot; cards with a brief in ideas/briefs/ expand</h2>
    {build_pipeline(backlog, briefs)}
  </section>
  <section id="panel-digest" class="panel" role="tabpanel" aria-labelledby="tab-panel-digest" tabindex="0">
    <h2 class="ptitle">Latest digest &mdash; digests/</h2>
    {digest_panel}
  </section>
  <section id="panel-white" class="panel" role="tabpanel" aria-labelledby="tab-panel-white" tabindex="0">
    <h2 class="ptitle">Topic white-space &mdash; taxonomy/topics.yaml</h2>
    {build_whitespace(topics, backlog, dcounts)}
  </section>
  <section id="panel-journals" class="panel" role="tabpanel" aria-labelledby="tab-panel-journals" tabindex="0">
    <h2 class="ptitle">Journal targeting &mdash; journals/journals.csv</h2>
    {build_journals(journals)}
  </section>
</main>
<script>window.DIGESTS={digests_js};</script>
<script>{JS}</script>
</body>
</html>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--output", type=Path, default=REPO / "dashboard.html",
                    help="output HTML path (default: repo-root/dashboard.html)")
    args = ap.parse_args()
    html_str = build_html(args.output)
    args.output.write_text(html_str, encoding="utf-8")
    try:
        rel = args.output.relative_to(REPO)
    except ValueError:
        rel = args.output
    print(f"wrote {rel}  ({len(html_str):,} bytes)")
    print(f"open it:  open '{args.output}'")


if __name__ == "__main__":
    main()
