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


def build_pipeline(backlog: list[dict]) -> str:
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

    def cell(val: str) -> str:
        v = (val or "").strip()
        if v.upper() == "TBD" or v == "":
            return '<td class="tbd">TBD</td>'
        return f"<td>{esc(v)}</td>"

    body = []
    for j in journals:
        checked = (j.get("guidelines_last_checked") or "").strip()
        n = days_since(checked)
        stale = n is None or n > 90
        has_tbd = any((j.get(k) or "").strip().upper() in ("", "TBD")
                      for k in ("body_words", "references_max", "figures_tables_max"))
        oa = (j.get("oa_model") or "").strip()
        apc = (j.get("apc_usd") or "").strip()
        apc_cell = f'<td class="{"apc" if "gold" in oa.lower() else ""}">{esc(apc or "–")}</td>'
        chk_cell = (f'<td class="{"stale" if stale else ""}">{esc(checked or "never")}</td>')
        notes = (j.get("notes") or "").strip()
        note_short = notes if len(notes) <= 130 else notes[:127] + "…"
        search = " ".join([j.get("journal", ""), j.get("article_type", ""),
                           j.get("publisher", ""), j.get("society", ""), notes]).lower()
        body.append(f"""
        <tr data-type="{esc(j.get('article_type'))}" data-tbd="{int(has_tbd)}"
            data-stale="{int(stale)}" data-search="{esc(search)}">
          <td class="jname">{esc(j.get('journal'))}<span class="pub">{esc(j.get('publisher'))}</span></td>
          <td>{esc(j.get('article_type'))}</td>
          <td class="c">{esc(j.get('unsolicited'))}</td>
          {cell(j.get('body_words'))}
          {cell(j.get('abstract_words'))}
          {cell(j.get('references_max'))}
          {cell(j.get('figures_tables_max'))}
          <td>{esc(j.get('reporting_guideline'))}</td>
          {apc_cell}
          <td class="c">{esc(j.get('photoprotection_fit'))}</td>
          {chk_cell}
          <td class="note" title="{esc(notes)}">{esc(note_short)}</td>
        </tr>""")

    return f"""
      <div class="filters">
        <input type="search" id="jq" placeholder="Search journal / notes / publisher…">
        <select id="jtype"><option value="">All article types</option>{opts}</select>
        <label><input type="checkbox" id="jtbd"> only rows with TBD specs</label>
        <label><input type="checkbox" id="jstale"> only stale IFA (&gt;90d / never)</label>
        <span id="jcount" class="jcount"></span>
      </div>
      <div class="scroll">
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
  --bg:#f6f7f9; --panel:#fff; --ink:#1c2024; --muted:#6b7280; --line:#e3e6ea;
  --accent:#2563eb; --gl:#16a34a; --dev:#2563eb; --park:#d97706; --kill:#dc2626;
  --old:#dc2626; --stale:#d97706; --fresh:#16a34a; --never:#9ca3af;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#0f1216; --panel:#161a20; --ink:#e6e8eb; --muted:#9199a4; --line:#262c34;
  --accent:#5b9bff;
}}
html,body{margin:0}
body{background:var(--bg);color:var(--ink);
  font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
a{color:var(--accent)}
code{font:12px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;
  background:rgba(127,127,127,.14);padding:.06em .35em;border-radius:4px}
header.top{position:sticky;top:0;z-index:5;background:var(--panel);
  border-bottom:1px solid var(--line);padding:14px 20px 0}
h1{font-size:16px;margin:0 0 2px}
.sub{color:var(--muted);font-size:12px;margin-bottom:10px}
.stats{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:12px;color:var(--muted);margin-bottom:10px}
.stats b{color:var(--ink)}
nav{display:flex;gap:4px}
nav button{appearance:none;border:1px solid var(--line);border-bottom:none;
  background:transparent;color:var(--muted);padding:8px 14px;font-size:13px;
  border-radius:8px 8px 0 0;cursor:pointer}
nav button.on{background:var(--bg);color:var(--ink);font-weight:600}
main{padding:18px 20px 60px;max-width:1280px}
.panel[hidden]{display:none}
h2.ptitle{font-size:14px;margin:0 0 12px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
.hint,.note-p{font-size:12px;color:var(--muted);margin:0 0 12px}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:10px;background:var(--panel)}

/* board */
.board{display:flex;gap:12px;overflow-x:auto;padding-bottom:8px}
.col{flex:0 0 270px;background:var(--panel);border:1px solid var(--line);border-radius:10px}
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
.card-meta{font-size:11px;color:var(--muted)}
.card-j{font-size:11px;margin-top:6px}
.card-next{font-size:11px;margin-top:6px;color:var(--muted)}
.tag{display:inline-block;font-size:10px;padding:1px 6px;border-radius:999px;margin-top:8px}
.tag-ex{background:rgba(217,119,6,.18);color:var(--park)}

/* grids */
table.grid{border-collapse:collapse;width:100%;font-size:12.5px}
table.grid th,table.grid td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
table.grid th{position:sticky;top:0;background:var(--panel);font-size:11px;
  text-transform:uppercase;letter-spacing:.03em;color:var(--muted)}
table.grid td.c{text-align:center}
.t-label{font-weight:600;margin-bottom:2px}
.age-old{color:var(--old);font-weight:600}
.age-stale{color:var(--stale)}
.age-fresh{color:var(--fresh)}
.age-never{color:var(--never);font-weight:600}
td.tbd{color:var(--park);font-weight:600}
td.stale,td .stale{color:var(--old);font-weight:600}
td.apc{color:var(--park)}
.jname{font-weight:600}
.jname .pub{display:block;font-weight:400;color:var(--muted);font-size:11px}
td.note{max-width:280px;color:var(--muted)}
.filters{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:12px}
.filters input[type=search],.filters select{padding:6px 8px;border:1px solid var(--line);
  border-radius:7px;background:var(--panel);color:var(--ink);font-size:12.5px}
.filters input[type=search]{min-width:240px}
.filters label{font-size:12px;color:var(--muted);display:flex;align-items:center;gap:4px}
.jcount{font-size:12px;color:var(--muted);margin-left:auto}

/* digest */
.digest-pick{margin-bottom:14px}
.digest-pick select{padding:6px 8px;border:1px solid var(--line);border-radius:7px;
  background:var(--panel);color:var(--ink)}
.md-body{background:var(--panel);border:1px solid var(--line);border-radius:10px;
  padding:20px 26px;max-width:860px}
.md-body h1{font-size:19px;margin:.2em 0 .5em}
.md-body h2{font-size:16px;margin:1.4em 0 .5em;padding-bottom:.2em;border-bottom:1px solid var(--line)}
.md-body h3{font-size:14px;margin:1.2em 0 .4em}
.md-body table{border-collapse:collapse;width:100%;font-size:12.5px;margin:.6em 0}
.md-body th,.md-body td{border:1px solid var(--line);padding:6px 9px;text-align:left}
.md-body blockquote{margin:.6em 0;padding:.2em 0 .2em 14px;border-left:3px solid var(--line);color:var(--muted)}
.md-body hr{border:none;border-top:1px solid var(--line);margin:1.4em 0}
.md-body ul,.md-body ol{padding-left:22px}
.md-body li{margin:.25em 0}
"""

