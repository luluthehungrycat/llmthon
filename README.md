# LLMthon

A Python interpreter powered by predictions and audacity.

LLMthon is an experimental Python execution simulator: an LLM receives Python source and predicts what running it would produce. A companion differential benchmark compares those predictions with actual Python runtimes. The joke is the premise; execution fidelity is the research question.

**Status: milestones 1 and 2 are implemented.** The strict predictor sends one explicitly authorized source file to Requesty and validates its prediction against the v1 contract. There is no reference runtime, code execution, or benchmark runner.

## Two modes

- **Strict:** predict the declared reference runtime faithfully, including bugs, exceptions, output, and nontermination when recognizable. Do not silently repair code.
- **Vibes:** report the predicted original outcome and a separate improvised outcome, with explicit repair descriptions. Original behaviour remains independently scoreable.

The only implemented prediction mode is strict. The initial prompt targets CPython 3.13.5. Run from the source tree with an explicitly chosen model, a required spend cap, and an explicit source-transmission opt-in:

```sh
PYTHONPATH=src python3 -m llmthon predict examples/mutable_default.py \
  --model openai/gpt-6-luna \
  --max-spend-usd 0.01 \
  --send-to-provider
```

The only accepted model IDs are `openai/gpt-6-luna` and `openai/gpt-6-luna:flex`. They are exact Requesty catalog deployment IDs, not routing policies or aliases. The Requesty catalog pages describe these deployments as direct, with no routing or failover. Requesty's generic FAQ and quickstart describe automatic fallback more broadly; that wording conflicts with the per-model pages, so this integration relies on the exact model IDs and does not claim control over Requesty's internal infrastructure. It never retries or selects another model.

Both models' catalog prices are recorded as dated estimates: $0.10/$0.50 per million input/output tokens for Luna, and $0.05/$0.25 for Luna Flex, plus the 5% Requesty PAYG margin. The preflight estimates cost using those rates and rejects a request whose estimate exceeds `--max-spend-usd`. This is a local estimate, not a provider-enforced spend cap. Prices may change. The Luna catalog page labels its rate update October 3, 2026; the Flex page currently labels its update October 2, 2026, while listing the prices recorded here. See the [Luna catalog](https://www.requesty.ai/models/openai/gpt-6-luna), [Luna Flex catalog](https://www.requesty.ai/models/openai/gpt-6-luna-flex), and [Requesty quickstart response format](https://docs.requesty.ai/quickstart).

Before an opted-in request, the CLI checks a positive finite timeout, a required positive spend cap, the catalog context/output maxima (1.1M/128K), and the requested prompt plus output against `--context-limit`. The local prompt-token bound uses UTF-8 bytes as a one-byte-per-token ceiling plus 1,024 tokens for message framing; source is limited to 256 KiB. This is a conservative offline preflight, not a tokenizer measurement. Defaults are 8,192 context tokens and 1,024 output tokens. Requesty receives the source text. Set `REQUESTY_API_KEY` in the runtime environment; the program does not print it. Use `--retain-raw-response PATH` only when raw provider response retention is wanted. Missing provider usage or cost is emitted as `null`.

## Offline development

Requires Python 3.11 or newer. No install step is needed for offline development and the package has no runtime dependencies; run it directly from the source tree:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

The version 1 JSON Schemas live in [`src/llmthon/schemas/v1/`](src/llmthon/schemas/v1/). The standard-library contract checks, pure comparator, strict Requesty adapter, and CLI are in `src/llmthon/`. Offline tests use an injected mock transport; they do not call a model or execute fixture source.

For the included mutable-default example, strict mode should predict `[1]` followed by `[1, 2]`. Producing `[1]` followed by `[2]` is a semantic error, even if it feels like better Python.

## First useful experiment

Start with self-contained UTF-8 source files and one explicitly pinned CPython version. Capture stdout, stderr, termination, and exception type; compare these with a structured model prediction. Keep model/provider failures separate from predicted program exceptions. Report exact-match rates alongside separate component scores, cost, and latency.

PyPy is a later reference adapter, limited to compatible versions and dependencies. Jython is exploratory and must use its own declared language/version profile; it is not automatically interchangeable with contemporary CPython. Bytecode, packages, persistent REPL state, and virtual filesystems are later experiments.

LLMthon must not secretly execute submitted Python to obtain its prediction. Only the benchmark reference side executes code, in an explicitly configured isolated environment. Model predictions cannot authorize host operations. Remote model providers receive submitted source; users must explicitly select that disclosure.

## Repository map

| Path | Purpose |
| --- | --- |
| `SPEC.md` | Proposed behaviour and benchmark contract |
| `ROADMAP.md` | Ordered milestones and completion gates |
| `AGENTS.md` | Instructions for coding agents |
| `src/llmthon/` | Version 1 contracts and offline comparison |
| `tests/` | Offline contract fixtures and comparator tests |
| `benchmarks/cases/` | Future deterministic benchmark corpus |
| `examples/` | Small source examples, not an execution harness |
| `docs/` | Design notes and review record |

Read the [specification](SPEC.md) before implementing and the [roadmap](ROADMAP.md) before expanding scope. There are no measured accuracy claims yet, and no guarantee that an LLM prediction matches Python.
