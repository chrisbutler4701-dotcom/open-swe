---
type: contributor guide
title: Open SWE Codebase Guide
description: Start here to set up Open SWE, identify the public entrypoint and owner for a safe change, and select focused validation. Links route contributors to the detailed architecture, workflow, integration, operations, and testing guides.
tags: [open-swe, contributor-guide, development, langgraph, testing]
sources:
  - id: openwiki-source-328bde9e94017848bb09ba23
    resource: repo://agent/api/app.py
  - id: openwiki-source-921ec88ab63280d28b3dddb5
    resource: repo://agent/chat.py
  - id: openwiki-source-c48b309c5ca416cf623f0866
    resource: repo://agent/dispatch.py
  - id: openwiki-source-f8665996049065d2172f68e2
    resource: repo://agent/graphs/agent.py
  - id: openwiki-source-f2c7a9cbc0f7af0b4db77658
    resource: repo://agent/graphs/analyzer.py
  - id: openwiki-source-368e3a3da2c40119aead4316
    resource: repo://agent/graphs/chat.py
  - id: openwiki-source-6edf3a3d0424db652805727f
    resource: repo://agent/graphs/review_scout.py
  - id: openwiki-source-73db7609f2a24f4a0ff5c32c
    resource: repo://agent/graphs/reviewer.py
  - id: openwiki-source-1116ea2d477f08cf0f5b2ef0
    resource: repo://agent/graphs/scheduler.py
  - id: openwiki-source-276ab38291eb5741b4c2141c
    resource: repo://agent/reviewer.py
  - id: openwiki-source-3e15117ace082a39e1f130d8
    resource: repo://agent/scheduler.py
  - id: openwiki-source-856ade03ef31ac38e1347f7c
    resource: repo://agent/server.py
  - id: openwiki-source-3096620cfd0eb1bae6d9e78c
    resource: repo://agent/webapp.py
  - id: openwiki-source-8037e2358a2c4f9b2c722a11
    resource: repo://AGENTS.md
  - id: openwiki-source-19973c87ca458faa5d03fecc
    resource: repo://docs/DEVELOPMENT.md
  - id: openwiki-source-5bbba7b2a8ea8360ff233d63
    resource: repo://langgraph.json
  - id: openwiki-source-012f2c78e3b1446dfc35803f
    resource: repo://Makefile
  - id: openwiki-source-5b54a58d1b51cd490b0e7162
    resource: repo://package.json
  - id: openwiki-source-05ccef8d4cf1698187f20464
    resource: repo://pyproject.toml
  - id: openwiki-source-23775c3de52f3ab95a13cb8b
    resource: repo://README.md
  - id: openwiki-source-f0a6e7dc03522b2682f88655
    resource: repo://tests/conftest.py
  - id: openwiki-source-859f98720585f4648f0f7b2e
    resource: repo://tests/e2e/playwright.config.ts
  - id: openwiki-source-4b944ec14a3d793a6f771403
    resource: repo://tests/e2e/playwright.desktop.config.ts
  - id: openwiki-source-7ef60dc4372e1a33c7728fe6
    resource: repo://tests/e2e/README.md
generated: { by: "openwiki/0.4.2", at: "2026-09-29T08:16:15.658Z" }
verified:
  - by: openwiki/0.4.2
    at: 2026-09-29T08:16:15.658Z
---

# Open SWE Codebase Guide

Open SWE is an asynchronous coding agent and software factory. It runs coding work in an isolated sandbox per thread, with separate read-only reviewer, review-scout, and review-style analyzer graphs. Use this page to find the narrow owner and workflow before changing code; source and focused tests remain authoritative.

## Local loop

Use Python 3.14+ and `uv` for the backend. The `ui`, `desktop`, and `tests/e2e` workspace uses Node 22.22.2+ and `pnpm`.

```bash
make install            # uv sync --extra dev
make build-dashboard    # build ui/.output/public
make dev                # LangGraph graphs, FastAPI, and built dashboard on :2024
make dev-ui             # Vite on :3000 plus the backend on :2024
make run                # FastAPI only on :8000
make desktop            # Electron; start the backend separately
```

