
#!/usr/bin/env python3
"""
Generate an index.html in the current directory linking to HTML documents found in:
  - cXXXXX/src/*.html
  - cXXXXX/delivery-doc/src/*.html   (fallback support)

For each cXXXXX folder:
  - Extract the <title> from the HTML document(s)
  - Compute the total folder size (recursive)
  - Output an HTML index with titles, links, and sizes

Usage:
  python3 generate_delivery_docs_index.py

Notes:
  - Folder name pattern is case-insensitive: c followed by digits (e.g., c00001, C42)
  - Supports both .html and .htm files
"""

import os
import re
import sys
import html
from pathlib import Path
from typing import List, Optional, Tuple

# --- Title extraction using stdlib HTMLParser ---
from html.parser import HTMLParser

class TitleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_title = False
        self.title_chunks: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "title":
            self.in_title = True

    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title_chunks.append(data)

    @property
    def title(self) -> str:
        return "".join(self.title_chunks).strip()


def extract_title_from_html_file(html_path: Path) -> str:
    """Extract <title> text from an HTML file. Returns filename if no title found."""
    try:
        # Read a reasonable amount (or full file) to catch title; robust to encoding issues
        text = html_path.read_text(encoding="utf-8", errors="ignore")
        parser = TitleParser()
        parser.feed(text)
        title = parser.title
        if title:
            return title
    except Exception:
        pass
    # Fallback to the filename if title not found
    return html_path.name


def human_readable_size(num_bytes: int) -> str:
    """Convert bytes to human-readable string."""
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0


def folder_size_bytes(path: Path) -> int:
    """Compute total size of folder recursively."""
    total = 0
    for root, dirs, files in os.walk(path, onerror=None):
        for f in files:
            fp = Path(root) / f
            try:
                total += fp.stat().st_size
            except (OSError, FileNotFoundError):
                # Skip files that disappear or are inaccessible
                continue
    return total


def find_html_files_for_client_folder(client_folder: Path) -> List[Path]:
    """
    Return list of HTML files for a given cXXXXX folder by checking:
      1) client_folder/src/*.html, *.htm
      2) client_folder/delivery-doc/src/*.html, *.htm  (fallback)
    """
    candidates: List[Path] = []
    primary = client_folder / "src"
    fallback = client_folder / "delivery-doc" / "src"

    patterns = ["*.html", "*.htm"]

    if primary.is_dir():
        for pat in patterns:
            candidates.extend(primary.glob(pat))
    if not candidates and fallback.is_dir():
        for pat in patterns:
            candidates.extend(fallback.glob(pat))

    # Sort deterministically (alphabetical by filename)
    candidates = sorted(set(p for p in candidates if p.is_file()))
    return candidates


def is_client_folder_name(name: str) -> bool:
    """Return True if name matches c followed by digits (e.g., c00001, C42)."""
    return re.fullmatch(r"[cC]\d+", name) is not None


def numeric_key_from_client_name(name: str) -> Tuple[int, str]:
    """
    For sorting: extract the numeric part for natural order, fallback to name.
    Example: 'c00012' -> (12, 'c00012')
    """
    m = re.fullmatch(r"[cC](\d+)", name)
    if m:
        try:
            return (int(m.group(1)), name)
        except ValueError:
            pass
    return (float("inf"), name)



