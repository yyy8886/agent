"""Local stdio MCP server for the desktop companion."""

from datetime import datetime
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from mcp.server.fastmcp import FastMCP


server = FastMCP(
    name="my-agent-tools",
    instructions="提供桌面助手使用的低风险本地工具。",
)

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"


@server.tool()
def get_current_time() -> str:
    """返回当前电脑所在时区的日期、时间和时区偏移。"""
    return datetime.now().astimezone().isoformat(timespec="seconds")


@server.tool()
def create_drawio_flowchart(
    title: str,
    steps: list[str],
    filename: str = "diagram.drawio",
) -> str:
    """根据标题和顺序步骤生成可编辑的 draw.io 流程图文件。"""
    cleaned_steps = [step.strip() for step in steps if step.strip()]
    if not cleaned_steps:
        return "生成失败：steps 至少需要一个非空步骤。"
    if len(cleaned_steps) > 20:
        return "生成失败：第一版流程图最多支持 20 个步骤。"

    safe_stem = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(filename).stem).strip("_")
    output_file = OUTPUT_DIR / f"{safe_stem or 'diagram'}.drawio"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    mxfile = ET.Element("mxfile", host="app.diagrams.net")
    diagram = ET.SubElement(mxfile, "diagram", name=title.strip() or "流程图")
    model = ET.SubElement(diagram, "mxGraphModel", grid="1", page="1")
    root = ET.SubElement(model, "root")
    ET.SubElement(root, "mxCell", id="0")
    ET.SubElement(root, "mxCell", id="1", parent="0")

    node_ids = []
    for index, label in enumerate(cleaned_steps, start=1):
        node_id = f"node-{index}"
        node_ids.append(node_id)
        cell = ET.SubElement(
            root,
            "mxCell",
            id=node_id,
            value=label,
            style=("rounded=1;whiteSpace=wrap;html=1;fillColor=#dae8fc;"
                   "strokeColor=#6c8ebf;fontSize=14;"),
            vertex="1",
            parent="1",
        )
        ET.SubElement(cell, "mxGeometry", x="240", y=str(60 + (index - 1) * 120),
                      width="320", height="60", **{"as": "geometry"})

    for index in range(len(node_ids) - 1):
        edge = ET.SubElement(
            root,
            "mxCell",
            id=f"edge-{index + 1}",
            style="edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;endArrow=block;",
            edge="1",
            parent="1",
            source=node_ids[index],
            target=node_ids[index + 1],
        )
        ET.SubElement(edge, "mxGeometry", relative="1", **{"as": "geometry"})

    ET.ElementTree(mxfile).write(output_file, encoding="utf-8", xml_declaration=True)
    return f"流程图已生成：{output_file}"


if __name__ == "__main__":
    server.run(transport="stdio")
