#!/usr/bin/env python3
"""Analyze a .drawio file's structure: pages, node types, and color coverage.

Useful before colorizing or re-theming a diagram — understand what node types
exist and how many are already colored, so you can pick the right palette or
spot nodes that will be missed.

  python3 analyze.py diagram.drawio
  python3 analyze.py diagram.drawio --json   # machine-readable output

Usage: python3 analyze.py <file.drawio> [--json]
"""
import argparse
import base64
import json
import os
import re
import sys
import urllib.parse
import zlib
import xml.etree.ElementTree as ET


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


def get_key(style: str, key: str) -> str | None:
    m = re.search(rf"(?:^|;){key}=([^;]*)", style)
    return m.group(1) if m else None


def analyze(path: str) -> dict:
    """Return a structured summary of the diagram."""
    tree = ET.parse(path)
    root = tree.getroot()
    pages = root.findall("diagram")

    result = {
        "file": os.path.basename(path),
        "pages": [],
        "total_vertices": 0,
        "total_edges": 0,
        "colored_vertices": 0,
        "uncolored_vertices": 0,
        "node_types": {},   # label-prefix -> count
    }

    for page in pages:
        page_info = {
            "name": page.get("name", "?"),
            "compressed": page.find("mxGraphModel") is None,
            "vertices": 0,
            "edges": 0,
            "colored": 0,
        }

        model = page.find("mxGraphModel")
        if model is None:
            # Compressed page.
            xml_text = decompress_page(page.text or "")
            try:
                sub = ET.fromstring(xml_text)
            except ET.ParseError:
                page_info["error"] = "cannot parse compressed page"
                result["pages"].append(page_info)
                continue
            cells = list(sub.iter("mxCell"))
        else:
            cells = list(model.iter("mxCell"))

        for cell in cells:
            is_vertex = cell.get("vertex") == "1"
            is_edge = cell.get("edge") == "1"
            if is_vertex:
                page_info["vertices"] += 1
                result["total_vertices"] += 1
                style = cell.get("style") or ""
                fill = get_key(style, "fillColor")
                if fill and fill != "none":
                    page_info["colored"] += 1
                    result["colored_vertices"] += 1
                else:
                    result["uncolored_vertices"] += 1
                # Node type by label prefix.
                label = cell.get("value") or ""
                if label:
                    prefix = re.match(r"^[A-Za-z_]+", label)
                    if prefix:
                        key = prefix.group(0).upper()
                        result["node_types"][key] = result["node_types"].get(key, 0) + 1
            elif is_edge:
                page_info["edges"] += 1
                result["total_edges"] += 1

        result["pages"].append(page_info)

    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("file", help="input .drawio (plain or compressed)")
    ap.add_argument("--json", action="store_true", help="machine-readable JSON output")
    args = ap.parse_args()

    if not os.path.isfile(args.file):
        sys.exit(f"error: {args.file}: no such file")

    result = analyze(args.file)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    print(f"File: {result['file']}")
    print(f"Pages: {len(result['pages'])}")
    print(f"Vertices: {result['total_vertices']} (colored: {result['colored_vertices']}, "
          f"uncolored: {result['uncolored_vertices']})")
    print(f"Edges: {result['total_edges']}")
    print()
    print("Node types (by label prefix):")
    for prefix, count in sorted(result["node_types"].items(), key=lambda x: -x[1]):
        print(f"  {prefix:<20} {count}")
    print()
    print("Per-page:")
    for p in result["pages"]:
        status = "compressed" if p["compressed"] else "plain"
        err = f" ({p.get('error', '')})" if "error" in p else ""
        print(f"  {p['name']:<30} {status:<12} vertices={p['vertices']:<5} "
              f"edges={p['edges']:<5} colored={p['colored']}{err}")


if __name__ == "__main__":
    main()