def generate_index_html(entries: List[dict], output_path: Path) -> None:
    """
    entries: list of dicts with keys:
      - client: str               (folder name, e.g., c00001)
      - folder_size_bytes: int
      - docs: List[dict] with:
          - title: str
          - rel_href: str
          - rel_path_display: str
    """
    rows = []
    for entry in entries:
        client = html.escape(entry["client"])
        size_str = human_readable_size(entry["folder_size_bytes"])
        size_esc = html.escape(size_str)

        if not entry["docs"]:
            # Show row indicating no document found
            rows.append(f"""
            <tr>
                <td><code>{client}</code></td>
                <td>{size_esc}</td>
                <td colspan="2" class="muted">No HTML document found in <code>src/</code> or <code>delivery-doc/src/</code></td>
            </tr>
            """)
            continue

        # If multiple docs exist, show one row per document, repeating size
        for doc in entry["docs"]:
            title = html.escape(doc["title"])
            rel_href = html.escape(doc["rel_href"])
            rel_disp = html.escape(doc["rel_path_display"])

            rows.append(f"""
            <tr>
                <td><code>{client}</code></td>
                <td>{size_esc}</td>
                <td><a href="{rel_href}" target="_blank" rel="noopener">{title}</a></td>
                <td><code>{rel_disp}</code></td>
            </tr>
            """)

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Delivery Documents Index</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
    :root {{
        --fg: #1f2937;
        --muted: #6b7280;
        --bg: #ffffff;
        --table-border: #e5e7eb;
        --link: #2563eb;
    }}
    html, body {{
        margin: 0; padding: 0; background: var(--bg); color: var(--fg);
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, "Helvetica Neue", Arial, "Noto Sans", "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol";
        line-height: 1.5;
    }}
    .container {{
        max-width: 1200px; margin: 2rem auto; padding: 0 1rem;
    }}
    h1 {{
        font-size: 1.6rem; margin: 0 0 1rem 0;
    }}
    p.subtitle {{
        margin: 0 0 1.25rem 0; color: var(--muted);
    }}
    table {{
        width: 100%; border-collapse: collapse; border: 1px solid var(--table-border);
    }}
    th, td {{
        border-bottom: 1px solid var(--table-border);
        padding: 0.6rem 0.7rem; text-align: left; vertical-align: top;
    }}
    th {{
        background: #f9fafb; font-weight: 600;
    }}
    tr:hover td {{
        background: #fcfcfd;
    }}
    a {{
        color: var(--link); text-decoration: none;
    }}
    a:hover {{ text-decoration: underline; }}
    code {{
        background: #f3f4f6; padding: 0.1rem 0.3rem; border-radius: 4px;
    }}
    .muted {{ color: var(--muted); }}
    .footer {{
        margin-top: 1rem; color: var(--muted); font-size: 0.9rem;
    }}
</style>
</head>
<body>
<div class="container">
  <h1>Delivery Documents Index</h1>
  <p class="subtitle">Generated from folders matching <code>c\\d+</code>. Looks for HTML in <code>src/</code> (or <code>delivery-doc/src/</code> fallback). Folder size shown is the total size of each <code>cXXXXX</code> directory.</p>

  <table>
    <thead>
      <tr>
        <th>Folder</th>
        <th>Folder Size</th>
        <th>Document Title</th>
        <th>Relative Path</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>

  <div class="footer">Generated by generate_delivery_docs_index.py</div>
</div>
</body>
</html>
"""
    output_path.write_text(html_doc, encoding="utf-8")


def main():
    root = Path.cwd()
    # Discover client folders (c followed by digits)
    client_folders = [p for p in root.iterdir() if p.is_dir() and is_client_folder_name(p.name)]
    # Sort by numeric suffix, then name
    client_folders.sort(key=lambda p: numeric_key_from_client_name(p.name))

    entries = []
    for cf in client_folders:
        docs: List[dict] = []
        html_files = find_html_files_for_client_folder(cf)

        for f in html_files:
            title = extract_title_from_html_file(f)
            rel_href = os.path.relpath(f, root).replace(os.sep, "/")
            docs.append({
                "title": title,
                "rel_href": rel_href,
                "rel_path_display": rel_href
            })

        size_b = folder_size_bytes(cf)
        entries.append({
            "client": cf.name,
            "folder_size_bytes": size_b,
            "docs": docs
        })

    output_file = root / "index.html"
    generate_index_html(entries, output_file)

    print(f"✅ Generated: {output_file}")
    print(f"   Folders scanned: {len(client_folders)}")
    doc_count = sum(len(e['docs']) for e in entries)
    print(f"   Documents found: {doc_count}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)

  
