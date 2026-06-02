from backend.skills.compiler import (
    CompiledSkill,
    SafeSkillRuntime,
    SkillCompiler,
    SkillCritic,
    SkillModuleGenerator,
    SkillParser,
    ToolMapper,
    example_compiled_skill,
)

try:
    from backend.skills.parser import Skill, SkillRepository, parse_skill_markdown
except ModuleNotFoundError:
    Skill = None  # type: ignore[assignment]
    SkillRepository = None  # type: ignore[assignment]
    parse_skill_markdown = None  # type: ignore[assignment]

try:
    from backend.skills.obsidian_extractor import extract_skills_from_obsidian
except ModuleNotFoundError:
    extract_skills_from_obsidian = None  # type: ignore[assignment]

__all__ = [
    "CompiledSkill",
    "SafeSkillRuntime",
    "Skill",
    "SkillCompiler",
    "SkillCritic",
    "SkillModuleGenerator",
    "SkillParser",
    "SkillRepository",
    "ToolMapper",
    "example_compiled_skill",
    "extract_skills_from_obsidian",
    "parse_skill_markdown",
]
