export type GitFileChange = {
  path: string;
  status: string;
  staged: boolean;
  unstaged: boolean;
};

export type GitWorkspaceStatus = {
  repo_path: string;
  branch: string;
  upstream: string | null;
  clean: boolean;
  changes: GitFileChange[];
  ahead: number;
  behind: number;
};

export type DiffFile = {
  path: string;
  status: string;
  additions: number;
  deletions: number;
  hunks: string[];
};

export type DiffView = {
  repo_path: string;
  files: DiffFile[];
  raw: string;
  additions: number;
  deletions: number;
};

export type CommitProposal = {
  message: string;
  paths: string[];
  summary: string;
  risk: string;
};

export type CommitResult = {
  success: boolean;
  proposal: CommitProposal;
  commit_sha: string | null;
};

export type PullRequestDraft = {
  title: string;
  body: string;
  head_branch: string;
  base_branch: string;
  changed_files: string[];
  diff_summary: string;
  risks: string[];
  linked_tasks: string[];
};

export async function gitStatus(repoPath = "."): Promise<GitWorkspaceStatus> {
  return postGit<GitWorkspaceStatus>("/status", { repo_path: repoPath });
}

export async function createGitBranch(repoPath: string, branch: string, baseBranch?: string) {
  return postGit("/branches", { repo_path: repoPath, branch, base_branch: baseBranch });
}

export async function gitDiff(repoPath = ".", paths: string[] = [], staged = false): Promise<DiffView> {
  return postGit<DiffView>("/diff", { repo_path: repoPath, paths, staged });
}

export async function generateCommitProposal(
  repoPath: string,
  description: string,
  paths: string[] = [],
  kind = "feat",
  scope?: string,
): Promise<CommitProposal> {
  return postGit<CommitProposal>("/commits/proposal", {
    repo_path: repoPath,
    description,
    paths,
    kind,
    scope,
  });
}

export async function commitGitChanges(repoPath: string, proposal: CommitProposal): Promise<CommitResult> {
  return postGit<CommitResult>("/commits", {
    repo_path: repoPath,
    message: proposal.message,
    paths: proposal.paths,
    summary: proposal.summary,
    risk: proposal.risk,
  });
}

export async function preparePullRequestDraft(
  repoPath: string,
  description: string,
  options: { title?: string; baseBranch?: string; linkedTasks?: string[] } = {},
): Promise<PullRequestDraft> {
  return postGit<PullRequestDraft>("/pull-request/draft", {
    repo_path: repoPath,
    title: options.title,
    description,
    base_branch: options.baseBranch ?? "main",
    linked_tasks: options.linkedTasks ?? [],
  });
}

async function postGit<T>(path: string, payload: Record<string, unknown>): Promise<T> {
  const response = await fetch(`/api/git${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || `Git workspace request failed: ${path}`);
  }
  return (await response.json()) as T;
}
