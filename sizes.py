#!/usr/bin/env python3
"""
List all files inside a folder (and its subfolders), sorted by size (desc),
and write the results to out.txt.

Usage:
    python list_files_by_size.py /path/to/folder
    # Optional:
    python list_files_by_size.py /path/to/folder --output out.txt --human

Notes:
- Default output file is ./out.txt (in the current working directory).
- File sizes are in bytes by default; use --human for human-readable sizes.
"""

import argparse
import os
from pathlib import Path
from typing import List, Tuple, Optional

def human_size(num_bytes: int) -> str:
    """Convert a byte value into a human-readable string."""
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            # Format with up to 2 decimals, strip trailing zeros
            return f"{size:.2f} {unit}".replace(".00", "")
        size /= 1024.0
    return f"{num_bytes} B"  # Fallback (shouldn't reach here)

def collect_files_with_sizes(root: Path) -> List[Tuple[int, Path]]:
    """
    Recursively collect (size, absolute_path) for all regular files under root.
    Skips unreadable files and broken symlinks, logging nothing (silent).
    """
    results: List[Tuple[int, Path]] = []

    # Use os.walk for speed and control; followlinks=False to avoid loops
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # Convert to Path for consistency
        dir_path = Path(dirpath)

        for fname in filenames:
            fpath = dir_path / fname

            try:
                # Use lstat to avoid following symlinks; if it's a symlink to file,
                # try stat to get the target size safely (if accessible).
                if fpath.is_symlink():
                    # Try to stat the target; if broken or inaccessible, skip
                    try:
                        size = fpath.stat().st_size
                    except (OSError, FileNotFoundError, PermissionError):
                        continue
                else:
                    # Regular file or special file
                    if not fpath.is_file():
                        continue
                    size = fpath.stat().st_size
            except (OSError, FileNotFoundError, PermissionError):
                # Skip files we can't stat
                continue

            results.append((size, fpath.resolve()))

    return results

def write_results(
    items: List[Tuple[int, Path]],
    root: Path,
    out_file: Path,
    human: bool = False
) -> None:
    """
    Write the sorted list to out_file.
    Format: "<size>\t<relative_path>" or "<human_size>\t<relative_path>"
    """
    # Ensure parent directory for output exists
    out_file.parent.mkdir(parents=True, exist_ok=True)

    with out_file.open("w", encoding="utf-8", newline="\n") as f:
        header = f"# Files under: {root.resolve()}\n# Sorted by size (largest first)\n# Size\tPath\n"
        f.write(header)
        for size, abspath in items:
            rel = abspath.relative_to(root) if abspath.is_relative_to(root) else abspath
            size_str = human_size(size) if human else str(size)
            f.write(f"{size_str}\t{rel.as_posix()}\n")

def main():
    parser = argparse.ArgumentParser(
        description="List files under a folder (recursively) sorted by size (desc) into out.txt"
    )
    parser.add_argument(
        "folder",
        help="Path to the folder to scan (use '.' for current directory)"
    )
    parser.add_argument(
        "-o", "--output",
        default="out.txt",
        help="Output file path (default: out.txt in current working directory)"
    )
    parser.add_argument(
        "--human",
        action="store_true",
        help="Show sizes in human-readable units (e.g., MB, GB)"
    )
    args = parser.parse_args()

    root = Path(args.folder).expanduser().resolve()
    out_file = Path(args.output).expanduser()

    if not root.exists():
        print(f"Error: Folder does not exist: {root}")
        raise SystemExit(1)
    if not root.is_dir():
        print(f"Error: Path is not a directory: {root}")
        raise SystemExit(1)

    files = collect_files_with_sizes(root)

    # Sort by size descending, then by path name for stability
    files.sort(key=lambda t: (-t[0], str(t[1])))

    write_results(files, root=root, out_file=out_file, human=args.human)

    print(f"Done. Wrote {len(files)} files to {out_file.resolve()}")

if __name__ == "__main__":
    main()
