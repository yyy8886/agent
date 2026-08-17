#!/usr/bin/env python3
"""Compress a .drawio file's pages into deflate+URL-encoded XML.

The inverse of decompress.py. draw.io uses this format for large diagrams to
keep file size small. Compressing is optional — draw.io can open plain XML
too — but it shrinks the file dramatically for big diagrams.

  python3 compress.py diagram_plain.drawio -o diagram.drawio
  python3 compress.py diagram_plain.drawio            # in-place (backup first)

Usage: python3 compress.py <file.drawio> [-o <out.drawio>] [--no-backup]
"""
import argparse
import base64
import os
import shutil
import sys
import urllib.parse
import zlib
import xml.etree.ElementTree as ET


def compress_page(xml_text: str) -> str:
    """Compress a page's XML to draw.io's base64+deflate format.

    draw.io stores compressed pages as base64 of raw-deflate(URL-encoded XML).
    """
    # URL-encode the XML first (draw.io convention), then deflate, then base64.
    encoded = urllib.parse.quote(xml_text, safe="")
    compressor = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS)
    compressed = compressor.compress(encoded.encode("utf-8")) + compressor.flush()
    return base64.b64encode(compressed).decode("utf-8")


def process(path: str, out_path: str, backup: bool) -> int:
    """Compress all plain-XML pages in a .drawio file. Returns pages compressed."""
    tree = ET.parse(path)
    root = tree.getroot()
    pages = root.findall("diagram")
    if not pages:
        sys.exit(f"error: {path}: no <diagram> pages found")

    compressed = 0
    for page in pages:
        model = page.find("mxGraphModel")
        if model is not None:
            # Serialize the mxGraphModel element to text, then compress.
            xml_text = ET.tostring(model, encoding="unicode")
            page.remove(model)
            page.text = compress_page(xml_text)
            compressed += 1

    if compressed == 0:
        print(f"info: {path}: no plain-XML pages to compress")
    else:
        if backup and os.path.abspath(path) == os.path.abspath(out_path):
            backup_path = path + ".bak"
            shutil.copy2(path, backup_path)
            print(f"info: backup saved to {backup_path}")
        tree.write(out_path, encoding="utf-8", xml_declaration=True)
        print(f"ok: compressed {compressed} page(s) -> {out_path}")

    return compressed


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("file", help="input .drawio (plain XML)")
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
