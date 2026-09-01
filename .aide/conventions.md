# AIDE conventions

The shared contract every agent, script, and human obeys.

This file is the **index**. Each section is one file under
[`conventions/`](conventions/), so a pointer of the form `§6` resolves to
[`conventions/6-test-hygiene.md`](conventions/6-test-hygiene.md), and one of the
form `§1 → insights.md` to
[`conventions/1-format-contract/insights.md`](conventions/1-format-contract/insights.md).
Read the section you were pointed at; nothing here expects a top-to-bottom read.

| § | Section | What it governs |
|---|---|---|
| 1 | [Format contract](conventions/1-format-contract.md) | The exact shapes `aide.py` parses in `docs/aide/**`, and the rule that every durable artifact must read cold. Its own index, one file per document shape |
| 2 | [Claim protocol](conventions/2-claim-protocol.md) | How "this item is taken" is signalled between concurrent runs — the pushed claim branch, not a `🚧` on a feature branch |
| 3 | [Command hygiene](conventions/3-command-hygiene.md) | The canonical shell-command rules. Runtime-general; an adapter enforces them, it does not restate them |
| 4 | [Git modes](conventions/4-git-modes.md) | What `git.mode` changes inside `aide claim` / `aide merge`. Agent instructions are identical across modes |
| 5 | [Clarify mode](conventions/5-clarify-mode.md) | How `spec-author` resolves an ambiguous queued item under `loop.clarify` — and why the root documents sit outside it: authored via their entry point, interactively |
| 6 | [Test hygiene](conventions/6-test-hygiene.md) | Portability, and tests that can actually fail. Runtime-general, like §3 |
| 7 | [Off-platform verification](conventions/7-off-platform-verification.md) | No role in this loop sees a non-Linux checkout or real CI status; this is how to look at the gate that does |
| 8 | [Reaching into another repository](conventions/8-sibling-repos.md) | A repository's own instructions bind for work inside it |

Sections are **runtime-general**: an adapter delivers them to its own agents by
whatever mechanism it has, and never restates a rule as its own. The one page
that must bind before anything points anywhere is
[`AGENT-CONTEXT.md`](AGENT-CONTEXT.md).
