#!/usr/bin/env python2
# -*- coding: utf-8 -*-

"""
Collect component code files into concatenated .txt files per phase.

Usage:
    python collect.py /path/to/C000xx [/path/to/C000yy ...]

Outputs (in current working directory):
    - <COMPONENT>_0_PLAN.txt
    - <COMPONENT>_1_SPEC_ARCHI.txt
    - <COMPONENT>_2_DESIGN.txt
    - <COMPONENT>_3_CODE.txt
    - <COMPONENT>_4_UNIT_VERIF.txt
    - <COMPONENT>_5_INTEG_VERIF.txt
    - <COMPONENT>_6_ENVIRONMENT.txt
    - <COMPONENT>_7_USER_GUIDE.txt

Entry format per file:
    <filename>:
    <empty line>
    <file contents>
    <empty line>
    <empty line>
"""

from __future__ import unicode_literals

import os
import sys
import codecs

# Header label behavior: True -> only filename; False -> relative path
HEADER_ONLY_NAME = True

# Extensions/files to completely ignore during the scan
EXCLUDED_EXTS = ('.xlsx', '.xlsm', '.jar', '.html', '.pdf', '.rqtfimage', '.png', '.bin', '.lup', '.pptx', '.luh')

# Directories to completely skip (case-insensitive)
EXCLUDED_DIRS = set(['external', 'build', 'tmp'])

# -----------------------------
# Helpers
# -----------------------------
def norm(p):
    """Normalize path with forward slashes for matching / output."""
    return os.path.normpath(p).replace('\\', '/')

def relpath(base_dir, full_path):
    try:
        r = os.path.relpath(full_path, base_dir)
    except Exception:
        r = full_path
    return norm(r)

def read_text_utf8(path):
    """Read file as UTF-8, replacing undecodable bytes."""
    with codecs.open(path, 'r', 'utf-8', 'replace') as f:
        return f.read()

def format_header(rel_path, header_only_name):
    """
    Return the header line "<name>:\n\n".
    If header_only_name=True, show only the file basename.
    """
    label = os.path.basename(rel_path) if header_only_name else rel_path
    return u"%s:\n\n" % label

def write_bundle(out_name, entries, base_dir, header_only_name):
    """
    Write a bundle file in CWD:
      entries -> list of absolute file paths
      base_dir -> component root to compute relative headers
    """
    if not entries:
        with codecs.open(out_name, 'w', 'utf-8') as out:
            out.write(u"")
        print("  Wrote empty %s (no files found)" % out_name)
        return

    with codecs.open(out_name, 'w', 'utf-8') as out:
        for ap in entries:
            rel = relpath(base_dir, ap)
            out.write(format_header(rel, header_only_name))
            out.write(read_text_utf8(ap))
            out.write(u"\n\n")
    print("  Wrote %s (%d files)" % (out_name, len(entries)))

def walk_files(root):
    for r, dirs, files in os.walk(root):
        # Modify dirs in-place to prevent os.walk from entering excluded folders
        dirs[:] = [d for d in dirs if d.lower() not in EXCLUDED_DIRS]
        
        for fn in files:
            yield os.path.join(r, fn)

# -----------------------------
# Categorization Logic
# -----------------------------
def categorize_file(rel_path):
    """
    Maps a relative file path to its corresponding phase based on the table.
    Returns the phase name, or None if it doesn't belong to any phase.
    """
    n = norm(rel_path).lower()
    base = os.path.basename(n)

    # 0. PLAN
    if n.startswith('src/plan/'):
        return '0_PLAN'

    # 1. SPEC/ARCHI
    if n.startswith('src/spec/'):
        return '1_SPEC_ARCHI'

    # 2. DESIGN
    if n.startswith('src/design/') or base in ('.dcsl_derog', '.codda_derog'):
        return '2_DESIGN'

    # 3. CODE
    if n.startswith('src/main/c/') or n.startswith('src/main/header/') or n.startswith('src/main/asm/') or base in ('.checkc_derog', '.fanc_derog'):
        return '3_CODE'

    # 4. UNIT VERIF
    if n.startswith('src/verif/unit-test/'):
        return '4_UNIT_VERIF'

    # 5. INTEG VERIF
    # (Evaluated before Environment so specific toolchains map here instead of Environment)
    if n.startswith('src/verif/integration/') or n.startswith('src/toolchain/toolchain-titv/') or n.startswith('src/toolchain/toolchain-tienvbuild/'):
        return '5_INTEG_VERIF'

    # 7. USER GUIDE
    if n.startswith('src/delivery-doc/'):
        return '7_USER_GUIDE'

    # 6. ENVIRONMENT
    # Uncomment the line below to restore full environment folder tracking:
    # if 'rte/' in n or 'stack/' in n or 'wcet/' in n or 'toolchain/' in n or 'gradle/' in n:
    if base in ('data.gradle', 'jenkinsfile'):
        return '6_ENVIRONMENT'

    return None

# -----------------------------
# Main Processing
# -----------------------------
def process_component(comp_dir):
    if not os.path.isdir(comp_dir):
        sys.stderr.write("ERROR: Not a directory: %s\n" % comp_dir)
        return

    comp_dir = os.path.abspath(comp_dir)
    comp_name = os.path.basename(comp_dir)

    print("\n=== Processing Component: %s ===" % comp_name)

    phases = {
        '0_PLAN': [],
        '1_SPEC_ARCHI': [],
        '2_DESIGN': [],
        '3_CODE': [],
        '4_UNIT_VERIF': [],
        '5_INTEG_VERIF': [],
        '6_ENVIRONMENT': [],
        '7_USER_GUIDE': []
    }

    # Single pass walk through the directory
    for p in walk_files(comp_dir):
        # Skip excluded extensions immediately
        if p.lower().endswith(EXCLUDED_EXTS) or os.path.basename(p).lower() == 'rqtfimage':
            continue

        rel = relpath(comp_dir, p)
        category = categorize_file(rel)
        if category in phases:
            phases[category].append(p)

    # Sort files logically within each phase
    for cat in phases:
        phases[cat].sort(key=lambda x: (os.path.basename(x).lower(), relpath(comp_dir, x).lower()))

    # Write out the results
    for cat, entries in sorted(phases.items()):
        out_name = "%s_%s.txt" % (comp_name, cat)
        write_bundle(out_name, entries, comp_dir, HEADER_ONLY_NAME)

    # Print summary
    print("\nSummary for %s:" % comp_name)
    for cat, entries in sorted(phases.items()):
        print("  %s: %d files" % (cat, len(entries)))

def main():
    if len(sys.argv) < 2:
        sys.stderr.write("Usage: python2 %s /path/to/C000xx [/path/to/C000yy ...]\n" % os.path.basename(sys.argv[0]))
        sys.exit(1)

    # Process every argument passed to the script
    for comp_dir in sys.argv[1:]:
        process_component(comp_dir)

if __name__ == "__main__":
    main()