`make dev` starts a loopback PostgreSQL container unless `POSTGRES_URI` is set, rejects an occupied port 2024, and serves the registered graphs and HTTP app. Use it for any change that creates or executes a LangGraph run. `make run` does not include the LangGraph runtime, so run creation cannot work there. See [Development, Deployment, and Packaging](operations/deployment.md) for worktrees, UI/desktop packaging, and deployment; see [Configuration and Startup Validation](operations/configuration.md) before adding settings or credentials.

For local GitHub or Slack webhooks, use `make tunnel NGROK_DOMAIN=<name>.ngrok-free.dev`. Its supplied traffic policy exposes only `/webhooks/*`; do not publish the unauthenticated LangGraph development API. Follow `docs/DEVELOPMENT.md` for the ordered app, credential, database, and tunnel setup.

**Repository conventions that affect a safe change**

- Implement async paths only. If an interface mandates a synchronous method, raise `NotImplementedError` rather than maintain a second implementation.
- Keep strong Python and TypeScript types; do not use `Any` or `any` to suppress a type error. Use absolute imports except for same-package imports, and do not discard exceptions without propagating or logging them.
- Put model-facing prompts in `agent/resources/prompts/` and load them through `prompt(...)`; route new dashboard endpoints through the feature package that owns them, not the aggregate router.

## Public entrypoints and ownership

`langgraph.json` is the deployed registration boundary. It registers six graph entrypoints and `agent.webapp:app`; each graph entrypoint is a thin `agent/graphs/` re-export, so normally change its implementation rather than the shim.

| Entrypoint | Owner | Route to |
| --- | --- | --- |
| `agent.graphs.agent:traced_agent` | `agent/server.py` | [Coding Agent Assembly](architecture/agent-graph.md), then [Agent Middleware and Failure Boundaries](architecture/middleware-stack.md) for order-sensitive behavior. |
| `agent.graphs.reviewer:traced_reviewer_agent` | `agent/reviewer.py` | [Reviewer, Review Scout, and Style Analyzer](architecture/reviewer-and-analyzer.md) and [Pull Request Review Workflow](workflows/pr-review.md). |
| `agent.graphs.analyzer:traced_analyzer` | `agent/analyzer.py` | [Reviewer, Review Scout, and Style Analyzer](architecture/reviewer-and-analyzer.md). |
| `agent.graphs.review_scout:traced_review_scout` | `agent/review_scout/graph.py` | [Reviewer, Review Scout, and Style Analyzer](architecture/reviewer-and-analyzer.md). |
| `agent.graphs.chat:traced_chat_agent` | `agent/chat.py` | PR-chat handling in [Dashboard and Desktop Clients](integrations/dashboard-ui.md) and the review architecture guide. |
| `agent.graphs.scheduler:get_scheduler` | `agent/scheduler.py` | [Schedules, Background Tasks, and Baby-Sit](workflows/scheduling-and-baby-sit.md). |
| `agent.webapp:app` | `agent/api/app.py` | [Runtime and Product Architecture](architecture/overview.md), [Inbound Invocation to Durable Run](workflows/invocation.md), or [Dashboard and Desktop Clients](integrations/dashboard-ui.md). |

```mermaid
flowchart LR
    Ingress["Dashboard GitHub Slack Linear"] --> API["FastAPI routers"]
    API --> Dispatch["durable run dispatch"]
    Dispatch --> Graph["agent or reviewer graph"]
    Tick["Cron tick"] --> Scheduler["scheduler graph"]
    Scheduler --> Graph
```

This shows the primary routing boundary: interactive ingress creates durable graph work, while a cron invocation first selects maintenance work or a scheduled coding run.

The FastAPI lifespan pins the event loop; validates login allowlists, sandbox configuration, local model configuration, and database configuration; migrates the database; then starts best-effort analytics, transcript, and bridge listeners. The composition function adds dashboard, plan, workflow-approval, Linear, Slack, health, GitHub webhook, and sandbox-tool routers and mounts the dashboard UI. Credentialed CORS is enabled only for explicitly configured origins and rejects `*`.

## Change-routing map

### Agent, state, and sandbox

