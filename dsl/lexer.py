from __future__ import annotations

import shlex
from dataclasses import dataclass


@dataclass(frozen=True)
class Token:
    value: str


def tokenize(text: str) -> list[Token]:
    lexer = shlex.shlex(text, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    lexer.wordchars += "/.-_:"
    return [Token(token) for token in lexer]


def split_pipeline(text: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    quote: str | None = None
    depth = 0

    for char in text:
        if char in {"'", '"'}:
            quote = None if quote == char else char if quote is None else quote
        elif quote is None:
            if char == "{":
                depth += 1
            elif char == "}":
                depth = max(0, depth - 1)
            elif char == "|" and depth == 0:
                part = "".join(current).strip()
                if part:
                    parts.append(part)
                current = []
                continue
        current.append(char)

    part = "".join(current).strip()
    if part:
        parts.append(part)
    return parts


__all__ = ["Token", "split_pipeline", "tokenize"]
