"""Command line entry point for the explicitly opted-in strict predictor."""

import argparse
import json
import os
from pathlib import Path
import sys

from .predict import (
    InvalidResponse,
    MAX_SOURCE_BYTES,
    PRICING_DATE,
    PredictionError,
    ProviderFailure,
    predict,
)


def _positive_float(value):
    try:
        return float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc


def _positive_int(value):
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def _parser():
    parser = argparse.ArgumentParser(prog="llmthon")
    parser.add_argument("command", choices=("predict",), help="predict source behavior")
    parser.add_argument("source", type=Path, help="UTF-8 Python source file (transmitted verbatim when opted in)")
    parser.add_argument("--model", choices=("openai/gpt-6-luna", "openai/gpt-6-luna:flex"),
                        required=True, help="exact Requesty model deployment ID")
    parser.add_argument("--timeout", type=_positive_float, default=60.0, help="positive request timeout in seconds")
    parser.add_argument("--context-limit", type=_positive_int, default=8192,
                        help="local prompt plus output token ceiling (max 1100000)")
    parser.add_argument("--output-limit", type=_positive_int, default=1024,
                        help="maximum generated tokens (max 128000)")
    parser.add_argument("--max-spend-usd", type=_positive_float, required=True,
                        help="required per-invocation worst-case USD cap")
    parser.add_argument("--send-to-provider", action="store_true",
                        help="explicitly authorize sending this source to Requesty")
    parser.add_argument("--retain-raw-response", type=Path, metavar="PATH",
                        help="opt in to writing the original provider response bytes")
    return parser


def main(argv=None, *, transport=None):
    args = _parser().parse_args(argv)
    try:
        with args.source.open("rb") as source_file:
            source_bytes = source_file.read(MAX_SOURCE_BYTES + 1)
        if len(source_bytes) > MAX_SOURCE_BYTES:
            raise PredictionError(f"source exceeds {MAX_SOURCE_BYTES} UTF-8 bytes")
        source = source_bytes.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(json.dumps({"status": "input_failure", "error": type(exc).__name__}), file=sys.stderr)
        return 2
    try:
        result = predict(
            source,
            model=args.model,
            api_key=os.environ.get("REQUESTY_API_KEY") if args.send_to_provider else None,
            timeout=args.timeout,
            context_limit=args.context_limit,
            output_limit=args.output_limit,
            max_spend_usd=args.max_spend_usd,
            send_to_provider=args.send_to_provider,
            retain_raw_response=args.retain_raw_response is not None,
            transport=transport,
        )
        if args.retain_raw_response is not None:
            args.retain_raw_response.write_bytes(result.raw_response)
    except PredictionError as exc:
        category = ("invalid_response" if isinstance(exc, InvalidResponse)
                    else "provider_failure" if isinstance(exc, ProviderFailure)
                    else "preflight_failure")
        print(json.dumps({"status": category, "error": str(exc)}), file=sys.stderr)
        return 2
    output = {
        "status": "abstention" if result.prediction["original"]["termination"] == "unknown" else "valid_prediction",
        "prediction": result.prediction,
        "provider": result.provider,
        "model": result.model,
        "prompt_template": result.prompt_template,
        "prompt_sha256": result.prompt_sha256,
        "context_limit": result.context_limit,
        "output_limit": result.output_limit,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "cost_amount": result.actual_cost_usd,
        "cost_currency": "USD" if result.actual_cost_usd is not None else None,
        "cost_provenance": "Requesty usage.cost" if result.actual_cost_usd is not None else None,
        "estimated_max_cost_usd": result.estimated_max_cost_usd,
        "estimate_provenance": f"Requesty upstream rates dated {PRICING_DATE} plus 5% PAYG margin; local estimate only",
        "latency_seconds": result.latency_seconds,
        "raw_response_retained": args.retain_raw_response is not None,
    }
    print(json.dumps(output, ensure_ascii=False, separators=(",", ":")))
    return 0
