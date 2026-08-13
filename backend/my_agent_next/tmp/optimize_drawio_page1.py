#!/usr/bin/env python3
import argparse, base64, hashlib, urllib.parse, zlib
import xml.etree.ElementTree as ET
from pathlib import Path


def sha256_text(s):
    return hashlib.sha256((s or '').encode('utf-8')).hexdigest()


def decode_drawio_payload(text):
    """Decode diagrams.net compressed diagram: base64(raw-deflate(urlencoded XML))."""
    if not text or not text.strip():
        raise ValueError('diagram payload is empty')
    raw = base64.b64decode(''.join(text.split()))
    encoded_xml = zlib.decompress(raw, -15).decode('utf-8')
    return urllib.parse.unquote(encoded_xml)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('out')
    ap.add_argument('--manifest', required=True)
    args = ap.parse_args()

    src, out = Path(args.src), Path(args.out)
    tree = ET.parse(src)
    root = tree.getroot()
    diagrams = list(root.findall('diagram'))
    if len(diagrams) != 4:
        raise SystemExit(f'expected 4 pages, found {len(diagrams)}')

    first = diagrams[0]
    if first.get('name') != 'ad_mp_top':
        raise SystemExit(f"expected first page 'ad_mp_top', found {first.get('name')!r}")
    if first.find('mxGraphModel') is not None:
        raise SystemExit('first page is already uncompressed; refusing unexpected input')

    original_other = [(d.get('id'), d.get('name'), sha256_text(d.text)) for d in diagrams[1:]]
    xml = decode_drawio_payload(first.text)
    model = ET.fromstring(xml)
    if model.tag != 'mxGraphModel' or model.find('root') is None:
        raise SystemExit('decoded first page is not a valid mxGraphModel/root')

    first.text = None
    first.append(model)
    out.parent.mkdir(parents=True, exist_ok=True)
    tree.write(out, encoding='utf-8', xml_declaration=False)

    # Verify immediately after reconstruction.
    check = ET.parse(out).getroot()
    pages = list(check.findall('diagram'))
    if len(pages) != 4 or pages[0].find('mxGraphModel/root') is None:
        raise SystemExit('reconstructed output failed page/model verification')
    for d, expected in zip(pages[1:], original_other):
        actual = (d.get('id'), d.get('name'), sha256_text(d.text))
        if actual != expected:
            raise SystemExit(f'non-target page changed: expected {expected[:2]}, got {actual[:2]}')

    manifest = Path(args.manifest)
    manifest.write_text('\n'.join(
        [f'page_count=4', f'target_name={first.get("name")}',
         f'target_id={first.get("id", "")}', f'decoded_xml_bytes={len(xml.encode("utf-8"))}'] +
        [f'preserved_page_{i+2}={pid}|{name}|{digest}' for i, (pid, name, digest) in enumerate(original_other)]
    ) + '\n', encoding='utf-8')
    print(f'wrote reconstructed file: {out}')
    print(f'decoded first page XML bytes: {len(xml.encode("utf-8"))}')
    print('preserved compressed payload hashes for pages 2-4')

if __name__ == '__main__':
    main()
