"""Pipeline domain models.

The filename intentionally follows the project-requested `pipline.py` spelling.
"""

from dataclasses import asdict, dataclass, field


@dataclass
class PipelineEdge:
    source: str
    target: str
    condition: str = "always"


@dataclass
class PipelineDefinition:
    id: str
    name: str
    entry_agent: str
    enabled: bool = True
    edges: list[PipelineEdge] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PipelineDefinition":
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            entry_agent=str(data["entry_agent"]),
            enabled=bool(data.get("enabled", True)),
            edges=[PipelineEdge(**edge) for edge in data.get("edges", [])],
        )

