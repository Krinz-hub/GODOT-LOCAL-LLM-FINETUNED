"""Extractor for Godot documentation content."""

from dataclasses import dataclass, field
import re
from typing import Dict, List


@dataclass
class DocSection:
    title: str
    section_path: str
    content: str
    code_snippets: List[str] = field(default_factory=list)


def extract_documentation_sections(html_or_md: str, source_path: str = "") -> List[DocSection]:
    """Extracts sections, text, and code snippets from documentation."""
    sections: List[DocSection] = []

    # Simple markdown or HTML code block extraction
    code_block_pattern = re.compile(r"```(?:gdscript|python|bash)?\n(.*?)```", re.DOTALL)
    snippets = code_block_pattern.findall(html_or_md)

    # Clean HTML tags if html
    clean_text = re.sub(r"<[^>]+>", " ", html_or_md)
    clean_text = re.sub(r"\s+", " ", clean_text).strip()

    # Extract title
    title = "Godot Documentation Section"
    m_h1 = re.search(r"#\s+([^\n]+)", html_or_md)
    if m_h1:
        title = m_h1.group(1).strip()
    else:
        m_html_title = re.search(r"<title>([^<]+)</title>", html_or_md, re.IGNORECASE)
        if m_html_title:
            title = m_html_title.group(1).replace("— Godot Engine documentation", "").strip()

    sections.append(DocSection(
        title=title,
        section_path=source_path,
        content=clean_text[:5000],  # Bound reasonable section length
        code_snippets=snippets,
    ))

    return sections
