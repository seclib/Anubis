from __future__ import annotations

from pathlib import Path

from anubis import (
    ArchitectureAnalyzer,
    ArchitectureSeverity,
    EventType,
    FileEdit,
    InMemoryEventBus,
    PullRequestSystem,
    RefactorPlanner,
    RefactorStatus,
)


async def test_architecture_analyzer_detects_missing_docstring_and_size(tmp_path: Path) -> None:
    path = tmp_path / "big_module.py"
    path.write_text("x = 1\n" * 4, encoding="utf-8")
    analyzer = ArchitectureAnalyzer(max_lines=2)

    findings = await analyzer.analyze_paths((path,))

    assert {finding.rule_id for finding in findings} == {
        "module.too_large",
        "module.missing_docstring",
    }
    assert any(finding.severity == ArchitectureSeverity.WARNING for finding in findings)


async def test_architecture_analyzer_detects_forbidden_dependency(tmp_path: Path) -> None:
    path = tmp_path / "ui_panel.py"
    path.write_text("import anubis.execution\n", encoding="utf-8")
    analyzer = ArchitectureAnalyzer(
        forbidden_imports={"ui_panel.py": ("anubis.execution",)}
    )

    findings = await analyzer.analyze_paths((path,))

    assert any(finding.rule_id == "dependency.forbidden" for finding in findings)


async def test_refactor_planner_proposes_docstring_change(tmp_path: Path) -> None:
    path = tmp_path / "module.py"
    path.write_text("VALUE = 1\n", encoding="utf-8")
    findings = await ArchitectureAnalyzer().analyze_paths((path,))

    proposals = await RefactorPlanner().propose(findings)

    assert len(proposals) == 1
    assert proposals[0].status == RefactorStatus.PROPOSED
    assert proposals[0].edits[0].prepend is True
    assert "docstring" in proposals[0].title.lower()


async def test_pull_request_system_generates_patch_without_applying(tmp_path: Path) -> None:
    path = tmp_path / "module.py"
    path.write_text("VALUE = 1\n", encoding="utf-8")
    findings = await ArchitectureAnalyzer().analyze_paths((path,))
    proposal = (await RefactorPlanner().propose(findings))[0]

    result = await PullRequestSystem().apply(proposal)

    assert result.applied is False
    assert result.changed_files == ()
    assert result.requires_human_approval is True
    assert "runtime source modification is disabled" in result.errors[-1]
    assert result.patch.startswith("diff --git")
    assert path.read_text(encoding="utf-8") == "VALUE = 1\n"


async def test_pull_request_system_rejects_stale_base_hash(tmp_path: Path) -> None:
    path = tmp_path / "module.py"
    original = "VALUE = 1\n"
    path.write_text(original, encoding="utf-8")
    edit = FileEdit.replace(str(path), original, "VALUE = 1", "VALUE = 2")
    path.write_text("VALUE = 3\n", encoding="utf-8")

    result = await PullRequestSystem().apply(
        __import__("anubis").RefactorProposal(
            id="proposal",
            title="change value",
            rationale="test",
            findings=(),
            edits=(edit,),
        )
    )

    assert result.applied is False
    assert result.errors[0] == f"base hash mismatch: {path}"
    assert "requires human approval" in result.errors[-1]


async def test_architecture_system_emits_events(tmp_path: Path) -> None:
    bus = InMemoryEventBus()
    path = tmp_path / "module.py"
    path.write_text("VALUE = 1\n", encoding="utf-8")
    analyzer = ArchitectureAnalyzer(event_bus=bus)
    planner = RefactorPlanner(event_bus=bus)
    pr = PullRequestSystem(event_bus=bus)

    findings = await analyzer.analyze_paths((path,))
    proposal = (await planner.propose(findings))[0]
    await pr.apply(proposal)

    event_types = [event.type for event in bus.events]

    assert EventType.ARCHITECTURE_FINDING_CREATED in event_types
    assert EventType.REFACTOR_PROPOSED in event_types
    assert EventType.PATCH_PROPOSED in event_types
    assert EventType.PATCH_REQUIRES_APPROVAL in event_types
