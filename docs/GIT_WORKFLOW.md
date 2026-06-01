# Git Workflow

## Branches

- `main` is always releasable.
- Feature work uses short-lived branches named `feature/<topic>`, `fix/<topic>`, or `chore/<topic>`.
- Keep branches focused on one behavior change or one maintenance slice.

## Local Checks

Run the same baseline before opening a pull request:

```bash
make check
```

This compiles Python packages, runs unit tests, and builds the desktop web shell when dependencies are installed.

Git identity must also be enforced locally:

```bash
scripts/git-fix-identity.sh
scripts/git-audit-authors.sh
```

See `docs/GIT_IDENTITY.md` for the required identity, prevention hooks, and
optional history rewrite workflow.

## Pull Requests

- Describe user-visible behavior, architecture impact, and verification commands.
- Keep generated runtime state, logs, caches, and local database files out of commits.
- Prefer additive migrations and compatibility adapters over moving legacy entrypoints in the same PR.
- Do not merge while CI is red unless the failure is documented as unrelated infrastructure noise.

## Release Hygiene

- Tag releases from `main`.
- Rebuild Qdrant indexes from Markdown vault content; do not treat vector DB data as source of truth.
- Keep `.env.example`, `requirements.txt`, `desktop/package.json`, and Docker/Compose files in sync with setup docs.
