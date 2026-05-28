from pathlib import Path
from typing import List

def read_file(path: str) -> str:
    return Path(path).read_text()


def write_file(path: str, content: str) -> str:
    Path(path).write_text(content)
    return "file_written"


def list_files(path: str = ".") -> List[str]:
    p = Path(path)
    if not p.exists():
        return []
    return [str(x) for x in sorted(p.rglob("*"))]