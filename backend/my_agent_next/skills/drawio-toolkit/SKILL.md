---
name: drawio-toolkit
description: Process drawio files that are compressed (deflate/base64) or need node-type-based coloring. Decompress compressed .drawio pages to plain XML, compress plain XML back to draw.io's compact format, analyze diagram structure (pages, node types, color coverage), and colorize nodes by their label type (MUX/ICG/GATE/BUF etc). Use when a .drawio file cannot be read by other tools because pages are compressed, or when you need to visually distinguish node types in a large diagram.
---

# Draw.io Toolkit

## Overview

Process `.drawio` files that other tools can't handle. draw.io saves large diagrams with each page's XML **compressed** (base64 of raw-deflate of URL-encoded XML) — most tools (including drawio-skill's scripts) skip these pages. This skill decompresses them, lets you analyze and colorize the diagram, and re-compresses if needed.

## When to use

- A `.drawio` file's pages are **compressed** and other tools skip them ("compressed page — skipped").
- You want to **colorize nodes by type** (MUX/ICG/GATE/BUF/div/SW/PLL/XTAL…) so a large diagram is readable at a glance.
- You want to **analyze** a diagram's structure: pages, node types, color coverage.
- You want to **compress** a plain-XML `.drawio` to shrink file size.

## Quick Start

```bash
# Analyze a diagram (works on compressed files)
python3 scripts/analyze.py diagram.drawio

# Colorize nodes by type (handles compressed files, writes compressed output)
python3 scripts/colorize.py diagram.drawio -o colored.drawio --preset circuit

# Decompress all pages to plain XML (so other tools can read it)
python3 scripts/decompress.py diagram.drawio -o plain.drawio

# Compress plain XML back to draw.io's compact format
python3 scripts/compress.py plain.drawio -o diagram.drawio
```

## Scripts

### `analyze.py` — inspect a diagram

Reports pages, vertex/edge counts, color coverage, and node types (by label prefix). Works on both plain and compressed files.

```bash
python3 scripts/analyze.py diagram.drawio          # human-readable
python3 scripts/analyze.py diagram.drawio --json   # machine-readable
```

### `colorize.py` — colorize nodes by type

Matches each vertex's label against a type pattern and applies a fill/stroke color. Handles compressed files (decompresses internally, colorizes, re-compresses).

```bash
# Built-in palettes
python3 scripts/colorize.py diagram.drawio --preset circuit      # clock tree / circuit
python3 scripts/colorize.py diagram.drawio --preset architecture # system design
python3 scripts/colorize.py diagram.drawio --preset network      # network topology

# Custom mapping (JSON: {pattern: [fill, stroke]})
python3 scripts/colorize.py diagram.drawio --map types.json

# In-place (backs up first)
python3 scripts/colorize.py diagram.drawio
```

**Built-in palettes:**

| Preset | Types matched | Fill / Stroke |
| --- | --- | --- |
| `circuit` | `MUX`, `ICG`, `GATE`, `BUF`, `div`, `SW`, `PLL`, `XTAL`, `RFSPHDS`, `MAX`, `NO_LOAD`, `pull`, `clk` | blue / green / orange / yellow / purple / light-blue / red / pink / grey |
| `architecture` | `api`, `db`, `cache`, `queue`, `auth`, `worker`, `frontend`, `backend`, `gateway` | blue / orange / yellow / purple / red / green / light-blue / pink / grey |
| `network` | `router`, `switch`, `firewall`, `server`, `client`, `load-bal` | blue / green / red / yellow / purple / light-blue |

**Custom mapping example (`types.json`):**
```json
{
  "^MUX": ["#dae8fc", "#6c8ebf"],
  "^ICG": ["#d5e8d4", "#82b366"],
  "^GATE": ["#ffe6cc", "#d79b00"]
}
```

### `decompress.py` — decompress pages to plain XML

Converts compressed pages to plain XML (nested `<mxGraphModel>`), so any tool can read them.

```bash
python3 scripts/decompress.py diagram.drawio -o plain.drawio   # to a new file
python3 scripts/decompress.py diagram.drawio                   # in-place (backs up)
```

### `compress.py` — compress pages to draw.io's compact format

The inverse of `decompress.py`. Shrinks large diagrams significantly.

```bash
python3 scripts/compress.py plain.drawio -o diagram.drawio     # to a new file
python3 scripts/compress.py plain.drawio                       # in-place (backs up)
```

## draw.io compression format

draw.io stores compressed pages as:

```
<diagram>base64( raw-deflate( URL-encoded-XML ) )</diagram>
```

To decompress: `base64-decode` → `zlib.decompress(raw, -MAX_WBITS)` → `urllib.parse.unquote`.

To compress: `urllib.parse.quote(xml)` → `zlib.compressobj(9, DEFLATED, -MAX_WBITS)` → `base64-encode`.

## Notes

- All scripts **back up** the original file before writing in-place (`.bak` suffix). Use `--no-backup` to skip.
- **Output files always get a `.drawio` suffix** — if `-o` is given a path without `.drawio`, it is appended automatically so draw.io can open the result.
- `colorize.py` preserves layout, shapes, and edge routing — it only changes `fillColor`/`strokeColor`.
- `colorize.py` skips `fillColor=none` (structural lanes/containers) and image nodes.
- Scripts are stdlib-only (no external dependencies).
