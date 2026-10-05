# LLMthon specification

Status: proposed v0.1 design; milestone 1 contracts/comparison and milestone 2's bounded strict Requesty predictor are implemented. Reference execution and benchmark reporting remain future work. Normative words describe acceptance criteria.

## Milestone 2: strict Requesty prediction

The initial prediction prompt targets **CPython 3.13.5**. This identifies the requested prediction profile; no reference interpreter is invoked or verified by the predictor.

The only provider is Requesty's OpenAI-compatible Chat Completions endpoint, `https://router.requesty.ai/v1/chat/completions`. Each invocation must choose exactly one of `openai/gpt-6-luna` or `openai/gpt-6-luna:flex`. These IDs come from the exact Requesty model catalog pages, which describe each listed deployment as direct with no routing or failover. Requesty's generic FAQ and quickstart describe automatic fallback generally; this integration records that conflicting wording as a limitation, uses no policy ID or alias, and does not retry or switch provider/model. This is not a claim about Requesty's internal infrastructure.

The dated preflight schedule is $0.10 input / $0.50 output per million tokens for Luna and $0.05 / $0.25 for Luna Flex, with a 5% PAYG margin. The catalog prices are a reference estimate, not fixed provider pricing. The Luna page labels its rates updated October 3, 2026; the Luna Flex page currently labels its rates updated October 2, 2026. Both show the rates used here. If rates are unavailable in code/configuration, preflight must fail closed. The user supplies a positive finite per-invocation USD cap; the local maximum estimate must not exceed it. No provider-enforced per-request cap is claimed; the check is local only.

Input is bounded to 262,144 UTF-8 bytes. Offline token preflight uses a ceiling of one token per UTF-8 byte in the fixed prompt and source, plus 1,024 tokens reserved for chat framing. This ceiling and reservation are conservative bounds, not tokenizer counts. A positive finite timeout is required. The requested context limit cannot exceed 1,100,000 tokens, output limit cannot exceed 128,000 tokens, and the local input bound plus output limit must fit the requested context limit. The request makes one transport attempt only. Redirects, retries, model switching, and provider switching are not used.

Source reaches Requesty only when the caller supplies explicit `--send-to-provider` opt-in. `REQUESTY_API_KEY` is read at runtime only for that opted-in CLI invocation and is never printed or persisted. The adapter sends no tools. It requires one assistant choice with a normal stop reason and one JSON object whose strict prediction validates against the v1 contract. Refusals, truncation, malformed JSON, duplicate object keys, extra prose, and wrong structures are invalid responses; transport/HTTP failures are provider failures. Both are separate from predicted Python exceptions. Requesty usage token counts and `usage.cost` are captured when present; missing values are null. Raw response bytes are kept only when the caller opts in to response retention. No source or raw response is written by default.

## Purpose and scope

Provide an amusing but measurable Python execution predictor and a differential benchmark. The initial unit is one self-contained UTF-8 `.py` file, evaluated as a script in a fresh process by the reference and predicted in one stateless model request. Version one excludes imports outside an explicit standard-library allowlist, network access, subprocesses, arbitrary filesystem access, packages, stdin, interactive sessions, and bytecode.

The initial corpus should need no imports. An allowlist is a scope restriction, not a security sandbox. Enforcing isolation belongs to the reference runner's execution environment.

## Input and reference profile

Each case has a stable identifier, source hash, source text, mode, and reference profile. The profile records implementation and exact version, operating environment, encoding, locale, timezone, working-directory policy, environment allowlist, argv, empty stdin, hash seed, and resource limits. Unsupported requirements make a case ineligible rather than silently changing its meaning.

The harness records the actual executable's reported implementation/version and rejects a mismatch with the declared profile. CPython is the first oracle; comparisons with other runtimes are separate runs under their own compatible profiles. An oracle is the observed result for that environment, not a universal definition of every implementation's output.

## Prediction envelope

The future machine-readable response uses a versioned JSON object with these required fields:

| Field | Meaning |
| --- | --- |
| `schema_version` | Initially `1` |
| `mode` | `strict` or `vibes` |
| `original` | Predicted outcome of unchanged source |
| `improvised` | `null` in strict; separate predicted repaired outcome in vibes |
| `repairs` | Empty array in strict; textual repair descriptions in vibes |

Each outcome also includes `exit_code`: an integer for `completed` or `exception`, and null for `nonterminating` or `unknown`. Intentional `SystemExit` is `completed` with its actual process exit code, not an unhandled exception. Each outcome contains `termination` (`completed`, `exception`, `nonterminating`, or `unknown`), `stdout` and `stderr` as strings, and `exception_type` as a qualified type string or `null`. Exception type is required for `exception` and must be null otherwise. A syntax error is a predicted program exception. `unknown` is an abstention, not success. Nontermination is a prediction, not proof.

Vibes requires an improvised outcome and repairs array, possibly empty if it predicts no repairs. The improvised outcome is hypothetical and must never replace the original in fidelity scoring. Initially repairs are descriptive; replaying or verifying repaired source is out of scope.

