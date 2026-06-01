#!/usr/bin/env bash
set -euo pipefail

EXPECTED_NAME="${GIT_IDENTITY_NAME:-seclib}"
EXPECTED_EMAIL="${GIT_IDENTITY_EMAIL:-thaerudit@gmail.com}"

ROOT_DIR="$(git rev-parse --show-toplevel 2>/dev/null)"
cd "$ROOT_DIR"

usage() {
  cat <<EOF
Usage: $0 [--check-only] [--install-hooks] [--rewrite-history] [--force]

Enforces local Git identity for this repository:
  user.name  = $EXPECTED_NAME
  user.email = $EXPECTED_EMAIL

Options:
  --check-only        Verify current local/effective identity and exit.
  --install-hooks    Install identity prevention hooks only.
  --rewrite-history  Rewrite matching old author/committer metadata with git-filter-repo.
  --force            Allow history rewrite with uncommitted changes present.

Environment overrides:
  GIT_IDENTITY_NAME
  GIT_IDENTITY_EMAIL
EOF
}

check_identity() {
  local local_name local_email author_ident committer_ident
  local_name="$(git config --local --get user.name || true)"
  local_email="$(git config --local --get user.email || true)"
  author_ident="$(git var GIT_AUTHOR_IDENT)"
  committer_ident="$(git var GIT_COMMITTER_IDENT)"

  if [[ "$local_name" != "$EXPECTED_NAME" || "$local_email" != "$EXPECTED_EMAIL" ]]; then
    cat >&2 <<EOF
Wrong local Git identity.
Expected: $EXPECTED_NAME <$EXPECTED_EMAIL>
Current:  ${local_name:-<unset>} <${local_email:-unset}>

Run:
  scripts/git-fix-identity.sh
EOF
    return 1
  fi

  if [[ "$author_ident" != "$EXPECTED_NAME <$EXPECTED_EMAIL> "* ]]; then
    cat >&2 <<EOF
Wrong effective author identity for this commit:
  $author_ident

Expected:
  $EXPECTED_NAME <$EXPECTED_EMAIL>

Check for --author, GIT_AUTHOR_NAME, or GIT_AUTHOR_EMAIL overrides.
EOF
    return 1
  fi

  if [[ "$committer_ident" != "$EXPECTED_NAME <$EXPECTED_EMAIL> "* ]]; then
    cat >&2 <<EOF
Wrong effective committer identity for this commit:
  $committer_ident

Expected:
  $EXPECTED_NAME <$EXPECTED_EMAIL>

Check for GIT_COMMITTER_NAME or GIT_COMMITTER_EMAIL overrides.
EOF
    return 1
  fi
}

install_hooks() {
  mkdir -p .git/hooks

  cat > .git/hooks/pre-commit <<'HOOK'
#!/usr/bin/env bash
set -euo pipefail

scripts/git-fix-identity.sh --check-only
HOOK

  cat > .git/hooks/commit-msg <<'HOOK'
#!/usr/bin/env bash
set -euo pipefail

scripts/git-fix-identity.sh --check-only
HOOK

  chmod +x .git/hooks/pre-commit .git/hooks/commit-msg
  echo "Installed local Git identity hooks in .git/hooks."
}

rewrite_history() {
  local force="$1"

  if ! command -v git-filter-repo >/dev/null 2>&1; then
    cat >&2 <<'EOF'
git-filter-repo is required for history rewrite.

Install one of:
  python3 -m pip install git-filter-repo
  pipx install git-filter-repo
EOF
    return 1
  fi

  if [[ "$force" != "true" && -n "$(git status --porcelain)" ]]; then
    cat >&2 <<'EOF'
Refusing to rewrite history with uncommitted changes.
Commit, stash, or rerun with --force after making a backup.
EOF
    return 1
  fi

  cat <<EOF
About to rewrite Git history metadata.

Every mismatched author or committer identity will be normalized to:
  $EXPECTED_NAME <$EXPECTED_EMAIL>

This rewrites commit hashes. Coordinate with every clone/fork before force-pushing.
EOF

  read -r -p "Type REWRITE to continue: " confirmation
  if [[ "$confirmation" != "REWRITE" ]]; then
    echo "History rewrite cancelled."
    return 1
  fi

  git filter-repo --force --commit-callback "
new_name = b'$EXPECTED_NAME'
new_email = b'$EXPECTED_EMAIL'

if commit.author_name != new_name or commit.author_email != new_email:
    commit.author_name = new_name
    commit.author_email = new_email
if commit.committer_name != new_name or commit.committer_email != new_email:
    commit.committer_name = new_name
    commit.committer_email = new_email
"
}

mode="apply"
force="false"

while (($#)); do
  case "$1" in
    --check-only)
      mode="check"
      ;;
    --install-hooks)
      mode="hooks"
      ;;
    --rewrite-history)
      mode="rewrite"
      ;;
    --force)
      force="true"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

case "$mode" in
  check)
    check_identity
    ;;
  hooks)
    install_hooks
    ;;
  rewrite)
    rewrite_history "$force"
    ;;
  apply)
    git config --local user.name "$EXPECTED_NAME"
    git config --local user.email "$EXPECTED_EMAIL"
    install_hooks
    check_identity
    echo "Local Git identity enforced for $ROOT_DIR."
    ;;
esac
