#!/usr/bin/env python3
"""Decompress a .drawio file that uses deflate-compressed XML pages.

draw.io saves large diagrams with each <diagram> page's XML compressed via
deflate (zlib) and then URL-encoded. Most tools (including drawio-skill's
scripts) cannot read these compressed pages — they skip them with a warning.
This script decompresses every page so the file becomes plain XML that any
tool can parse.

  python3 decompress.py diagram.drawio -o diagram_plain.drawio
  python3 decompress.py diagram.drawio            # in-place (backup first)

Usage: python3 decompress.py <file.drawio> [-o <out.drawio>] [--no-backup]
"""
import argparse
import base64
import os
import shutil
import sys
import urllib.parse
import zlib
import xml.etree.ElementTree as ET


def decompress_page(text: str) -> str:
    """Decompress a draw.io page's payload to URL-encoded XML text.

    draw.io uses two formats for compressed pages:
    1. URL-encoded deflate:  %3CmxGraphModel...%3C%2FmxGraphModel%3E
    2. base64 deflate:       <base64 of raw-deflate(URL-encoded XML)>
    Both are handled here. Returns the URL-encoded XML.
    """
    # Case 1: already URL-encoded (starts with %3C or contains %3C).
    if "%3C" in text:
        return text
    # Case 2: base64-encoded deflate. Decode base64, inflate (keep URL-encoded).
    try:
        raw = base64.b64decode(text)
        return zlib.decompress(raw, -zlib.MAX_WBITS).decode("utf-8")
    except Exception:
        # Fallback: maybe it's plain text already.
        return text


def is_compressed(page: ET.Element) -> bool:
    """Check if a <diagram> page is compressed (has text but no <mxGraphModel>)."""
    if page.find("mxGraphModel") is not None:
        return False
    return bool((page.text or "").strip())


def process(path: str, out_path: str, backup: bool) -> int:
    """Decompress all pages in a .drawio file. Returns number of pages decompressed."""
    tree = ET.parse(path)
    root = tree.getroot()
    pages = root.findall("diagram")
    if not pages:
        sys.exit(f"error: {path}: no <diagram> pages found")

    decompressed = 0
    for page in pages:
        if is_compressed(page):
            # Decompress to URL-encoded XML, then parse into a real element.
            xml_text = decompress_page(page.text or "")
            decoded = urllib.parse.unquote(xml_text)
            model = ET.fromstring(decoded)
            # Replace the page's text with the parsed mxGraphModel child.
            page.text = None
            page.append(model)
            decompressed += 1

    if decompressed == 0:
        print(f"info: {path}: no compressed pages (already plain XML)")
    else:
        if backup and os.path.abspath(path) == os.path.abspath(out_path):
            backup_path = path + ".bak"
            shutil.copy2(path, backup_path)
            print(f"info: backup saved to {backup_path}")
        tree.write(out_path, encoding="utf-8", xml_declaration=True)
        print(f"ok: decompressed {decompressed} page(s) -> {out_path}")

    return decompressed


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("file", help="input .drawio (possibly compressed)")
    ap.add_argument("-o", "--out", help="output path (default: in-place)")
    ap.add_argument("--no-backup", action="store_true",
                    help="skip backup when writing in-place")
    args = ap.parse_args()

    if not os.path.isfile(args.file):
        sys.exit(f"error: {args.file}: no such file")
    out = args.out or args.file
    # Ensure the output always has a .drawio suffix so draw.io can open it.
    if not out.lower().endswith(".drawio"):
        out += ".drawio"
    process(args.file, out, backup=not args.no_backup)


if __name__ == "__main__":
    main()
