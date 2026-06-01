from dataclasses import dataclass


@dataclass(frozen=True)
class MarkdownSection:
    heading: str
    text: str
    line_start: int
    line_end: int


def split_markdown_sections(content: str) -> list[MarkdownSection]:
    lines = content.splitlines()
    sections: list[MarkdownSection] = []
    current_heading = "Document"
    start = 1
    buffer: list[str] = []

    for index, line in enumerate(lines, start=1):
        if line.startswith("# ") or line.startswith("## "):
            if buffer:
                sections.append(MarkdownSection(current_heading, "\n".join(buffer).strip(), start, index - 1))
            current_heading = line.lstrip("#").strip()
            start = index
            buffer = [line]
        else:
            buffer.append(line)

    if buffer:
        sections.append(MarkdownSection(current_heading, "\n".join(buffer).strip(), start, len(lines)))

    return [section for section in sections if section.text]
