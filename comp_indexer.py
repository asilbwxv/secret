#!/usr/bin/env python2
# -*- coding: utf-8 -*-

"""
Python 2.7.5-compatible script to build a sortable, filterable HTML index of
components present under the current working directory (folders named C00001, C00002, ...).

Columns:
  1) Component (clickable → local folder, if found)
  2) Name (clickable → local folder, if found)
  3) Docs (chips for nearest *.html whose filename contains AD/SD/SID/UG)
  4) CODDA (collapsible list; filenames containing 'codda' or ending '.codda')
  5) DCSL  (collapsible list; filenames containing 'dcsl' or ending '.dcsl')
  6) C/H   (collapsible list; *.c and *.h)
  7) Robot (collapsible list; *.robot)

Usage:
  - Put this script in the parent folder of your C00... directories.
  - Put 'components_map.txt' in the same folder (one "C00001 Name" per line).
  - Run:  python2 build_components_index_py27.py
  - Output: components_index.html (links are relative)
"""

from __future__ import unicode_literals

import os
import re
import codecs
import cgi
from collections import OrderedDict

try:
    # Python 2
    from HTMLParser import HTMLParser
except ImportError:
    # Fallback if running on Py3 by mistake
    from html.parser import HTMLParser

HP = HTMLParser()

# -----------------------------
# Config
# -----------------------------
OUTPUT_HTML = "components_index.html"
MAP_FILE = "components_map.txt"
DOC_TOKENS = ["AD", "SD", "SID", "UG"]  # tokens for docs column

CODE_RE = re.compile(r"^C\d{5}$", re.IGNORECASE)

