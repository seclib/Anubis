import { FormEvent, useEffect, useState } from "react";
import { GitBranch, GitCommit, GitPullRequest, RefreshCw } from "lucide-react";
import {
  createGitBranch,
  generateCommitProposal,
  gitDiff,
  gitStatus,
  preparePullRequestDraft,
  type CommitProposal,
  type DiffView,
  type GitWorkspaceStatus,
  type PullRequestDraft,
} from "../core/gitWorkspace";

export function GitWorkspacePanel() {
  const [repoPath, setRepoPath] = useState(".");
  const [branchName, setBranchName] = useState("anubis/task/native-git");
  const [description, setDescription] = useState("add native Git workflow");
  const [status, setStatus] = useState<GitWorkspaceStatus | null>(null);
  const [diff, setDiff] = useState<DiffView | null>(null);
  const [proposal, setProposal] = useState<CommitProposal | null>(null);
  const [draft, setDraft] = useState<PullRequestDraft | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const [nextStatus, nextDiff] = await Promise.all([gitStatus(repoPath), gitDiff(repoPath)]);
      setStatus(nextStatus);
      setDiff(nextDiff);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Git workspace unavailable");
    } finally {
      setLoading(false);
    }
  }

  async function branch(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      await createGitBranch(repoPath, branchName);
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Branch creation failed");
      setLoading(false);
    }
  }

  async function proposeCommit() {
    setLoading(true);
    setError("");
    try {
      setProposal(await generateCommitProposal(repoPath, description, diff?.files.map((file) => file.path) ?? []));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Commit proposal failed");
    } finally {
      setLoading(false);
    }
  }

  async function preparePr() {
    setLoading(true);
    setError("");
    try {
      setDraft(await preparePullRequestDraft(repoPath, description));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "PR draft failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="flex min-h-0 flex-col overflow-auto bg-neutral-950 px-8 py-7">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-neutral-50">Git Workspace</h2>
          <p className="mt-1 text-sm text-neutral-500">Branch, inspect, commit, and prepare pull requests.</p>
        </div>
        <button
          type="button"
          onClick={refresh}
          disabled={loading}
          className="flex items-center gap-2 rounded-lg border border-neutral-800 bg-neutral-900 px-3 py-2 text-sm text-neutral-200 transition hover:border-neutral-700 disabled:opacity-50"
        >
          <RefreshCw size={14} />
          Refresh
        </button>
      </header>

      <div className="mt-6 grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="space-y-4">
          <div className="rounded-lg border border-neutral-800 bg-neutral-900/40 p-4">
            <label className="text-xs uppercase tracking-wide text-neutral-500" htmlFor="git-repo-path">
              Repository
            </label>
            <input
              id="git-repo-path"
              value={repoPath}
              onChange={(event) => setRepoPath(event.target.value)}
              className="mt-2 h-10 w-full rounded border border-neutral-800 bg-neutral-950 px-3 font-mono text-sm text-neutral-100 outline-none focus:border-neutral-600"
            />
            <div className="mt-3 flex flex-wrap gap-2 text-xs text-neutral-500">
              <span>Branch: {status?.branch ?? "unknown"}</span>
              <span>{status?.clean ? "Clean" : `${status?.changes.length ?? 0} change(s)`}</span>
              {status?.upstream && <span>Upstream: {status.upstream}</span>}
            </div>
          </div>

          <form onSubmit={branch} className="rounded-lg border border-neutral-800 bg-neutral-900/40 p-4">
            <div className="mb-3 flex items-center gap-2 text-sm font-medium text-neutral-200">
              <GitBranch size={15} />
              Branch creation
            </div>
            <div className="flex gap-2">
              <input
                value={branchName}
                onChange={(event) => setBranchName(event.target.value)}
                className="h-10 min-w-0 flex-1 rounded border border-neutral-800 bg-neutral-950 px-3 font-mono text-sm text-neutral-100 outline-none focus:border-neutral-600"
              />
              <button className="rounded bg-neutral-100 px-3 text-sm font-medium text-neutral-950" type="submit" disabled={loading}>
                Create
              </button>
            </div>
          </form>

          <div className="rounded-lg border border-neutral-800 bg-neutral-900/40 p-4">
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm font-medium text-neutral-200">
                <GitCommit size={15} />
                Commit proposal
              </div>
              <button className="text-xs text-neutral-300 hover:text-white" type="button" onClick={proposeCommit}>
                Generate
              </button>
            </div>
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              className="min-h-[72px] w-full resize-none rounded border border-neutral-800 bg-neutral-950 px-3 py-2 text-sm text-neutral-100 outline-none focus:border-neutral-600"
            />
            {proposal && (
              <div className="mt-3 rounded border border-neutral-800 bg-neutral-950 p-3">
                <p className="font-mono text-sm text-emerald-300">{proposal.message}</p>
                <p className="mt-2 text-xs text-neutral-500">{proposal.summary}</p>
              </div>
            )}
          </div>

          <div className="rounded-lg border border-neutral-800 bg-neutral-900/40 p-4">
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm font-medium text-neutral-200">
                <GitPullRequest size={15} />
                Pull request preparation
              </div>
              <button className="text-xs text-neutral-300 hover:text-white" type="button" onClick={preparePr}>
                Prepare
              </button>
            </div>
            {draft ? (
              <div className="space-y-3">
                <p className="text-sm font-medium text-neutral-100">{draft.title}</p>
                <p className="text-xs text-neutral-500">
                  {draft.head_branch} {"->"} {draft.base_branch} · {draft.diff_summary}
                </p>
                <pre className="max-h-48 overflow-auto rounded border border-neutral-800 bg-neutral-950 p-3 text-xs leading-5 text-neutral-400">
                  {draft.body}
                </pre>
              </div>
            ) : (
              <p className="text-sm text-neutral-500">Generate a PR draft from the current branch and diff.</p>
            )}
          </div>
        </div>

        <aside className="space-y-4">
          <div className="rounded-lg border border-neutral-800 bg-neutral-900/40 p-4">
            <h3 className="text-sm font-medium text-neutral-200">Changed files</h3>
            <div className="mt-3 space-y-2">
              {(status?.changes ?? []).map((change) => (
                <div key={change.path} className="rounded border border-neutral-800 bg-neutral-950 px-3 py-2">
                  <p className="truncate font-mono text-xs text-neutral-200">{change.path}</p>
                  <p className="mt-1 text-[11px] text-neutral-500">{change.status}</p>
                </div>
              ))}
              {status?.clean && <p className="text-sm text-neutral-500">No changes.</p>}
            </div>
          </div>

          <div className="rounded-lg border border-neutral-800 bg-neutral-900/40 p-4">
            <h3 className="text-sm font-medium text-neutral-200">Diff viewer</h3>
            <p className="mt-2 text-xs text-neutral-500">
              {diff ? `${diff.files.length} file(s), +${diff.additions}/-${diff.deletions}` : "No diff loaded"}
            </p>
            <pre className="mt-3 max-h-80 overflow-auto rounded border border-neutral-800 bg-neutral-950 p-3 text-xs leading-5 text-neutral-400">
              {diff?.raw || "No unstaged diff."}
            </pre>
          </div>
        </aside>
      </div>

      {error && <p className="mt-4 rounded border border-red-900/60 bg-red-950/40 px-3 py-2 text-sm text-red-200">{error}</p>}
    </section>
  );
}
