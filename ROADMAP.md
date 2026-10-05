# Roadmap

Milestone 1 contracts and offline comparison are implemented. Unchecked items are planned; no implementation completion is implied.

## 0 — Agree on the experiment

- [x] Describe strict prediction, vibes repairs, and differential benchmarking.
- [x] Establish scope, trust boundaries, comparison rules, and repository layout.
- [x] Choose the initial exact CPython version and one model/provider (CPython 3.13.5; Requesty direct deployment IDs).

## 1 — Contract before inference

- [x] Implement versioned case, prediction, observation, and run-record schemas.
- [x] Add fixtures for valid modes, exceptions, abstention, malformed output, and provider failures.
- [x] Implement a pure comparison function with byte-exact and component scores.
- [x] Test whitespace, traceback mismatch, missing metadata, denominators, unknown-observation exclusions, and limit events.

Gate: offline schema/comparator tests pass with no network, model requests, or submitted-code execution. Verified with the documented `PYTHONPATH=src python3 -m unittest discover -s tests -v` command on 2026-10-04.

## 2 — One strict predictor

- [x] Add one explicitly selected provider adapter, prompt template, and `predict` command.
- [x] Enforce response validation, request timeout, context/output limits, and local request/spend preflight.
- [x] Add injectable mock transport for offline tests and opt-in response retention.
- [x] Preserve raw responses only by opt-in and distinguish abstention from provider failure.

Gate: source-to-validated-prediction works; no execution tools; real requests are explicit and bounded. Verified with mocked offline tests and static checks on 2026-10-05; no live provider request was made. The spend check is a local estimate, not a provider-enforced cap.

## 3 — One isolated oracle

- [ ] Select and document an OS-level isolation backend; fail closed when unavailable.
- [ ] Pin and verify the reference profile and capture stdout/stderr independently of control metadata.
- [ ] Test normal exit, syntax/runtime exception, infinite loop, excessive output, signals, and resource limits.
- [ ] Verify script semantics and prevention of network, credential, and host-filesystem access.

Gate: isolation and capture tests pass before accepting arbitrary input. No host-execution fallback.

## 4 — Small reproducible benchmark

- [ ] Add original deterministic cases: mutable defaults, aliasing, evaluation order, closures, exceptions, and numeric behaviour.
- [ ] Run the predictor before exposing oracle results; record provenance and repetitions.
- [ ] Export a machine-readable report and readable summary with exact/component scores, failures, coverage, latency, and known costs.

Gate: a clean rerun reproduces reference observations and explains every denominator; publish measured results with model/profile metadata.

## 5 — Vibes and compatible runtimes

- [ ] Add separately reported hypothetical repairs and strict/original fidelity comparisons.
- [ ] Add a compatible PyPy adapter with explicit profile differences and skips.
- [ ] Assess Jython as a separate language/version track before committing to support.

Gate: repairs cannot improve the original-fidelity score; cross-runtime differences remain visible.

## Later, only if useful

Multi-file packages and module entry points; bytecode prediction; persistent REPL/virtual state; safely serialized selected variables; broader corpora and model comparisons. Each requires a scoped spec update and evidence that the additional complexity serves the experiment.
