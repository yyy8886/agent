"""Runtime discovery and loading for an Agent's authorized Skills."""

from __future__ import annotations

from langchain_core.tools import tool

from my_agent_next.skills._loader import get

from .base import truncate_output


@tool
def discover_skills(query: str) -> str:
    """Search the current Agent's authorized Skill catalog when a new need appears.

    Args:
        query: A short description of the newly discovered task or problem.
    """
    return "This tool is resolved by the active Agent runtime."


@tool
def load_skill(name: str) -> str:
    """Load one authorized Skill's instructions before applying that Skill.

    Args:
        name: Exact Skill directory name returned by discover_skills.
    """
    return "This tool is resolved by the active Agent runtime."


def discover_authorized_skills(query: str, authorized_names: list[str]) -> str:
    """Return ranked metadata without exposing unbound Skills."""
    normalized = " ".join(str(query).casefold().split())
    terms = {term for term in normalized.replace("-", " ").split() if term}
    matches: list[tuple[int, int, str]] = []
    for order, name in enumerate(authorized_names):
        info = get(name)
        if info is None:
            continue
        haystack = f"{name} {info.name} {info.description}".casefold()
        score = sum(1 for term in terms if term in haystack)
        if normalized and normalized in haystack:
            score += 3
        matches.append((-score, order, f"- {name}: {info.description}"))
    if not matches:
        return "No authorized Skills are available for this Agent."
    matches.sort(key=lambda item: (item[0], item[1]))
    relevant = [line for score, _, line in matches if score < 0]
    lines = relevant[:8] if relevant else [item[2] for item in matches[:8]]
    return (
        "Authorized Skill matches (metadata only). Call load_skill with the exact "
        "name before following one:\n" + "\n".join(lines)
    )


def load_authorized_skill(name: str, authorized_names: list[str]) -> str:
    """Load Skill instructions only when the Agent is currently authorized."""
    requested = str(name).strip()
    if requested not in authorized_names:
        return f"Permission denied: Skill '{requested}' is not bound to this Agent."
    info = get(requested)
    if info is None:
        return f"Skill '{requested}' is missing or invalid."
    skill_dir = info.path
    scripts = _resource_names(skill_dir / "scripts")
    references = _resource_names(skill_dir / "references")
    resources: list[str] = []
    if scripts:
        resources.append("scripts/: " + ", ".join(scripts))
    if references:
        resources.append("references/: " + ", ".join(references))
    resource_text = "\nResources: " + "; ".join(resources) if resources else ""
    return truncate_output(
        f"Skill loaded: {requested}\nDescription: {info.description}\n"
        f"Directory: skills/{requested}/\n\n{info.content}{resource_text}",
        max_chars=20_000,
    )


def _resource_names(directory) -> list[str]:
    if not directory.is_dir():
        return []
    return sorted(
        path.name for path in directory.iterdir()
        if path.is_file() and not path.name.startswith(".")
    )