JS = """
(function(){
  var KEY='ss-dash-tab';
  var btns=[].slice.call(document.querySelectorAll('nav button'));
  var panels=[].slice.call(document.querySelectorAll('.panel'));
  function show(id){
    btns.forEach(function(b){b.classList.toggle('on',b.dataset.panel===id)});
    panels.forEach(function(p){p.hidden=p.id!==id});
    try{localStorage.setItem(KEY,id)}catch(e){}
  }
  btns.forEach(function(b){b.addEventListener('click',function(){show(b.dataset.panel)})});
  var saved;try{saved=localStorage.getItem(KEY)}catch(e){}
  show(document.getElementById(saved)?saved:btns[0].dataset.panel);

  // digest picker
  var sel=document.getElementById('digestPick');
  var host=document.getElementById('digestBody');
  if(sel&&host&&window.DIGESTS){
    function render(){host.innerHTML=window.DIGESTS[sel.value]||'<p>(no digest)</p>'}
    sel.addEventListener('change',render); render();
  }

  // journal filters
  var q=document.getElementById('jq'),ty=document.getElementById('jtype'),
      tb=document.getElementById('jtbd'),st=document.getElementById('jstale'),
      cnt=document.getElementById('jcount'),
      rows=[].slice.call(document.querySelectorAll('#jtable tbody tr'));
  function filt(){
    if(!rows.length)return;
    var s=(q.value||'').toLowerCase().trim(),t=ty.value,
        needTbd=tb.checked,needStale=st.checked,shown=0;
    rows.forEach(function(r){
      var ok=(!s||r.dataset.search.indexOf(s)>=0)
        &&(!t||r.dataset.type===t)
        &&(!needTbd||r.dataset.tbd==='1')
        &&(!needStale||r.dataset.stale==='1');
      r.hidden=!ok; if(ok)shown++;
    });
    cnt.textContent=shown+' / '+rows.length+' rows';
  }
  [q,ty,tb,st].forEach(function(el){el&&el.addEventListener('input',filt)});
  filt();
})();
"""


