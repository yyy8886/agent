#!/usr/bin/env python3
"""Colorize a .drawio diagram's nodes by their type (label prefix).

Useful for large diagrams (clock trees, circuit schematics, architecture
diagrams) where nodes of the same kind should share a color so the structure
is readable at a glance. Matches each vertex's label against a set of type
patterns and applies a fill/stroke color. Handles both plain-XML and
compressed (deflate) .drawio files.

  python3 colorize.py diagram.drawio -o colored.drawio
  python3 colorize.py diagram.drawio --preset circuit   # built-in palette
  python3 colorize.py diagram.drawio --map types.json   # custom mapping

Usage: python3 colorize.py <file.drawio> [-o <out.drawio>] [--preset NAME]
       [--map <types.json>] [--no-backup]
"""
import argparse
import base64
import json
import os
import re
import shutil
import sys
import urllib.parse
import zlib
import xml.etree.ElementTree as ET

# ---------------------------------------------------------------------------
# Built-in type -> color palettes
# ---------------------------------------------------------------------------
# Each entry: type pattern (regex, matched against node label) -> (fill, stroke)
PALETTES = {
    "circuit": {
        # Clock tree / circuit design node types
        r"^MUX":        ("#dae8fc", "#6c8ebf"),   # blue
        r"^ICG":        ("#d5e8d4", "#82b366"),   # green
        r"^GATE":       ("#ffe6cc", "#d79b00"),   # orange
        r"^BUF":        ("#fff2cc", "#d6b656"),   # yellow
        r"^div":        ("#e1d5e7", "#9673a6"),   # purple
        r"^SW":         ("#d6e8f8", "#5a8cc0"),   # light blue
        r"^PLL":        ("#f8cecc", "#b85450"),   # red
        r"^XTAL":       ("#fce4ec", "#c2185b"),   # pink
        r"^RFSPHDS":    ("#f5f5f5", "#666666"),   # grey
        r"^MAX":        ("#d6e8f8", "#5a8cc0"),   # light blue
        r"^NO_LOAD":    ("#f5f5f5", "#999999"),   # light grey
        r"^pull":       ("#e8f5e9", "#66bb6a"),   # light green
        r"^clk":        ("#f0f0f0", "#999999"),   # light grey
    },
    "architecture": {
        # Generic architecture / system design node types
        r"^api|^API":   ("#dae8fc", "#6c8ebf"),   # blue
        r"^db|^DB":     ("#ffe6cc", "#d79b00"),   # orange
        r"^cache":      ("#fff2cc", "#d6b656"),   # yellow
        r"^queue":      ("#e1d5e7", "#9673a6"),   # purple
        r"^auth":       ("#f8cecc", "#b85450"),   # red
        r"^worker":     ("#d5e8d4", "#82b366"),   # green
        r"^frontend":   ("#d6e8f8", "#5a8cc0"),   # light blue
        r"^backend":    ("#fce4ec", "#c2185b"),   # pink
        r"^gateway":    ("#f5f5f5", "#666666"),   # grey
    },
    "network": {
        r"^router":     ("#dae8fc", "#6c8ebf"),   # blue
        r"^switch":     ("#d5e8d4", "#82b366"),   # green
        r"^firewall":   ("#f8cecc", "#b85450"),   # red
        r"^server":     ("#fff2cc", "#d6b656"),   # yellow
        r"^client":     ("#e1d5e7", "#9673a6"),   # purple
        r"^load.?bal":  ("#d6e8f8", "#5a8cc0"),   # light blue
    },
}


def get_key(style: str, key: str) -> str | None:
    """Extract a key=value from a draw.io style string."""
    m = re.search(rf"(?:^|;){key}=([^;]*)", style)
    return m.group(1) if m else None


def set_key(style: str, key: str, value: str) -> str:
    """Set a key=value in a style string, replacing any existing occurrence."""
    # Remove existing key.
    style = re.sub(rf"(?:^|;){key}=[^;]*", "", style)
    # Append new key.
    return f"{style};{key}={value}" if style else f"{key}={value}"


def match_type(label: str, patterns: dict) -> tuple[str, str] | None:
    """Return (fill, stroke) for the first pattern matching the label."""
    for pat, colors in patterns.items():
        if re.search(pat, label, re.IGNORECASE):
            return colors
    return None


