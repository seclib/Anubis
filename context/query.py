from __future__ import annotations

import re

from anubis.context.embeddings import tokenize


def expand_task_query(task: str) -> tuple[str, set[str]]:
    terms = set(tokenize(task))
    for token in re.findall(r"[A-Z][A-Za-z0-9]+", task):
        terms.add(token.lower())
    for path_part in re.findall(r"[\w.-]+", task):
        if "." in path_part:
            terms.update(part.lower() for part in path_part.split(".") if len(part) > 2)
    expanded = " ".join(sorted(terms))
    return expanded, terms


__all__ = ["expand_task_query"]
