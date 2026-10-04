# Initial scaffold review

Historical review of the documentation-only scaffold. Milestone 1 implementation is recorded in `ROADMAP.md`; statements below describe the repository at the time of this review.

Date: 2026-10-04. Method: linus-review design/scaffold review performed by the authoring agent; this is not an independent second-model review.

## Verdict

Acceptable for a documentation-only initial commit. No remaining blockers found in the reviewed scope. This does not approve a runtime implementation, isolation backend, or measured accuracy claim.

## Findings resolved

- **VERIFIED STATICALLY:** Treating a reference timeout as proof of nontermination would mislabel results. The specification separates observed limit events from ordinary accuracy and refuses proof claims.
- **VERIFIED STATICALLY:** Dropping invalid model responses or provider failures would inflate fidelity. The specification retains every planned eligible attempt in the denominator and reports failures separately.
- **VERIFIED STATICALLY:** Combining vibes repairs with original outcomes would reward semantic changes. Separate outcomes and scoring are required.
- **VERIFIED STATICALLY:** Script exits need exit-code handling in addition to exception detection. The envelope now includes exit codes and distinguishes intentional `SystemExit` from unhandled exceptions.
- **VERIFIED STATICALLY:** Reference execution and model source disclosure cross trust boundaries. The design requires explicit selection, bounded requests, fail-closed OS isolation, no host fallback, and withheld oracle observations.

## Verification and limits

Relative Markdown links and required scaffold files were checked locally, and `git diff --cached --check` passed before commit. The mutable-default example was run with local Python and produced `[1]` then `[1, 2]`; this verifies the example only, not a pinned benchmark oracle. There is no implementation, test suite, or CI yet. Isolation, transport handling, schema validation, script-preserving exception capture, and benchmark accounting remain future milestones with explicit acceptance gates.

The initial exact CPython version, provider, packaging, license, and isolation backend remain unselected. They do not block this scaffold; they must be resolved when the corresponding implementation/distribution work starts. No license grant is implied by this commit.
