# LLMthon

A Python interpreter powered by predictions and audacity.

LLMthon is an experimental Python execution simulator: an LLM receives Python source and predicts what running it would produce. A companion differential benchmark compares those predictions with actual Python runtimes. The joke is the premise; execution fidelity is the research question.

**Status: milestone 1 contracts and offline comparator are implemented.** There is no runtime, CLI, provider integration, or benchmark runner. The contracts do not execute case source.

## Two modes

- **Strict:** predict the declared reference runtime faithfully, including bugs, exceptions, output, and nontermination when recognizable. Do not silently repair code.
- **Vibes:** report the predicted original outcome and a separate improvised outcome, with explicit repair descriptions. Original behaviour remains independently scoreable.

```sh
# Proposed future commands; not implemented yet.
llmthon predict examples/mutable_default.py --mode strict
llmthon predict examples/mutable_default.py --mode vibes
llmthon benchmark benchmarks/cases --reference cpython
```

## Offline development

Requires Python 3.11 or newer. No install step is needed for offline development and the package has no runtime dependencies; run it directly from the source tree:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

The version 1 JSON Schemas live in [`src/llmthon/schemas/v1/`](src/llmthon/schemas/v1/). The standard-library contract checks and pure comparator are in `src/llmthon/`. Fixtures and tests are offline; they do not call a model or execute fixture source.

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