Provider timeouts, transport failures, refusals, invalid JSON, extra prose, invalid field combinations, and output-limit exhaustion are harness-level failures, not Python exceptions. Validate responses without executing them. A schema implementation and fixtures are required in milestone one before any provider integration.

The versioned machine-readable contracts are published under `src/llmthon/schemas/v1/` as JSON Schema Draft 2020-12 documents. Contract checks must reject unknown fields and unsupported schema versions. A run record represents one attempt and retains its reference profile and reproducibility/cost metadata; unknown token usage or cost is `null`, never zero. Malformed provider content is recorded as an invalid response without coercing it into a prediction.

## Reference observations

Record raw stdout/stderr bytes, return code, elapsed time, timeout/signal/resource-limit status, and exception type when obtained reliably. Use an explicit reference wrapper/protocol whose control channel is separate from program stdout/stderr. Handle syntax errors and runtime exceptions, distinguish intentional `SystemExit` (including nonzero exit codes) from unhandled exceptions, preserve script execution semantics, and test that the wrapper does not alter observable output. If exception extraction is unavailable or ambiguous, report it as unavailable; do not guess from arbitrary stderr text.

For JSON serialization in version 1, raw stdout and stderr are base64-encoded fields and decoded back to bytes for comparison. An observation carries its termination, return code, optional exception type, limit-event kind, and eligibility/exclusion reason. An exception observation may have a null exception type when reliable extraction was unavailable.

A killed or timed-out reference process is an observed limit event. It does not establish mathematical nontermination. Reference infrastructure failures must be distinguished from program failures and excluded from correctness denominators, with counts disclosed.

An observation with `termination: "unknown"` and no `limit_event` is ineligible and must carry an `exclusion_reason`; it cannot enter ordinary accuracy denominators.

## Comparison and reporting

For the initial UTF-8 text corpus, encode predicted strings as UTF-8 and compare with raw captured bytes without stripping whitespace or normalizing newlines. Non-UTF-8 output is outside the initial scope and is ineligible with a recorded reason.

Report stdout match, stderr match, termination/exit-code match, exception-type match when available, and full observable exact match. Full match requires all applicable components and a normally observed completion/exception; missing exception metadata prevents full-match scoring for exceptions. Traceback differences count as stderr mismatches; a correctly predicted exception can still earn its independent component score. Do not infer exact fidelity from exception type alone.

For eligible, normally observed reference cases, every planned model attempt stays in the accuracy denominator: invalid responses, provider failures, and abstentions are unsuccessful attempts and reported separately. Attempt-failure counts cover all planned attempts, including attempts paired with excluded, limit-event, or non-UTF-8 observations; those observations remain outside the accuracy denominator. Report coverage and exclusions. Timeouts/resource limits use a separate limit-event table and are excluded from ordinary full-match accuracy; report nontermination predictions separately without labeling them proven correct.

The offline comparator scores the original outcome only, including for vibes predictions. It returns numerator/denominator counts and rates for each applicable component, a full exact-match count and rate, attempt-failure counts, exclusion reasons, and separate limit-event counts. Non-UTF-8 observations are excluded with the reason `non_utf8_output` under the initial UTF-8 corpus contract.

Record model identity, provider, prompt template/hash, decoding settings, context/output limits, seed when supported, repetition index, source hash, reference profile, run identifier, latency, token usage when supplied, and cost with currency/pricing provenance when known. Missing usage/cost is unknown, never zero. Cache hits are disclosed and separated from fresh-request latency. Repetitions are separate attempts; never select only the best result. No numerical semantic-similarity score in v0.1: exactness and component matches are easier to interpret.

## Boundaries

Source, comments, docstrings, and model responses are untrusted data. Embedded instructions cannot change mode, scoring, disclosure, or tool privileges. The predictor has no execution tools or access to reference observations/expected answers before its response is finalized. Model training contamination cannot be ruled out; include newly generated deterministic cases and disclose corpus provenance.

Reference execution requires explicit opt-in and a configured OS-level isolated runner, with no network, no credentials, read-only input, disposable writable storage, nonprivileged identity, and CPU/time/memory/process/output limits. A timeout or subprocess alone is not a sandbox. The runner fails closed if isolation is unavailable. Never run arbitrary submitted programs directly on the developer host.

Select remote providers explicitly, disclose source transmission, and keep credentials out of logs and artifacts. Record replayable metadata and raw responses with opt-in retention; do not persist submitted private source or sensitive output by default. Set per-run request/token/spend caps; never silently retry paid requests or switch providers.

## Future experiments

Package/module entry points require a manifest with an explicit script or `python -m package` equivalent; `__init__.py` is not a generic application entry point. Multi-file inputs require dependency and source-disclosure rules. Bytecode requires a pinned implementation/version and trusted decoding strategy; never deserialize arbitrary `.pyc` data on the host. Persistent sessions require an explicit state and reset contract. Selected-variable comparison needs a safe, typed serialization design before introduction.
