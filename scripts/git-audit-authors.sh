#!/usr/bin/env bash
set -euo pipefail

EXPECTED_NAME="${GIT_IDENTITY_NAME:-seclib}"
EXPECTED_EMAIL="${GIT_IDENTITY_EMAIL:-thaerudit@gmail.com}"

ROOT_DIR="$(git rev-parse --show-toplevel 2>/dev/null)"
cd "$ROOT_DIR"

format='%H%x1f%h%x1f%an%x1f%ae%x1f%cn%x1f%ce%x1f%s'
bad_count=0
total_count=0

join_reasons() {
  local joined=""
  local reason

  for reason in "$@"; do
    if [[ -n "$joined" ]]; then
      joined+=", "
    fi
    joined+="$reason"
  done

  printf '%s' "$joined"
}

echo "Auditing Git authors in: $ROOT_DIR"
echo "Expected author/committer: $EXPECTED_NAME <$EXPECTED_EMAIL>"
echo

while IFS=$'\037' read -r full_hash short_hash author_name author_email committer_name committer_email subject; do
  total_count=$((total_count + 1))
  reasons=()

  if [[ "$author_name" != "$EXPECTED_NAME" ]]; then
    reasons+=("author name '$author_name'")
  fi
  if [[ "$author_email" != "$EXPECTED_EMAIL" ]]; then
    reasons+=("author email '$author_email'")
  fi
  if [[ "$committer_name" != "$EXPECTED_NAME" ]]; then
    reasons+=("committer name '$committer_name'")
  fi
  if [[ "$committer_email" != "$EXPECTED_EMAIL" ]]; then
    reasons+=("committer email '$committer_email'")
  fi

  if (( ${#reasons[@]} > 0 )); then
    bad_count=$((bad_count + 1))
    printf '%s %s\n' "$short_hash" "$subject"
    printf '  author:    %s <%s>\n' "$author_name" "$author_email"
    printf '  committer: %s <%s>\n' "$committer_name" "$committer_email"
    printf '  mismatch:  %s\n' "$(join_reasons "${reasons[@]}")"
    printf '  full hash: %s\n\n' "$full_hash"
  fi
done < <(git log --all --format="$format")

echo "Audited commits: $total_count"
echo "Mismatched commits: $bad_count"

if (( bad_count > 0 )); then
  echo
  echo "Run scripts/git-fix-identity.sh to enforce local config and install hooks."
  echo "History rewrite is available as an explicit opt-in:"
  echo "  scripts/git-fix-identity.sh --rewrite-history"
  exit 1
fi

echo "All checked commits match the expected Git identity."
