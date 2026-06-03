from __future__ import annotations


class GitHubTool:
    """Simulation-first GitHub tool with API-ready action boundaries."""

    def execute(self, input: dict) -> dict:
        action = str(input.get("action", "")).strip().lower()
        if action == "create_repo":
            return self._create_repo(input)
        if action == "list_issues":
            return self._list_issues(input)
        if action == "commit":
            return self._commit(input)
        return {"ok": False, "error": f"unknown github action: {action}"}

    def _create_repo(self, input: dict) -> dict:
        name = str(input.get("name") or input.get("repo") or "anubis-repo").strip()
        private = bool(input.get("private", True))
        return {
            "ok": True,
            "action": "create_repo",
            "mode": "mock",
            "repo": name,
            "private": private,
            "url": f"https://github.com/mock/{name}",
        }

    def _list_issues(self, input: dict) -> dict:
        repo = str(input.get("repo", "anubis-repo")).strip()
        return {
            "ok": True,
            "action": "list_issues",
            "mode": "mock",
            "repo": repo,
            "issues": [
                {"number": 1, "title": "Wire ANUBIS tool router", "state": "open"},
                {"number": 2, "title": "Add real GitHub API adapter", "state": "open"},
            ],
        }

    def _commit(self, input: dict) -> dict:
        repo = str(input.get("repo", "anubis-repo")).strip()
        message = str(input.get("message", "ANUBIS simulated commit")).strip()
        files = list(input.get("files", [])) if isinstance(input.get("files", []), list) else []
        return {
            "ok": True,
            "action": "commit",
            "mode": "mock",
            "repo": repo,
            "message": message,
            "files": files,
            "sha": "mock-anubis-commit",
        }


__all__ = ["GitHubTool"]
