---
name: implement-module
description: Implement or close out exactly one module (M0-M9) of the minimum-coding-agent-mvp OpenSpec change. Use when the user says "实现 M0", "继续下一模块", "implement module", or asks to close out after a passed review. Enforces single-module scope, OpenSpec apply context, branch workflow, Review Gate, and D17/tasks handoff.
license: MIT
compatibility: Requires the openspec CLI and git; the change minimum-coding-agent-mvp must exist in the current checkout.
metadata:
  author: minimum-coding-agent
  version: "1.0"
---

Implement exactly one module of the `minimum-coding-agent-mvp` OpenSpec change per session, then stop at the module's Review Gate. This skill is the project-level replacement for pasting long session prompts.

**Input**: A module id `M0`-`M9` (for example `/implement-module M0`). If no module is provided:

1. Run `openspec instructions apply --change minimum-coding-agent-mvp --json`.
2. Infer the next module from `progress` and `tasks` (first section with unfinished tasks).
3. Announce the inferred module and ask the user to confirm before writing anything.

## Preflight

1. Confirm the current branch contains `openspec/changes/minimum-coding-agent-mvp` and the project skills. If not, stop and ask the user to check out the branch that contains the change (or merge it into the baseline). Never recreate or hand-edit artifacts.
2. Run `openspec instructions apply --change minimum-coding-agent-mvp --json`. Treat its `context`, `operationGuidance`, `progress`, and `tasks` as authoritative. Announce: change name, module, planned branch, progress.
3. Read:
   - `openspec/changes/minimum-coding-agent-mvp/tasks.md`, target module section only;
   - `openspec/changes/minimum-coding-agent-mvp/design.md`: D2 (module map), D13-D17, plus decisions relevant to the module;
   - the matching `openspec/changes/minimum-coding-agent-mvp/specs/<capability>/spec.md`;
   - `git status`, `git log --oneline -10`. Require a clean working tree; if dirty, stop and ask.
4. Create the module branch from the current baseline branch (normally `master` once the spec branch is merged):

| Module | Branch |
|---|---|
| M0 | `feat/m0-foundation` |
| M1 | `feat/m1-model-provider` |
| M2 | `feat/m2-tool-system` |
| M3 | `feat/m3-agent-core` |
| M4 | `feat/m4-task-planning` |
| M5 | `feat/m5-console-ui` |
| M6 | `feat/m6-extensions` |
| M7 | `feat/m7-code-intelligence` |
| M8 | `feat/m8-mcp-integration` |
| M9 | `feat/m9-integration` |

Never implement directly on the baseline branch.

## Implement (this module only)

- Execute only the checkboxes in the target module section. Do not touch later modules and do not refactor unrelated code.
- Keep tests and documentation for this module in the same change set; do not defer them to a later module.
- Follow project rules: English code/identifiers, Chinese README/docs/OpenSpec artifacts, Google Style docstrings on public APIs, and green `ruff` + `pydoclint` + `pytest`.
- Tests must use scripted models and temporary workspaces. Never call a real model endpoint; `live` tests stay skipped.
- No TODO/FIXME placeholders and no "tests will be added later".
- Run the verification commands stated in the tasks (for example `make setup && make check`, or the module demo). If a command cannot run yet because this module introduces it, explain that in the review packet.
- If a change to another module's contract is unavoidable, stop and report it in the review packet instead of editing that module.

## Review Gate (mandatory stop)

1. Produce a review packet containing:
   - what changed and why;
   - interface or behavior changes;
   - how to run the module demo;
   - test and quality command output summary;
   - known limitations and risks;
   - suggested review focus.
2. Append a record to `design.md` under `### D17 ...`:
   - module, branch, commit range, delivered scope, deviations and reasons, decisions made, impact on later modules, leftovers.
3. Update `tasks.md`:
   - tick only ordinary tasks completed in this module;
   - do **not** tick the module's Review Gate task.
4. Stop and wait for explicit human approval. Do not start the next module, do not merge, and do not archive.

## Close-out mode (only after the user says the review passed)

1. Append the review conclusion (approved, or changes requested) to the D17 record.
2. Add newly discovered work to `tasks.md`; if a behavior contract or design decision changed, update `specs/` and/or `design.md` first, only with explicit user approval.
3. Tick the module's Review Gate task.
4. Merge the module branch into the baseline branch (normally `master`), keep the working tree clean, and do not delete the module branch unless asked.
5. Report the merge commit, `make check` result, and the D17 summary, then end the session.

## Hard rules

- One module per session. If the user asks for several modules, implement the first one only and tell them to open a new session for the next.
- Never tick a Review Gate without explicit human confirmation.
- Never modify `design.md` or `specs/` silently; behavior contract changes go through `/openspec-update-change` or explicit user approval.
- Never rely on previous session chat history. All handoff state must live in the change artifacts, code, tests, and git.
- Do not run `make test-live` unless the user explicitly provides an endpoint for this session.
