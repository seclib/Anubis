from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from modules.osint.schemas import (
    AdapterExecution,
    AnalysisReport,
    FootprintReport,
    IdentityReport,
    OsintInput,
    OsintReport,
)


URL_RE = re.compile(r"https?://[^\s\"'<>]+")

PLATFORM_PATTERNS: tuple[tuple[str, str], ...] = (
    ("linkedin", "linkedin.com"),
    ("instagram", "instagram.com"),
    ("facebook", "facebook.com"),
    ("telegram", "t.me"),
    ("twitter/x", "twitter.com"),
    ("twitter/x", "x.com"),
    ("vk", "vk.com"),
    ("youtube", "youtube.com"),
    ("tiktok", "tiktok.com"),
    ("github", "github.com"),
)


class OsintSkillAdapter:
    """Adapter between Anubis and the external osint-skill scripts."""

    def __init__(self, skill_path: Path | None = None, timeout_seconds: int = 90) -> None:
        self.skill_path = skill_path or discover_skill_path()
        self.timeout_seconds = timeout_seconds

    def execute(self, request: OsintInput) -> AdapterExecution:
        target = request.target.strip()
        if not target:
            raise ValueError("OSINT target required")
        if not self.skill_path.exists():
            raise FileNotFoundError(f"osint-skill repository not found: {self.skill_path}")

        diagnostics: list[str] = []
        diagnostics.extend(self._run_script("diagnose.sh").diagnostics)

        volley = self._run_script("first-volley.sh", target, request.context)
        diagnostics.extend(volley.diagnostics)
        merge_output = ""
        outdir = _extract_outdir(volley.output)
        if outdir:
            merged = self._run_script("merge-volley.sh", outdir)
            diagnostics.extend(merged.diagnostics)
            merge_output = merged.output

        report = normalize_skill_output(target, "\n".join([volley.output, merge_output]))
        if not report.footprint.mentions:
            report.analysis.inferred_traits.append("limited_provider_coverage")
        return AdapterExecution(report=report, diagnostics=diagnostics)

    def _run_script(self, script_name: str, *args: str) -> "_ScriptResult":
        script = self.skill_path / "scripts" / script_name
        if not script.exists():
            return _ScriptResult("", [f"missing script: {script}"])

        command = ["bash", str(script), *[arg for arg in args if arg]]
        try:
            completed = subprocess.run(
                command,
                cwd=self.skill_path,
                env=os.environ.copy(),
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            output = "\n".join(part for part in [exc.stdout or "", exc.stderr or ""] if part)
            return _ScriptResult(output, [f"{script_name} timed out after {self.timeout_seconds}s"])

        output = "\n".join(part for part in [completed.stdout, completed.stderr] if part)
        diagnostics = []
        if completed.returncode != 0:
            diagnostics.append(f"{script_name} exited {completed.returncode}")
        return _ScriptResult(output, diagnostics)


class _ScriptResult:
    def __init__(self, output: str, diagnostics: list[str] | None = None) -> None:
        self.output = output
        self.diagnostics = diagnostics or []


def discover_skill_path() -> Path:
    configured = os.environ.get("OSINT_SKILL_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    ai_root = Path(__file__).resolve().parents[4]
    return ai_root / "osint-skill"


def normalize_skill_output(target: str, output: str) -> OsintReport:
    urls = _unique(_clean_url(match.group(0)) for match in URL_RE.finditer(output))
    mentions = [{"platform": _platform_for_url(url), "url": url} for url in urls]
    platforms = _unique(mention["platform"] for mention in mentions)
    confidence = _confidence(len(mentions))

    return OsintReport(
        identity=_identity_from_target(target),
        footprint=FootprintReport(platforms=platforms, mentions=mentions),
        analysis=AnalysisReport(confidence=confidence, inferred_traits=[]),
    )


def _identity_from_target(target: str) -> IdentityReport:
    text = target.strip()
    if text.startswith("@") and len(text) > 1:
        return IdentityReport(usernames=[text[1:]])

    parsed = urlparse(text)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        username = _username_from_url(parsed.path)
        aliases = [parsed.netloc.lower()]
        usernames = [username] if username else []
        return IdentityReport(aliases=aliases, usernames=usernames)

    return IdentityReport(names=[text])


def _username_from_url(path: str) -> str:
    parts = [part for part in path.split("/") if part]
    if not parts:
        return ""
    return parts[-1].lstrip("@")


def _platform_for_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    for platform, marker in PLATFORM_PATTERNS:
        if marker in host:
            return platform
    return host.removeprefix("www.") or "web"


def _extract_outdir(output: str) -> str:
    match = re.search(r"Output:\s*(/tmp/osint-[^\s/]+/?)", output)
    return match.group(1).rstrip("/") if match else ""


def _clean_url(url: str) -> str:
    return url.rstrip(".,);]")


def _unique(values: object) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _confidence(mention_count: int) -> float:
    if mention_count <= 0:
        return 0.0
    return min(1.0, round(0.25 + (mention_count * 0.08), 2))


__all__ = ["OsintSkillAdapter", "discover_skill_path", "normalize_skill_output"]