def colorize_vertex(vertex: ET.Element, patterns: dict) -> bool:
    """Apply fill/stroke to a vertex if its label matches a type. Returns True if changed."""
    label = vertex.get("value") or ""
    if not label:
        return False
    colors = match_type(label, patterns)
    if not colors:
        return False
    fill, stroke = colors
    style = vertex.get("style") or ""
    style = set_key(style, "fillColor", fill)
    style = set_key(style, "strokeColor", stroke)
    vertex.set("style", style)
    return True


def decompress_page(text: str) -> str:
    """Decompress a draw.io page's payload to XML text.

    draw.io uses two formats for compressed pages:
    1. URL-encoded deflate:  %3CmxGraphModel...%3C%2FmxGraphModel%3E
    2. base64 deflate:       <base64 of raw-deflate(URL-encoded XML)>
    Both are handled here.
    """
    if "%3C" in text:
        return urllib.parse.unquote(text)
    try:
        raw = base64.b64decode(text)
        inflated = zlib.decompress(raw, -zlib.MAX_WBITS).decode("utf-8")
        return urllib.parse.unquote(inflated)
    except Exception:
        return text


def compress_page(xml_text: str) -> str:
    """Compress a page's XML to draw.io's base64+deflate format.

    draw.io stores compressed pages as base64 of raw-deflate(URL-encoded XML).
    """
    # URL-encode the XML first (draw.io convention), then deflate, then base64.
    encoded = urllib.parse.quote(xml_text, safe="")
    compressor = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS)
    compressed = compressor.compress(encoded.encode("utf-8")) + compressor.flush()
    return base64.b64encode(compressed).decode("utf-8")


def process(path: str, out_path: str, patterns: dict, backup: bool) -> int:
    """Colorize all vertices in a .drawio file. Returns number of nodes colored."""
    tree = ET.parse(path)
    root = tree.getroot()
    pages = root.findall("diagram")
    if not pages:
        sys.exit(f"error: {path}: no <diagram> pages found")

    colored = 0
    for page in pages:
        model = page.find("mxGraphModel")
        if model is None:
            # Compressed page — decompress, colorize, recompress.
            xml_text = decompress_page(page.text or "")
            sub = ET.fromstring(xml_text)
            for vertex in sub.iter("mxCell"):
                if vertex.get("vertex") == "1":
                    if colorize_vertex(vertex, patterns):
                        colored += 1
            page.text = compress_page(ET.tostring(sub, encoding="unicode"))
        else:
            for vertex in model.iter("mxCell"):
                if vertex.get("vertex") == "1":
                    if colorize_vertex(vertex, patterns):
                        colored += 1

    if colored == 0:
        print(f"info: {path}: no nodes matched the type patterns")
    else:
        if backup and os.path.abspath(path) == os.path.abspath(out_path):
            backup_path = path + ".bak"
            shutil.copy2(path, backup_path)
            print(f"info: backup saved to {backup_path}")
        tree.write(out_path, encoding="utf-8", xml_declaration=True)
        print(f"ok: colored {colored} node(s) -> {out_path}")

    return colored


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("file", help="input .drawio (plain or compressed)")
    ap.add_argument("-o", "--out", help="output path (default: in-place)")
    ap.add_argument("--preset", choices=list(PALETTES), default="circuit",
                    help="built-in type palette (default: circuit)")
    ap.add_argument("--map", help="custom JSON mapping {pattern: [fill, stroke]}")
    ap.add_argument("--no-backup", action="store_true",
                    help="skip backup when writing in-place")
    args = ap.parse_args()

    if not os.path.isfile(args.file):
        sys.exit(f"error: {args.file}: no such file")

    if args.map:
        with open(args.map, encoding="utf-8") as f:
            patterns = json.load(f)
    else:
        patterns = PALETTES[args.preset]

    out = args.out or args.file
    # Ensure the output always has a .drawio suffix so draw.io can open it.
    if not out.lower().endswith(".drawio"):
        out += ".drawio"
    process(args.file, out, patterns, backup=not args.no_backup)


if __name__ == "__main__":
    main()
