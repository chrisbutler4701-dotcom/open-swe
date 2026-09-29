# Files

- [Coding Agent Assembly](agent-graph.md) - How Open SWE assembles the primary Deep Agent for an executable thread run, from tolerant run configuration through sandbox, model, context, tools, subagent, and durable preparation state.
- [Agent Middleware and Failure Boundaries](middleware-stack.md) - The ordered middleware envelopes around the coding agent and reviewer loops, including preparation, tool and delivery policy, follow-up delivery, model recovery, and completion guarantees.
- [Runtime and Product Architecture](overview.md) - How LangGraph graph factories, the FastAPI ingress application, durable dispatch, thread-scoped execution context, and cloud and desktop clients fit together.
- [Reviewer, Review Scout, and Style Analyzer](reviewer-and-analyzer.md) - Architecture of the read-only pull-request reviewer, its walkthrough-producing review scout, and the analyzer that persists repository-specific review guidance. Covers durable findings, publication and reconciliation, scout lifecycle, and continual style learning.
- [Thread Sandbox Lifecycle](sandbox-lifecycle.md) - Defines how a thread persists and reuses its sandbox, including workspace provisioning, proxy-backed GitHub access, safe recovery, explicit replacement, and local-machine bridges.
