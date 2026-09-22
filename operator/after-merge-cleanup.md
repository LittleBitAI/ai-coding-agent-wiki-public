---
scope: operator
severity: contract
triggers: ["머지", "merge", "브랜치.*정리", "정리.*브랜치"]
slots: [server_stop, scratch_dirs]
sources: []
sources_withheld: true
links: [do-the-whole-instruction, run-inside-this-session]
---

# Cleanup after a merge — before being told to

Rule. A request to merge includes the cleanup that follows it. After
confirming the merge actually landed, and before starting the next piece of
work, do all of the below. Do not seek separate approval for the cleanup and
do not push it to the next turn.

1. `git fetch origin --prune`
2. If the working folder is clean and not in use, return to `main` and
   `git pull --ff-only`. Do not switch a folder holding uncommitted changes or
   a separate review session.
3. Delete the merged local branch. After a squash merge `-d` refuses — before
   deleting, check that PR's merge commit and confirm the content is in it.
   Unmerged changes are preserved.
4. Check the remote branch (the merge has usually deleted it already).
5. Stop the server if one is up: `{server_stop}`.
   **Only what this session started.** Another project's server on the same
   machine looks identical by name and by timestamp. Tell them apart by
   command line → [[run-inside-this-session]]
6. In the merged worktree, first check for uncommitted changes, audio assets,
   runtime data, verification records and shared dependencies, and preserve
   outside the worktree whatever is needed. Remove the junction link, never
   its target. Clean up Orca worktrees through Orca, and keep the independent
   review session the user opened. Clear the scratch: `{scratch_dirs}`
7. Query local branches, remote branches and worktrees again, and report what
   was deleted and why anything was kept.

Do not treat the page existing as the step being done. Put a real merge
request through the injector and confirm this rule lands in the body.

What goes wrong. Dead branches pile up, a server sits holding the GPU, and the
next session reads stale scratch as evidence.

## Confirm before deleting

A squash-merged branch has a tip that is not an ancestor of `main`, so
`git branch -d` refuses. Before forcing it with `-D`, check the content
actually landed.

```bash
git rev-parse <branch>^{tree}
git rev-parse <that-PR-merge-commit>^{tree}
git diff --stat <branch> <that-PR-merge-commit>
```

Matching trees confirm the content is in. If they differ, review the conflict
resolution or the follow-up commits, preserve the original branch as a bundle
or similar, and then decide. Differing from the latest `main` is not by itself
grounds for calling a branch unmerged. Before deleting, check the absolute
path and what the link actually points at.
