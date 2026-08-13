#!/usr/bin/env python3
"""Complete corporate theming for default-filled shapes that restyle.py intentionally leaves white."""
import argparse, re
import xml.etree.ElementTree as ET

PALETTE = {
    'primary': ('#e3f2fd', '#1565c0'),
    'success': ('#e8f5e9', '#2e7d32'),
    'warning': ('#fff9c4', '#f57c00'),
    'accent': ('#fff3e0', '#e65100'),
    'neutral': ('#eceff1', '#455a64'),
    'secondary': ('#f3e5f5', '#6a1b9a'),
}

def has(style, key):
    return re.search(rf'(?:^|;){re.escape(key)}(?:=|;|$)', style) is not None

def get(style, key):
    m = re.search(rf'(?:^|;){re.escape(key)}=([^;]*)', style)
    return m.group(1) if m else None

def set_keys(style, **kv):
    for key in kv:
        style = re.sub(rf'(?:^|;){re.escape(key)}=[^;]*', '', style)
    style = style.strip('; ')
    tail = ';'.join(f'{k}={v}' for k,v in kv.items())
    return ((style + ';') if style else '') + tail + ';'

def role(style):
    if 'rhombus' in style:
        return 'warning'
    if 'trapezoid' in style:
        return 'secondary'
    if 'rounded=1' in style:
        return 'success'
    return 'primary'

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('file'); args=ap.parse_args()
    tree=ET.parse(args.file); pages=tree.getroot().findall('diagram')
    model=pages[0].find('mxGraphModel'); root=model.find('root')
    model.set('background', '#f8fafc')
    changed=0
    for item in root:
        cell=item if item.tag=='mxCell' else item.find('mxCell')
        if cell is None or cell.get('vertex')!='1': continue
        style=cell.get('style') or ''
        # Preserve images, transparent labels, edge labels, and explicitly transparent shapes.
        if ('shape=image' in style or style.startswith('text;') or style.startswith('edgeLabel;')
            or get(style,'fillColor')=='none' or get(style,'strokeColor')=='none'):
            continue
        if get(style,'fillColor') is None:
            fill,stroke=PALETTE[role(style)]
            cell.set('style', set_keys(style, fillColor=fill, strokeColor=stroke, fontColor='#1f2937'))
            changed += 1
    tree.write(args.file, encoding='utf-8', xml_declaration=False)
    print(f'enhanced {changed} default-filled shapes on page 1; set background #f8fafc')
if __name__=='__main__': main()
