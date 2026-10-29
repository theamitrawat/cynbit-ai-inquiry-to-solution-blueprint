"""Loads Cynbit's public service/product catalog (data/cynbit_catalog.json).

Why a JSON file and not RAG/vector DB? 15 short entries fit in the prompt directly.
A retrieval system would add moving parts without improving accuracy.
"""
import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, HttpUrl

from app.schemas import ServiceCategory

CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "cynbit_catalog.json"


class CatalogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    kind: Literal["service", "product"]
    category: ServiceCategory | None = None
    description: str
    source_url: HttpUrl


@lru_cache
def load_catalog(path: Path = CATALOG_PATH) -> tuple[CatalogEntry, ...]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    entries = tuple(CatalogEntry(**item) for item in raw["entries"])
    names = [e.name for e in entries]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate names in catalog.")
    return entries


def catalog_names() -> set[str]:
    return {e.name for e in load_catalog()}


def catalog_as_prompt_text() -> str:
    """Compact text block to embed in the LLM prompt (Stage 2)."""
    lines = []
    for e in load_catalog():
        cat = e.category.value if e.category else "n/a"
        lines.append(f"- [{e.kind}] {e.name} (category: {cat}): {e.description}")
    return "\n".join(lines)
