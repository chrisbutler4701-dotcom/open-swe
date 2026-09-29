# Files

- [Authentication, Credentials, and Security Boundaries](auth-and-security.md) - Dashboard authentication, identity gates, credential scope, webhook verification, and sandbox GitHub secret boundaries in Open SWE.
- [Models, Profiles, and Instructions](models-profiles-instructions.md) - Explains how workspace, profile, thread, routing, and provider configuration selects models for an agent run, and how repository and personal instructions enter the prompt.
- [Threads, Run State, and Durable Dispatch](threads-and-state.md) - How Open SWE derives durable LangGraph thread identities, normalizes each run input, dispatches interruptible checkpointed runs, and separates thread metadata from Store records.
- [Tool Surfaces and Authorization](tools.md) - How Open SWE assembles graph-specific tool surfaces, defers MCP integrations, scopes personal credentials, and applies contextual and tool-side safeguards to mutations.
