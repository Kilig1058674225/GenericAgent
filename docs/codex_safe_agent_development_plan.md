# GenericAgent Safe Agent Development Plan

## Goal

Turn GenericAgent into a safer, more reliable personal agent runtime that can be deployed locally, iterated on in this fork, and verified with repeatable smoke tests before each push.

Primary branch:

- `codex/safe-agent-foundation`

Remotes:

- `origin`: `https://github.com/Kilig1058674225/GenericAgent.git`
- `upstream`: `https://github.com/lsdefine/GenericAgent.git`

## Current Deployment Baseline

- Use Python 3.12 in `.venv`.
- Install with `uv pip install -e ".[ui]"`.
- Run Streamlit UI with:

```powershell
.\.venv\Scripts\python.exe -m streamlit run frontends\stapp.py --server.port 18510 --server.address 127.0.0.1 --server.headless true --client.toolbarMode viewer
```

- Open `http://127.0.0.1:18510`.
- Local model config can stay in ignored `mykey.py`; deployment can also use environment variables without writing secrets to disk.
- Do not commit API keys, cookies, model response logs, memory generated during experiments, or local task outputs.

Environment-only model config for OpenAI-compatible endpoints:

```powershell
$env:GENERICAGENT_API_BASE="https://api.openai.com/v1"
$env:GENERICAGENT_API_KEY="<secret>"
$env:GENERICAGENT_MODEL="<model>"
.\.venv\Scripts\python.exe -m ga_cli doctor
```

Optional tuning env vars include `GENERICAGENT_NAME`, `GENERICAGENT_API_MODE`, `GENERICAGENT_REASONING_EFFORT`, `GENERICAGENT_MAX_TOKENS`, `GENERICAGENT_TEMPERATURE`, and `GENERICAGENT_CONTEXT_WIN`.

## Phase 1: Safety Foundation

Add an explicit permission layer before risky tool execution.

- Define permission categories: file read, file write, command execution, browser control, credential access, network access, ADB/mobile control, messaging, payment or purchase flow.
- Add a central policy module that can classify tool calls from `agent_loop.py` before dispatch.
- Default policy:
  - allow low-risk read operations inside the workspace;
  - require confirmation for writes outside temp/workspace;
  - require confirmation for shell execution, browser actions on logged-in sites, messaging, ADB, and credential access;
  - block payment/purchase actions unless explicitly enabled for that task.
- Ensure policy decisions are logged to a local audit log under ignored `temp/`.
- Keep the first version local-only; no cloud policy service.
- Confirmation-grade actions use a one-time `GA_POLICY_CONFIRM_TOKEN` that only matches the exact tool, policy decision, and arguments; users should not need to disable the whole policy to resume one paused action.

Acceptance:

- A risky shell command is paused or denied before execution.
- Safe read-only tasks still run without extra prompts.
- Audit log records timestamp, tool name, risk level, decision, and sanitized arguments.

## Phase 2: Execution Timeline And Auditability

Make agent behavior inspectable.

- Add a structured event log for every task: user prompt, turns, model name, tool calls, policy decisions, outputs, errors, and final status.
- Add a small timeline viewer in the Streamlit UI.
- Store logs as JSONL under `temp/runs/`.
- Redact API keys, bearer tokens, cookies, and obvious secret patterns before writing.

Acceptance:

- After a task, the UI can show what happened without reading raw model logs.
- Logs do not contain configured API keys.
- A failed task shows the error and the last safe step.

## Phase 3: Skill Registry

Make self-evolved skills maintainable.

- Introduce a registry file under an ignored or user-owned data path, initially `memory/skill_registry.json`.
- Track for each skill: id, title, description, source file/path, required permissions, dependencies, last verified time, success/failure counts, enabled flag.
- Add CLI commands or Streamlit controls to list, enable/disable, and validate skills.
- Do not rewrite existing skill generation in this phase; wrap and index it.

Acceptance:

- Existing skills can be discovered and listed.
- Disabled skills are not selected automatically.
- A validation command can run a dry or lightweight check.

## Phase 4: Safer Workspace And Rollback

Reduce damage from autonomous edits.

- Route code-writing tasks into an explicit workspace root.
- For repo edits, create a pre-task git snapshot or require a clean/known worktree state.
- Show a diff summary before applying risky edits when policy requires approval.
- Add a rollback command for task-generated file changes where feasible.

Acceptance:

- A file-writing task produces a diff/audit entry.
- User can identify and revert changes from one task.
- The agent refuses ambiguous destructive paths by default.

## Phase 5: Reliability And Windows Polish

Make the local developer loop stable on this machine.

- Fix CLI output encoding on Windows so `ga list` renders readable Chinese/English.
- Add a `doctor` command that checks Python version, dependencies, model config presence, Git remotes, ignored secret files, and Streamlit port availability.
- Add smoke tests for:
  - imports;
  - model config loading without revealing secrets;
  - Streamlit app boot;
  - permission classifier;
  - audit log redaction;
  - skill registry read/write.

Acceptance:

- `ga doctor` reports actionable status.
- `ga list` is readable in PowerShell.
- All smoke tests pass before pushes.

## Phase 6: Model Routing

Support stable model usage without locking the runtime to one provider.

- Keep current `mykey.py` compatibility.
- Add optional env-based config helpers for OpenAI-compatible endpoints:
  - `GENERICAGENT_API_BASE`
  - `GENERICAGENT_API_KEY`
  - `GENERICAGENT_MODEL`
- Add routing metadata so future tasks can select planning, coding, cheap summarization, or vision models.
- Do not commit provider credentials.

Acceptance:

- The agent can start with only environment variables plus ignored local config.
- Model names and API base can be shown in UI, but keys are never displayed.

## Verification Before Each Push

Run:

```powershell
git status --short
.\.venv\Scripts\python.exe -m ga_cli verify
.\.venv\Scripts\python.exe -c "import agent_loop; print('agent_loop import OK')"
.\.venv\Scripts\python.exe -c "from agentmain import GeneraticAgent; a=GeneraticAgent(); print(a.list_llms())"
```

For UI:

```powershell
.\.venv\Scripts\python.exe -m streamlit run frontends\stapp.py --server.port 18510 --server.address 127.0.0.1 --server.headless true --client.toolbarMode viewer
```

Then open `http://127.0.0.1:18510` and verify:

- page loads;
- LLM dropdown is populated;
- console has no frontend errors;
- task input is visible.

For real model calls, inject the key via local process environment only. Do not write it into tracked files or terminal transcripts intended for sharing.

## First 5-6 Hour Goal Run

Recommended execution order:

1. Implement Phase 5 doctor command first, because it improves every later loop.
2. Fix Windows CLI encoding and verify in PowerShell.
3. Implement the policy classifier with tests.
4. Wire policy checks into tool dispatch in observe-only mode.
5. Add audit JSONL logging with redaction.
6. Turn on blocking/confirmation for the highest-risk tools.
7. Run UI boot check and a small safe task.
8. Commit and push small, reviewable changes to `codex/safe-agent-foundation`.

Stop criteria:

- local UI still boots;
- smoke tests pass;
- no secrets in `git diff`, `git status`, or generated tracked files;
- pushed branch is available on the fork.
