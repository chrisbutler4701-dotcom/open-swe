# OSWE-0 Lab Manager customization spike

Date: 2026-09-30  
Status: **technical spike passed; execution-budget compliance failed**

This is a proposal-only customization based on pinned upstream commit
`0b05f810491f51786d790394b6b84f57eba66773`. It is not a production deployment
recommendation.

## What this branch proves

- `lab_manager` is a registered sandbox provider with no local-provider fallback.
- Existing labs reattach by exact persisted ID; missing labs fail closed.
- Filesystem and command operations stay behind Lab Manager's bounded transport.
- A `proposal_only` Open SWE engineering profile removes controller HTTP/search,
  publication, sandbox recreation, skills, subagents, and model fallback.
- The trial invokes the exported `agent.graphs.agent:traced_agent` graph. The runner
  does not call `deepagents.create_deep_agent` directly.
- Proposal-only reconnects return to the exact bound Lab Manager ID rather than a
  desktop or local shell backend.

The passing construction path was:

```text
agent.graphs.agent:traced_agent
  -> agent.server.get_agent
  -> agent.server.build_agent(proposal_only=True)
  -> Open SWE engineering middleware
  -> LabManagerSandbox
```

## Connected evidence

- Tested branch head: `1374e84956276d1e1d6c58e73eae960f62e5a037`
- Allina adapter passing run: `run-allina-oswe-0-1790737831`
- Target repository revision: `420c867c27b533c5aa9949cebc4f491c8397f205`
- Model: `google_genai:gemini-3.5-flash-lite`
- Fallback model: disabled
- Worker duration: 18.0 seconds
- Changed path: `tests/midi/test_compiler.py` only
- Independent result: 33 targeted tests and 148 full-suite tests passed; Ruff and
  diff checks passed; Evidence v2 bundle `bundle-cbe292d50d2162dcfcfcdbe6`

The companion Allina fault probe also let a real Lab Manager create request succeed,
then dropped the response before the adapter received the lab ID. Since the observed
backend has no idempotency/discovery API, Allina returned `UNKNOWN_OUTCOME` and blocked
redispatch. Exactly one create POST occurred.

## Sanitized hashes

| Artifact | SHA-256 |
| --- | --- |
| Passing trial JSON | `97125595617833cc211d5575ad6639693dd46dd2dacd2f57bd9775262be8ed78` |
| Pre-persistence fault probe JSON | `e35c0eb565c56406040c9682ab3570fca1ed9e4ef494359fd477bf801a708565` |
| Verified MPC patch | `7c546a112ebf71b487ac09ac925b0bb1fac0ccb37c2c5e5c9cca9e4f0f7c8c6b` |
| Open SWE source/test diff from pin | `b5d509cdb9843109d183ae8acef78c7d0feb96896d9a7476127b98a576f6649b` |
| Allina source/test diff from preparation base | `756854f41539f96875895a47586bad7ce396eb3f1541e407d27046bfc3c40105` |

Detailed transcripts stay outside Git. The review package was scanned for credential
values; this document contains identities and content hashes only.

## Budget and review constraints

The task contract allowed two attempts. Nineteen trial JSON records survive: ten
preliminary direct-run records and nine Allina-run records. Technical acceptance does
not erase that budget failure. Deleted historical ledgers are unavailable unless
separately recovered.

Before any production consideration, review provider transport assumptions, async
behavior, the proposal-only tool surface, model registration, and compatibility with
current upstream. Do not enable production routing during this review.
