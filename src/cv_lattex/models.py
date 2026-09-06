"""Renderer-independent curriculum data and source accounting."""

from __future__ import annotations

import html
import json
from dataclasses import dataclass, field
from functools import cache
from importlib.resources import files
from typing import Literal


class CVError(ValueError):
    """An actionable input or conversion error."""


@cache
def catalog() -> dict:
    return json.loads(files("cv_lattex").joinpath("catalog.json").read_text("utf-8"))


def clean(value: str) -> str:
    """Decode one remaining HTML-entity layer, retaining the raw source separately."""
    return html.unescape(value).strip()


@dataclass(frozen=True)
class SourceField:
    path: str
    tag: str
    name: str
    value: str
    disposition: Literal["content", "administrative", "private", "unknown"]

    @property
    def text(self) -> str:
        return clean(self.value)


@dataclass(frozen=True)
class Issue:
    code: str
    path: str
    message: str


@dataclass
class Entry:
    section: str
    tag: str
    path: str
    fields: list[SourceField] = field(default_factory=list)
    id: str = ""
    year: int | None = None

    def find(self, *names: str, language: str = "pt") -> SourceField | None:
        for name in names:
            candidates = [name, name + "-INGLES", name + "-EN"]
            if language == "en":
                candidates = [name + "-INGLES", name + "-EN", name]
            for candidate in candidates:
                for item in self.fields:
                    if (
                        item.name == candidate
                        and item.text
                        and item.disposition == "content"
                    ):
                        return item
        return None

    def title_field(self, language: str = "pt") -> SourceField | None:
        section = catalog()["sections"][self.section]
        if section["kind"] == "education":
            return self.find("NOME-CURSO", "NOME-DO-CURSO", language=language)
        if self.section == "profile":
            return self.find("NOME-COMPLETO", language=language)
        return self.find(*section["titles"], language=language)

    def title(self, language: str = "pt") -> str:
        value = self.title_field(language)
        return value.text if value else catalog()["sections"][self.section][language]


@dataclass
class Curriculum:
    raw_xml: bytes
    entries: list[Entry]
    fields: list[SourceField]
    issues: list[Issue]

    @property
    def name(self) -> str:
        profile = next(
            (entry for entry in self.entries if entry.section == "profile"), None
        )
        name = profile.find("NOME-COMPLETO") if profile else None
        return name.text if name else ""