# -----------------------------
# Helpers
# -----------------------------
def read_components_map(path):
    """Read components from MAP_FILE → OrderedDict(code -> name)."""
    mapping = OrderedDict()
    if not os.path.isfile(path):
        return mapping
    with codecs.open(path, "r", "utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            m = re.match(r"^(C\d{5})\s+(.+)$", line, flags=re.IGNORECASE)
            if m:
                code = m.group(1).upper()
                name = HP.unescape(m.group(2)).strip()
                if code not in mapping:
                    mapping[code] = name
    return mapping

def find_component_folder(base_dir, code):
    """Return direct child folder matching the code (case-insensitive), or None."""
    candidate = os.path.join(base_dir, code)
    if os.path.isdir(candidate):
        return candidate
    # Case-insensitive fallback (handles e.g., c00001)
    for child in os.listdir(base_dir):
        p = os.path.join(base_dir, child)
        if os.path.isdir(p) and child.upper() == code.upper():
            return p
    return None

def walk_files(root):
    """Yield all file paths under root recursively."""
    for r, _dirs, files in os.walk(root):
        for fname in files:
            yield os.path.join(r, fname)

def _path_depth(p):
    """Approximate path depth for tie-breaking (fewer segments preferred)."""
    return len(os.path.normpath(p).split(os.sep))

def _prefer_nearer(current, new_path):
    """Choose the path closer to the component dir; tie → lexicographic."""
    if current is None:
        return new_path
    curr_key = (_path_depth(current), current.lower())
    new_key = (_path_depth(new_path), new_path.lower())
    return new_path if new_key < curr_key else current

def match_docs(comp_dir, code):
    """Pick one nearest *.html per token (AD, SD, SID, UG) and file name must include the component code."""
    found = dict((t, None) for t in DOC_TOKENS)
    up_code = code.upper()
    for p in walk_files(comp_dir):
        lp = p.lower()
        if not lp.endswith(".html"):
            continue
        up = os.path.basename(p).upper()
        if up_code not in up:
            continue
        for t in DOC_TOKENS:
            if t in up:
                found[t] = _prefer_nearer(found[t], p)
    return found

def list_cram_ram(comp_dir, code):
    """
    Collect files whose filename contains the component code AND ('CRAM_UG' or 'RAM-HLR'),
    and whose extension is .xlsm (case-insensitive).
    """
    out = []
    up_code = code.upper()
    for p in walk_files(comp_dir):
        up = os.path.basename(p).upper()
        if up_code in up and ('CRAM_UG' in up or 'RAM-HLR' in up):
            if not p.lower().endswith('.xlsm'):
                continue
            out.append(p)
    return out

def list_codda(comp_dir):
    out = []
    for p in walk_files(comp_dir):
        n = os.path.basename(p).lower()
        if p.lower().endswith(".codda"):
            out.append(p)
    return out

def list_dcsl(comp_dir):
    out = []
    for p in walk_files(comp_dir):
        n = os.path.basename(p).lower()
        if p.lower().endswith(".dcsl"):


            out.append(p)
    return out

def list_ch(comp_dir):
    out = []
    for p in walk_files(comp_dir):
        lp = p.lower()
        if lp.endswith(".c") or lp.endswith(".h"):
            out.append(p)
    return out

def list_robot(comp_dir):
    out = []
    for p in walk_files(comp_dir):
        if p.lower().endswith(".robot"):
            out.append(p)
    return out

def esc(s):
    """HTML-escape (including quotes)."""
    if s is None:
        return ""
    return cgi.escape(s, True)

def rel_href(from_dir, to_path):
    """Relative href from 'from_dir' to 'to_path' with URL-friendly slashes."""
    try:
        rel = os.path.relpath(to_path, from_dir)
    except Exception:
        rel = to_path
    return rel.replace(os.sep, "/")

def _relative_label(p, base):
    """Return label relative to base if under it; else just the basename."""
    try:
        rel = os.path.relpath(p, base)
        if not rel.startswith(".."):
            return rel.replace(os.sep, "/")
    except Exception:
        pass
    return os.path.basename(p)

def details_block(paths, base_dir, display_base):
    """Return collapsible HTML (<details>) listing the given paths."""
    if not paths:
        return u"—"
    paths_sorted = sorted(paths, key=lambda x: x.lower())
    items = []
    for p in paths_sorted:
        href = esc(rel_href(base_dir, p))
        label = esc(_relative_label(p, display_base)) if display_base else esc(os.path.basename(p))
        items.append(u'<li><a href="{0}">{1}</a></li>'.format(href, label))
    return (
        u"<details class='coll'>"
        u"<summary><span class='badge'>{0}</span> files</summary>"
        u"<ul class='filelist'>{1}</ul>"
        u"</details>"
    ).format(len(paths_sorted), u"".join(items))

# -----------------------------
# HTML builder
# -----------------------------
def build_html(entries, base_dir):
    rows = []
    for e in entries:
        code = e["code"]
        name = e["name"]
        folder = e["folder"]

        # Column 1: Component link if folder exists
        if folder:
            code_cell = u'<a href="{0}">{1}</a>'.format(
                esc(rel_href(base_dir, folder)), esc(code)
            )
            name_cell = u'<a href="{0}">{1}</a>'.format(
                esc(rel_href(base_dir, folder)), esc(name)
            )
        else:
            code_cell = u"<span class='missing'>{0}</span>".format(esc(code))
            name_cell = esc(name)

        # Column 3: Docs chips
        chips = []
        for t in DOC_TOKENS:
            p = e["docs"].get(t)
            if p:
                chips.append(u'<a class="chip chip-{0}" href="{1}">{0}</a>'.format(
                    t, esc(rel_href(base_dir, p))
                ))
        docs_cell = u" ".join(chips) if chips else u"—"

        # Collapsible lists
        codda_cell = details_block(e["codda"], base_dir, folder) if folder else u"—"
        dcsl_cell  = details_block(e["dcsl"],  base_dir, folder) if folder else u"—"
        ch_cell    = details_block(e["chs"],   base_dir, folder) if folder else u"—"
        robot_cell = details_block(e["robots"],base_dir, folder) if folder else u"—"
        cramram_cell = details_block(e["cramram"], base_dir, folder) if folder else u"—"

        row = (
            u"<tr>"
            u"<td data-sort='{0}'>{1}</td>"
            u"<td data-sort='{2}'>{3}</td>"
            u"<td>{4}</td>"
            u"<td data-sort='{5:05d}'>{6}</td>"   # CRAM/RAM
            u"<td data-sort='{7:05d}'>{8}</td>"   # CODDA
            u"<td data-sort='{9:05d}'>{10}</td>"  # DCSL
            u"<td data-sort='{11:05d}'>{12}</td>" # C/H
            u"<td data-sort='{13:05d}'>{14}</td>" # Robot
            u"</tr>"
        ).format(
            esc(code),            # 0
            code_cell,            # 1
            esc(name.lower()),    # 2
            name_cell,            # 3
            docs_cell,            # 4
            len(e["cramram"]),    # 5
            cramram_cell,         # 6
            len(e["codda"]),      # 7
            codda_cell,           # 8
            len(e["dcsl"]),       # 9
            dcsl_cell,            #10
            len(e["chs"]),        #11
            ch_cell,              #12
            len(e["robots"]),     #13
            robot_cell            #14
        )
        rows.append(row)

    rows_html = u"\n".join(rows)

    # Keep JS/CSS simple (ES5); no template literals/arrow functions.
    html_doc = u"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Components Index</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {{
    /* Let the UA drive light/dark (form controls, scrollbars, etc.) */
    color-scheme: light dark;

    /* Palette mapped to system colors so it adapts automatically */
    --bg: Canvas;
    --card: Canvas;          /* surfaces like tables/cards */
    --text: CanvasText;
    --muted: GrayText;
    --border: ButtonBorder;

    /* Inputs / chips */
    --field: Field;
    --fieldText: FieldText;

    /* Row backgrounds (fallbacks below for older browsers) */
    --row-odd-light: rgba(0,0,0,.03);
    --row-even-light: rgba(0,0,0,.06);
    --row-odd-dark:  rgba(255,255,255,.04);
    --row-even-dark: rgba(255,255,255,.07);

    /* Hover highlight */
    --hl-light: rgba(0,0,0,.12);
    --hl-dark:  rgba(255,255,255,.12);

    /* Links */
    --link: LinkText;
  }}

  * {{ box-sizing: border-box; }}
  html, body {{ height: 100%; }}

  body {{
    background: var(--bg);
    color: var(--text);
    font: 14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Arial;
    margin: 0;
    padding: 24px;
  }}

  .wrap {{ max-width: 1220px; margin: 0 auto; }}
  h1 {{ font-size: 20px; margin: 0 0 10px; }}
  .meta {{ color: var(--muted); margin-bottom: 14px; }}

  .tools {{
    display: flex;
    gap: 12px;
    align-items: center;
    margin: 12px 0 16px;
  }}

  input[type="search"]{{
    flex: 1;
    padding: 10px 12px;
    background: var(--field);
    color: var(--fieldText);
    border: 1px solid var(--border);
    border-radius: 8px;
    outline: none;
  }}

  table {{
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 10px;
    overflow: hidden;
  }}

  thead th {{
    position: sticky; top: 0;
    background: var(--card);
    color: var(--text);
    text-align: left;
    padding: 12px;
    font-weight: 600;
    user-select: none;
    cursor: pointer;
    border-bottom: 1px solid var(--border);
  }}
  thead th .arrow {{ margin-left: 6px; opacity: .7; }}

  tbody td {{
    padding: 11px 12px;
    border-bottom: 1px solid var(--border);
    vertical-align: top;
  }}

  /* Zebra rows with light/dark fallbacks */
  tbody tr:nth-child(odd) {{ background: var(--row-odd-light); }}
  tbody tr:nth-child(even){{ background: var(--row-even-light); }}
  @media (prefers-color-scheme: dark) {{
    tbody tr:nth-child(odd) {{ background: var(--row-odd-dark); }}
    tbody tr:nth-child(even){{ background: var(--row-even-dark); }}
  }}

  tbody tr:hover {{
    background: var(--hl-light);
  }}
  @media (prefers-color-scheme: dark) {{
    tbody tr:hover {{ background: var(--hl-dark); }}
  }}

  .pill {{
    background: Highlight;
    color: HighlightText;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 12px;
    margin-left: 8px;
    border: 1px solid var(--border);
  }}

  .missing {{ color: #d26a6a; }}

  a {{ color: var(--link); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}

  /* “Chip” style links (if you use them for Docs) */
  .chip {{
    display: inline-block;
    padding: 3px 8px;
    margin: 2px 4px 2px 0;
    border-radius: 999px;
    text-decoration: none;
    background: var(--field);
    color: var(--fieldText);
    border: 1px solid var(--border);
    font-size: 12px;
  }}

  /* Collapsible lists */
  .coll summary {{ cursor: pointer; list-style: none; }}
  .coll summary::-webkit-details-marker {{ display: none; }}
  .coll summary::before {{
    content: '▸';
    display: inline-block;
    margin-right: 6px;
    color: var(--muted);
  }}
  .coll[open] summary::before {{ content: '▾'; }}

  .badge {{
    display: inline-block;
    min-width: 18px;
    padding: 0 6px;
    text-align: center;
    border-radius: 10px;
    background: var(--field);
    color: var(--fieldText);
    font-size: 12px;
    border: 1px solid var(--border);
    margin-right: 6px;
  }}

  .filelist {{ margin: 8px 0 0 18px; padding: 0; }}
  .filelist li {{ list-style: disc; margin: 2px 0 0 16px; word-break: break-all; }}

  .count {{ color: var(--muted); font-size: 12px; margin-top: 8px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>Components</h1>
  <div class="meta">Click headers to sort (A–Z / Z–A). Use the search to filter. The <strong>Component</strong> and <strong>Name</strong> link to the local folder when found. Long lists (CODDA/DCSL/C/H/Robot) are collapsed by default.</div>

  <div class="tools">
    <input id="q" type="search" placeholder="Filter by component or name… (live)">
  </div>

  <table id="tbl">
    <thead>
      <tr>
        <th data-col="0" data-type="code">Component <span class="arrow">↕</span></th>
        <th data-col="1" data-type="text">Name <span class="arrow">↕</span></th>
        <th data-col="2" data-type="text">Docs <span class="arrow">↕</span></th>
        <th data-col="3" data-type="num">CRAM/RAM <span class="arrow">↕</span></th>
        <th data-col="4" data-type="num">CODDA <span class="arrow">↕</span></th>
        <th data-col="5" data-type="num">DCSL <span class="arrow">↕</span></th>
        <th data-col="6" data-type="num">C/H <span class="arrow">↕</span></th>
        <th data-col="7" data-type="num">Robot <span class="arrow">↕</span></th>
      </tr>
    </thead>
    <tbody>
{rows_html}
    </tbody>
  </table>

  <div class="count" id="count"></div>
</div>

<script>

// Minimal ES5 (works on old browsers)
(function () {{
  var tbl = document.getElementById('tbl');
  var tbody = tbl.tBodies[0];
  var ths = tbl.tHead.rows[0].cells;
  var sortState = {{ col: 0, dir: 1 }};

  function getText(el) {{
    return (el.textContent || el.innerText || '').trim();
  }}

  function cmp(a, b, type) {{
    if (type === 'code') {{
      var na = parseInt((a.match(/\\d+/) || ['0'])[0], 10);
      var nb = parseInt((b.match(/\\d+/) || ['0'])[0], 10);
      return na - nb;
    }}
    if (type === 'num') {{
      return (parseInt(a, 10) || 0) - (parseInt(b, 10) || 0);
    }}
    // case-insensitive text compare
    a = a.toLowerCase(); b = b.toLowerCase();
    if (a < b) return -1;
    if (a > b) return 1;
    return 0;
  }}

  function sortBy(col, type) {{
    var rows = [];
    for (var i = 0; i < tbody.rows.length; i++) rows.push(tbody.rows[i]);
    var dir = (sortState.col === col) ? -sortState.dir : 1;
    sortState = {{ col: col, dir: dir }};
    rows.sort(function (r1, r2) {{
      var a = r1.cells[col].getAttribute('data-sort') || getText(r1.cells[col]);
      var b = r2.cells[col].getAttribute('data-sort') || getText(r2.cells[col]);
      return dir * cmp(a, b, type);
    }});
    for (var j = 0; j < rows.length; j++) tbody.appendChild(rows[j]);
    for (var k = 0; k < ths.length; k++) {{
      var span = ths[k].querySelector('.arrow');
      if (span) span.innerHTML = '↕';
    }}
    var s = ths[col].querySelector('.arrow');
    if (s) s.innerHTML = (dir === 1 ? '↑' : '↓');
  }}

  for (var t = 0; t < ths.length; t++) {{
    (function(th, idx){{
      th.onclick = function () {{ sortBy(idx, th.getAttribute('data-type')); }};
    }})(ths[t], t);
  }}

  var q = document.getElementById('q');
  var count = document.getElementById('count');
  function applyFilter() {{
    var term = (q.value || '').toLowerCase();
    var visible = 0;
    for (var i = 0; i < tbody.rows.length; i++) {{
      var tr = tbody.rows[i];
      var text = tr.textContent ? tr.textContent.toLowerCase() : tr.innerText.toLowerCase();
      var show = !term || text.indexOf(term) !== -1;
      tr.style.display = show ? '' : 'none';
      if (show) visible++;
    }}
    count.innerHTML = term ? (visible + ' shown (filtered)') : '';
  }}
  if (q.addEventListener) q.addEventListener('input', applyFilter, false);
  else q.attachEvent('onkeyup', applyFilter);

  // Initial sort by Component ascending
  sortBy(0, 'code');
}})();
</script>
</body>
</html>
""".format(rows_html=rows_html)

    return html_doc

# -----------------------------
# Main
# -----------------------------
def main():
    base_dir = os.getcwd()
    mapping = read_components_map(os.path.join(base_dir, MAP_FILE))

    if not mapping:
        print("WARN: '{}' not found or empty. No rows will be generated.".format(MAP_FILE))

    entries = []
    for code, name in mapping.items():
        folder = find_component_folder(base_dir, code)

        if folder:
            docs = match_docs(folder, code)
            cramram = list_cram_ram(folder, code)
            codda = list_codda(folder)
            dcsl = list_dcsl(folder)
            chs = list_ch(folder)
            robots = list_robot(folder)
        else:
            docs = dict((t, None) for t in DOC_TOKENS)
            cramram = []
            codda = []
            dcsl = []
            chs = []
            robots = []

        entries.append({
            "code": code,
            "name": name,
            "folder": folder,
            "docs": docs,
            "cramram": cramram,   # <--- add this line
            "codda": codda,
            "dcsl": dcsl,
            "chs": chs,
            "robots": robots,
        })

    html_text = build_html(entries, base_dir)
    out_path = os.path.join(base_dir, OUTPUT_HTML)
    with codecs.open(out_path, "w", "utf-8") as f:
        f.write(html_text)

    print("Wrote: {}".format(out_path))
    print("Components indexed: {}".format(len(entries)))
    print(" - folders found: {}".format(sum(1 for e in entries if e['folder'])))
    print(" - with any docs:  {}".format(sum(1 for e in entries if any(e['docs'].values()))))

if __name__ == "__main__":
    main()
