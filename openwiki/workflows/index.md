# Files

- [Context Engineering and Prompt Assembly](context-engineering.md) - How inbound identities and conversation data become safe structured model context, then combine with workspace and repository instructions, scoped conventions, recent context, and virtual skills.
- [Follow-up Messages, Interrupts, and Queue Drain](follow-up-messages.md) - How Open SWE schedules follow-up work on a durable thread, injects data into a live run, drains deferred messages safely, and handles Slack and dashboard stops.
- [Inbound Invocation to Durable Run](invocation.md) - How dashboard, desktop, GitHub, Slack, Linear, schedules, and automation inputs are authenticated, normalized, routed to durable LangGraph threads and runs, streamed, and completed.
- [Pull Request Creation and Approval](pr-creation.md) - How coding agents push branches, create attributed GitHub pull requests, obtain approval for workflow-file changes, and connect pull requests to review, CI, and baby-sit follow-up.
- [Pull Request Review Workflow](pr-review.md) - How Open SWE admits pull-request reviews, runs the dedicated reviewer graph, persists and publishes findings, and keeps reviews synchronized across pushes, replies, and GitHub status checks.
- [Schedules, Background Tasks, and Baby-Sit](scheduling-and-baby-sit.md) - Model-free scheduler routing for durable agent schedules, delayed maintenance work, workspace refreshes, background command monitoring, feedback prompts, and opt-in pull-request CI watches.