- Change graph construction, model/profile resolution, skills, tools, or prompts: [Coding Agent Assembly](architecture/agent-graph.md), [Models, Profiles, and Instructions](concepts/models-profiles-instructions.md), and [Tool Surfaces and Authorization](concepts/tools.md).
- Change queueing, errors, timeouts, model fallbacks, push guards, or tool availability: [Agent Middleware and Failure Boundaries](architecture/middleware-stack.md).
- Change sandbox creation, reconnect/recreate behavior, provider registration, checkout state, or proxy credentials: [Thread Sandbox Lifecycle](architecture/sandbox-lifecycle.md) and [Sandbox Provider Integrations](integrations/sandbox-providers.md). Do not silently replace an unreachable coding sandbox: it can contain uncommitted work. The reviewer may recreate its checkout because it prepares a fresh review workspace.
- Change thread identity, persisted run input/configuration, interrupts, or durable state: [Threads, Run State, and Durable Dispatch](concepts/threads-and-state.md) and [Follow-up Messages, Interrupts, and Queue Drain](workflows/follow-up-messages.md).

The main agent factory is stateless; per-thread continuity belongs in its sandbox and thread metadata. `dispatch_agent_run` is the common dashboard, Slack, Linear, and GitHub contract for `agent` or `reviewer` runs. It defaults to an interrupt multitask strategy; pass either a complete prebuilt input or content/context/source identities, never both.

### Product ingress and integrations

- Change webhook admission, identity/context normalization, dispatch, streaming, or completion behavior: [Inbound Invocation to Durable Run](workflows/invocation.md).
- Change a pull request, workflow-file approval, push, or CI handoff: [Pull Request Creation and Approval](workflows/pr-creation.md).
- Change review eligibility, findings, publication, settlement, or PR chat: [Pull Request Review Workflow](workflows/pr-review.md). The reviewer has finding and publication tools but no commit, push, or PR-opening tools. PR chat is sandbox-less and read-only: it uses seeded `/pr/` virtual files and repository-scoped GitHub App access.
- Change dashboard APIs, the TanStack UI, Vite proxy, Electron, or client streaming: [Dashboard and Desktop Clients](integrations/dashboard-ui.md).
- Change OAuth, webhook signatures, roles, tokens, same-origin rules, or sandbox credential scope: [Authentication, Credentials, and Security Boundaries](concepts/auth-and-security.md).
- Change MCP, browser, observability, or third-party tool loading: [MCP, Observability, and External Tool Integrations](integrations/observability-and-mcp.md).

### Background work and operations

The scheduler has one launch node. It routes ticks to stale-run reconciliation, baby-sit evaluation, legacy-review cleanup, background-task monitoring, workspace refresh, session/thread/agent cost or feedback work, or a scheduled agent run; missing required identifiers become explicit result statuses. Start in [Schedules, Background Tasks, and Baby-Sit](workflows/scheduling-and-baby-sit.md).

The deployed checkpointer uses delete-based TTL cleanup, sweeping every 60 minutes with a default retention of 43,200 minutes. Configuration, startup checks, database requirements, and local/deployed persistence are covered by [Configuration and Startup Validation](operations/configuration.md).

## Focused validation

**Never run the full test suite locally.** Run the narrowest test owning the observable behavior, then the applicable quality check.

```bash
make test TEST_FILE=tests/github/test_open_pull_request.py
uv run pytest -vvv tests/path/to_test.py::test_name
make lint
make format-check
make typecheck
```

`make test` runs an existing file or directory through pytest; direct pytest is appropriate for a node id. Pytest uses asyncio auto mode. Shared fixtures route store access through an in-memory SDK-shaped store so production serialization is exercised, clear global caches and sandbox registries around each case, hide local bundled dashboard output, and enable automatic review by default unless a test overrides its gate.

Choose the family closest to the changed boundary—such as `tests/agent/`, `tests/middleware/`, `tests/sandbox/`, `tests/reviewer/`, `tests/webhooks/`, `tests/dashboard/`, `tests/github/`, `tests/slack/`, or `tests/tools/`. See [Focused Validation Strategy](testing/overview.md) for fixtures and frontend checks.

Use a single Playwright spec only for a real cross-boundary contract:

```bash
pnpm install --frozen-lockfile
pnpm run test:e2e:install
pnpm exec playwright test tests/full_flow.spec.ts
```

The E2E harness runs real agent code, LangGraph development server, local sandbox, local git, real dashboard, and Electron paths while faking the LLM and external SaaS HTTP boundaries. Browser tests are serial with one worker; the desktop configuration selects only `desktop.spec.ts`. The root scripts provide the browser and desktop E2E commands.