def build_html(out_path: Path) -> str:
    backlog = load_backlog()
    journals = load_journals()
    topics = load_topics()
    digests = find_digests()

    digest_html: dict[str, str] = {}
    latest_text = ""
    latest_window = ""
    for idx, p in enumerate(digests):
        txt = p.read_text(encoding="utf-8")
        digest_html[p.stem] = render_md(txt)
        if idx == 0:
            latest_text = txt
            latest_window = digest_window(txt)

    dcounts = digest_topic_counts(latest_text, [t["id"] for t in topics])

    # header stats
    real_ideas = [r for r in backlog if not r["_example"]]
    active = [r for r in real_ideas
              if (r.get("status") or "").strip().lower() in
              ("pitched", "drafting", "submitted", "revision")]
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
        f'<div class="digest-pick">Digest: <select id="digestPick">{digest_opts}</select>'
        f'{f" &nbsp;<span class=note-p>{esc(latest_window)}</span>" if latest_window else ""}</div>'
        f'<div id="digestBody" class="md-body"></div>'
        if digests else '<p class="hint">No digests found in <code>digests/</code>.</p>'
    )

    digests_js = json.dumps(digest_html).replace("</", "<\\/")

    gen = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sunscreen Pipeline Dashboard</title>
<style>{CSS}</style>
</head>
<body>
<header class="top">
  <h1>Sunscreen &amp; Photoprotection Pipeline</h1>
  <div class="sub">Read-only view &middot; generated {gen} &middot; run
    <code>python3 scripts/build-dashboard.py</code> to refresh</div>
  <div class="stats">
    <span><b>{len(real_ideas)}</b> ideas ({len(active)} active)</span>
    <span><b>{len(journals)}</b> journal rows &middot; <b>{n_tbd_j}</b> with TBD &middot; <b>{n_stale_j}</b> stale IFA</span>
    <span><b>{len(topics)}</b> topics &middot; <b>{n_never_topics}</b> never reviewed</span>
    <span><b>{len(digests)}</b> digests{f" &middot; latest {esc(digests[0].stem)}" if digests else ""}</span>
  </div>
  <nav>
    <button data-panel="panel-board">Pipeline board</button>
    <button data-panel="panel-digest">Latest digest</button>
    <button data-panel="panel-white">Topic white-space</button>
    <button data-panel="panel-journals">Journal targeting</button>
  </nav>
</header>
<main>
  <section id="panel-board" class="panel">
    <h2 class="ptitle">Pipeline board &mdash; ideas/backlog.csv by status</h2>
    {build_pipeline(backlog)}
  </section>
  <section id="panel-digest" class="panel">
    <h2 class="ptitle">Latest digest &mdash; digests/</h2>
    {digest_panel}
  </section>
  <section id="panel-white" class="panel">
    <h2 class="ptitle">Topic white-space &mdash; taxonomy/topics.yaml</h2>
    {build_whitespace(topics, backlog, dcounts)}
  </section>
  <section id="panel-journals" class="panel">
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
