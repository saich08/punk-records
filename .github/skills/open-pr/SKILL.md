---
name: open-pr
description: "Use when asked to open, create, or raise a pull request for a selected repository. Commits pending work and opens a PR whose title follows Conventional Commits (feat(), fix(), docs(), etc.)."
---

# Open a pull request

## Select the repository

- Use the repository the user names. If none is named and several workspace
  repositories are available, ask which one with `ask_user`; otherwise use the
  current working directory's repository.
- Run every git command with `git -C <repo-path>` and confirm it is a git
  repository with an `origin` remote on GitHub.

## Inspect the changes

1. Run `git -C <repo> status --short` and
   `git -C <repo> --no-pager diff` (plus `--staged`) to see pending work.
2. Determine the base branch from `origin/HEAD`
   (`git -C <repo> symbolic-ref --short refs/remotes/origin/HEAD`), falling
   back to `main`.
3. Run `git -C <repo> --no-pager log --oneline <base>..HEAD` to see commits
   already on the branch.
4. If there are no pending changes and no commits ahead of the base, stop and
   tell the user there is nothing to open a PR for.

## Write the Conventional Commit title

Format: `<type>(<scope>): <summary>`, e.g. `feat(punk-cli): add config command`.

| Type       | Use for                                               |
| ---------- | ----------------------------------------------------- |
| `feat`     | a new user-facing feature                             |
| `fix`      | a bug fix                                             |
| `docs`     | documentation only                                    |
| `style`    | formatting with no behavior change                    |
| `refactor` | code restructuring with no behavior change            |
| `perf`     | performance improvements                              |
| `test`     | adding or fixing tests                                |
| `build`    | build system, packaging, or dependencies              |
| `ci`       | CI configuration                                      |
| `chore`    | maintenance that fits no other type (e.g. skills)     |
| `revert`   | reverting a previous commit                           |

- Pick the type from the dominant change; if changes are unrelated, suggest
  separate PRs instead of one mixed PR.
- Scope is the affected component, usually the top-level tool or directory
  (e.g. `punk-cli`, `skills`). Omit `(<scope>)` if no single scope fits.
- Summary: imperative mood, lowercase start, no trailing period, at most ~72
  characters for the whole title.
- Append `!` after the type/scope (e.g. `feat(api)!:`) and add a
  `BREAKING CHANGE:` footer for breaking changes.
- If the user supplied a type or title, use it as given.

## Create the branch and commit

1. If on the base branch, create a new branch named `<github-user>/<short-topic>`
   (e.g. `saich08/punk-cli-config`). Otherwise reuse the current branch.
2. Stage only files relevant to the change; never stage secrets, `.venv/`,
   `build/`, `dist/`, or other generated output.
3. Commit with the Conventional Commit title as the subject, a short body
   explaining what and why if useful, and the trailer:

   ```text
   Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
   ```

4. Push with `git -C <repo> push -u origin <branch>`. Never force-push unless
   the user explicitly asks.

## Open the PR

Write a body with these sections:

```markdown
## Summary
<one or two sentences on what changed and why>

## Changes
- <bullet per notable change>

## Testing
- <commands run and results, or "Not tested" with reason>
```

Then open the PR against the base branch, using the first available method:

1. GitHub CLI, if `gh` is installed and authenticated (`gh auth status`):

   ```sh
   gh pr create --repo <owner>/<repo> --base <base> --head <branch> \
     --title "<title>" --body-file <body-file>
   ```

   Write the body to a temporary file in the session folder and delete it
   afterwards.
2. A GitHub MCP pull-request creation tool, if one is available.
3. Otherwise, give the user a prefilled compare link and the title and body to
   paste:
   `https://github.com/<owner>/<repo>/compare/<base>...<branch>?expand=1`

## Report

Tell the user the repository, branch, PR title, and PR URL (or compare link).
Register a created PR with `add_artifact_or_reference` as a `pullRequest`
artifact.
