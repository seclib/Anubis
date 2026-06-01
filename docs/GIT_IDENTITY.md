# Git Identity Rules

All commits in this repository must use:

```text
user.name  = seclib
user.email = thaerudit@gmail.com
```

The local repository config is authoritative. Do not rely on global Git config
for this project.

## Enforce Locally

Run:

```bash
scripts/git-fix-identity.sh
```

This sets:

```bash
git config --local user.name "seclib"
git config --local user.email "thaerudit@gmail.com"
```

It also installs local `pre-commit` and `commit-msg` hooks under `.git/hooks`.
The hooks reject commits when local config, effective author identity, or
effective committer identity do not match the required values.

## Audit Existing History

Run:

```bash
scripts/git-audit-authors.sh
```

The audit checks every commit reachable from `--all` and reports mismatched
author or committer names/emails. It exits with status `1` when mismatches are
found.

## Optional History Rewrite

History rewrite is destructive because commit hashes change. Use it only after
coordinating with anyone who has cloned or forked the repository.

Prerequisite:

```bash
python3 -m pip install git-filter-repo
```

Then run:

```bash
scripts/git-fix-identity.sh --rewrite-history
```

The rewrite normalizes any mismatched author or committer identity to:

```text
seclib <thaerudit@gmail.com>
```

The script prompts for `REWRITE` before changing history. It refuses to run with
uncommitted changes unless `--force` is passed.

## Overrides

For unusual maintenance work, these environment variables can override the
defaults:

```bash
GIT_IDENTITY_NAME
GIT_IDENTITY_EMAIL
```
