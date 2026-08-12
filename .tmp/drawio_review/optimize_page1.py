from pathlib import Path
import base64
import urllib.parse
import zlib
import xml.etree.ElementTree as ET


SOURCE = Path(".tmp/drawio_review/source.drawio")
OUTPUT = Path(".tmp/drawio_review/ad_mp_top_optimized.drawio")


def decode(text: str) -> ET.Element:
    data = zlib.decompress(base64.b64decode(text), -15).decode("utf-8")
    return ET.fromstring(urllib.parse.unquote(data))


def encode(root: ET.Element) -> str:
    xml = ET.tostring(root, encoding="unicode")
    quoted = urllib.parse.quote(xml, safe="~()*!.'")
    compressor = zlib.compressobj(level=9, wbits=-15)
    packed = compressor.compress(quoted.encode("utf-8")) + compressor.flush()
    return base64.b64encode(packed).decode("ascii")


document = ET.fromstring(SOURCE.read_text(encoding="utf-8"))
page = document.findall("diagram")[0]
graph = decode(page.text or "")
root = graph.find("root")
assert root is not None

# Remove the accidental placeholder in the open center of the schematic.
for cell in list(root):
    if cell.get("vertex") == "1" and cell.get("value", "").strip() == "Text":
        root.remove(cell)

# Align the four repeated memory-clock branches to one clear component grid.
branch_rows = {
    "XR": 430.0,
    "dir": 570.0,
    "sft": 710.0,
    "sfi": 850.0,
}
for cell in root.findall("mxCell"):
    value = cell.get("value", "")
    geometry = cell.find("mxGeometry")
    if geometry is None or cell.get("vertex") != "1":
        continue
    for suffix, center_y in branch_rows.items():
        plain = value.replace('<font style="font-size: 12px">', "").replace("</font>", "")
        if plain == f"div_{suffix}":
            geometry.set("x", "190")
            geometry.set("y", str(center_y - 20))
            geometry.set("width", "50")
            geometry.set("height", "20")
        elif plain == f"BUF_{suffix}":
            geometry.set("x", "250")
            geometry.set("y", str(center_y - 20))
            geometry.set("width", "60")
            geometry.set("height", "20")
        elif plain in {f"XRAM_MAX" if suffix == "XR" else f"MAX_{suffix}"}:
            geometry.set("x", "320")
            geometry.set("y", str(center_y))
            geometry.set("width", "100")
            geometry.set("height", "30")
        elif plain == "ICG" and abs(float(geometry.get("y", "0")) - center_y) < 45:
            geometry.set("x", "440")
            geometry.set("y", str(center_y))
        elif plain.startswith("RFSPHDS") and abs(float(geometry.get("y", "0")) - center_y) < 45:
            geometry.set("x", "500")
            geometry.set("y", str(center_y))
            geometry.set("width", "180")

# Make the page title deliberate and make red clock-net labels consistent.
for cell in root.findall("mxCell"):
    value = cell.get("value", "")
    if "ad_mp_top" in value:
        cell.set("value", '<b><font style="font-size: 26px">ad_mp_top</font></b>')
    if any(name in value for name in ("pll_cpu_clk", "sys_apb_clk", "devfi_clk")):
        style = cell.get("style", "")
        if "fontStyle=" not in style:
            style += "fontStyle=1;"
        cell.set("style", style)

page.text = encode(graph)
OUTPUT.write_text(ET.tostring(document, encoding="unicode"), encoding="utf-8")
print(OUTPUT.resolve())
