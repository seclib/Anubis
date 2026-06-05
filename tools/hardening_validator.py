from __future__ import annotations

from pathlib import Path


REQUIRED_FILES = (
    Path("config/production_hardening.yaml"),
    Path("config/secrets_policy.yaml"),
    Path("config/audit_policy.yaml"),
    Path("config/permissions.yaml"),
    Path("config/sandbox.yaml"),
    Path("docs/production_hardening.md"),
)

REQUIRED_TEXT = {
    Path("config/production_hardening.yaml"): (
        "default: deny",
        "runtime_code_injection: denied",
        "generated_code_execution: denied",
        "source_modification: denied",
        "trigger_kill_switch_on_critical_findings: true",
        "automatic_production_deployment: false",
    ),
    Path("config/secrets_policy.yaml"): (
        "inline_secrets: denied",
        "raw_secret_memory_storage: denied",
        "external_reference_required",
        "redact_logs: true",
    ),
    Path("config/audit_policy.yaml"): (
        "mode: append_only",
        "integrity: hash_chain",
        "sandbox.denied",
        "kill_switch.triggered",
    ),
    Path("config/sandbox.yaml"): (
        "readonly_root: true",
        "no_new_privileges: true",
        "source.modify",
        "action: kill_switch",
    ),
    Path("docs/production_hardening.md"): (
        "arbitrary code execution",
        "plugin abuse",
        "sandbox escape attempts",
        "Production changes are never automatic.",
    ),
}


def main() -> None:
    missing = [str(path) for path in REQUIRED_FILES if not path.exists()]
    if missing:
        raise SystemExit(f"missing hardening files: {missing}")

    failures: list[str] = []
    for path, required_items in REQUIRED_TEXT.items():
        text = path.read_text(encoding="utf-8")
        for item in required_items:
            if item not in text:
                failures.append(f"{path}: missing required hardening text: {item}")

    if failures:
        raise SystemExit("\n".join(failures))

    print({"hardening_policy": "valid", "files": [str(path) for path in REQUIRED_FILES]})


if __name__ == "__main__":
    main()
