"""Offline tests for the bounded, strict Requesty prediction path."""

import json
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from llmthon.cli import main
from llmthon.predict import (
    ALLOWED_MODELS,
    MAX_CONTEXT_TOKENS,
    MAX_OUTPUT_TOKENS,
    MESSAGE_TOKEN_OVERHEAD,
    InvalidResponse,
    PreflightError,
    ProviderFailure,
    estimate_worst_case_cost,
    predict,
)


def completion(content, *, usage=None, finish_reason="stop", refusal=None):
    message = {"role": "assistant", "content": content, "refusal": refusal}
    return json.dumps({
        "choices": [{"index": 0, "finish_reason": finish_reason, "message": message}],
        "usage": usage,
    }).encode()


class RequestyPredictTests(unittest.TestCase):
    def test_only_the_two_exact_direct_model_ids_are_accepted(self):
        self.assertEqual({"openai/gpt-6-luna", "openai/gpt-6-luna:flex"}, ALLOWED_MODELS)
        for alias in ("gpt-6-luna", "policy/cheap", "openai/gpt-6-luna;openai/gpt-6-sol"):
            with self.subTest(model=alias):
                with self.assertRaises(PreflightError):
                    predict("print(1)", model=alias, api_key="test", timeout=1,
                            context_limit=2048, output_limit=128, max_spend_usd=1,
                            send_to_provider=True, transport=lambda *a: self.fail("sent"))

    def test_budget_uses_byte_token_ceiling_output_limit_and_payg_margin(self):
        one = estimate_worst_case_cost("openai/gpt-6-luna", input_tokens=1_000_000,
                                       output_tokens=100_000)
        self.assertAlmostEqual(0.1575, one)
        flex = estimate_worst_case_cost("openai/gpt-6-luna:flex", input_tokens=1_000_000,
                                        output_tokens=100_000)
        self.assertAlmostEqual(0.07875, flex)

        captured = []
        def transport(url, headers, body, timeout):
            captured.append((url, headers, json.loads(body), timeout))
            return completion('{"schema_version":1,"mode":"strict","original":'
                              '{"termination":"completed","stdout":"ok\\n","stderr":"",'
                              '"exit_code":0,"exception_type":null},"improvised":null,"repairs":[]}')

        with self.assertRaises(PreflightError):
            predict("x", model="openai/gpt-6-luna", api_key="test", timeout=1,
                    context_limit=2048, output_limit=128, max_spend_usd=0.000001,
                    send_to_provider=True, transport=transport)
        self.assertEqual([], captured)

    def test_prompt_size_and_overhead_are_checked_against_context_and_output(self):
        with self.assertRaises(PreflightError):
            predict("x" * 4096, model="openai/gpt-6-luna", api_key="test", timeout=1,
                    context_limit=2048, output_limit=128, max_spend_usd=1,
                    send_to_provider=True, transport=lambda *a: self.fail("sent"))
        with self.assertRaises(PreflightError):
            predict("x", model="openai/gpt-6-luna", api_key="test", timeout=1,
                    context_limit=MAX_CONTEXT_TOKENS + 1, output_limit=128,
                    max_spend_usd=1, send_to_provider=True,
                    transport=lambda *a: self.fail("sent"))
        with self.assertRaises(PreflightError):
            predict("x", model="openai/gpt-6-luna", api_key="test", timeout=1,
                    context_limit=2048, output_limit=MAX_OUTPUT_TOKENS + 1,
                    max_spend_usd=1, send_to_provider=True,
                    transport=lambda *a: self.fail("sent"))
        self.assertGreaterEqual(MESSAGE_TOKEN_OVERHEAD, 1)

    def test_requires_explicit_send_and_rejects_unbounded_timeout(self):
        for kwargs in (
            {"send_to_provider": False, "timeout": 1},
            {"send_to_provider": True, "timeout": 0},
            {"send_to_provider": True, "timeout": float("inf")},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(PreflightError):
                    predict("x", model="openai/gpt-6-luna", api_key="test",
                            context_limit=2048, output_limit=128, max_spend_usd=1,
                            transport=lambda *a: self.fail("sent"), **kwargs)

    def test_makes_one_direct_request_and_validates_original_prediction(self):
        requests = []
        valid_prediction = {
            "schema_version": 1, "mode": "strict",
            "original": {"termination": "completed", "stdout": "ok\n", "stderr": "",
                         "exit_code": 0, "exception_type": None},
            "improvised": None, "repairs": [],
        }

        def transport(url, headers, body, timeout):
            requests.append((url, headers, json.loads(body), timeout))
            return completion(json.dumps(valid_prediction), usage={"prompt_tokens": 10,
                                                                     "completion_tokens": 20,
                                                                     "total_tokens": 30})

        result = predict("print('ok')", model="openai/gpt-6-luna:flex", api_key="secret",
                         timeout=2.5, context_limit=2048, output_limit=128,
                         max_spend_usd=1, send_to_provider=True, transport=transport)
        self.assertEqual(1, len(requests))
        url, headers, body, timeout = requests[0]
        self.assertEqual("https://router.requesty.ai/v1/chat/completions", url)
        self.assertEqual("Bearer secret", headers["Authorization"])
        self.assertEqual("openai/gpt-6-luna:flex", body["model"])
        self.assertEqual(128, body["max_completion_tokens"])
        self.assertEqual(2.5, timeout)
        self.assertEqual(valid_prediction, result.prediction)
        self.assertEqual(10, result.input_tokens)
        self.assertEqual(20, result.output_tokens)
        self.assertIsNone(result.actual_cost_usd)
        self.assertIsNone(result.raw_response)
        self.assertEqual(64, len(result.prompt_sha256))

    def test_transport_errors_are_not_retried_or_misreported_as_python_exceptions(self):
        calls = []
        def broken(*args):
            calls.append(args)
            raise OSError("offline")

        with self.assertRaises(ProviderFailure):
            predict("x", model="openai/gpt-6-luna", api_key="test", timeout=1,
                    context_limit=2048, output_limit=128, max_spend_usd=1,
                    send_to_provider=True, transport=broken)
        self.assertEqual(1, len(calls))

    def test_cli_requires_explicit_source_transmission_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "case.py"
            source.write_text("print('private')\n", encoding="utf-8")
            output, errors = io.StringIO(), io.StringIO()
            with patch.dict("os.environ", {}, clear=True), \
                    contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                status = main(["predict", str(source), "--model", "openai/gpt-6-luna",
                               "--max-spend-usd", "1"],
                              transport=lambda *a: self.fail("sent"))
        self.assertEqual(2, status)
        self.assertEqual("", output.getvalue())
        self.assertIn("preflight_failure", errors.getvalue())

    def test_cli_emits_an_abstention_record_after_mocked_request(self):
        response = completion('{"schema_version":1,"mode":"strict","original":'
                              '{"termination":"unknown","stdout":"","stderr":"",'
                              '"exit_code":null,"exception_type":null},"improvised":null,"repairs":[]}',
                              usage={"prompt_tokens": 100, "completion_tokens": 20,
                                     "total_tokens": 120, "cost": 0.00002})
        calls = []
        def transport(*args):
            calls.append(args)
            return response

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "case.py"
            source.write_text("print('not executed')\n", encoding="utf-8")
            output = io.StringIO()
            with patch.dict("os.environ", {"REQUESTY_API_KEY": "test-key"}), \
                    contextlib.redirect_stdout(output):
                status = main(["predict", str(source), "--model", "openai/gpt-6-luna",
                               "--max-spend-usd", "1", "--send-to-provider"],
                              transport=transport)
        record = json.loads(output.getvalue())
        self.assertEqual(0, status)
        self.assertEqual(1, len(calls))
        self.assertEqual("abstention", record["status"])
        self.assertEqual(0.00002, record["cost_amount"])
        self.assertFalse(record["raw_response_retained"])

    def test_malformed_extra_prose_refusal_and_wrong_structure_are_invalid_responses(self):
        bad_responses = (
            b"not json",
            completion('{"schema_version":1}') + b" extra",
            completion("prefix {\"schema_version\":1}"),
            completion('{"schema_version":1,"mode":"vibes","original":{},'
                       '"improvised":{},"repairs":[]}'),
            completion('{"schema_version":1,"mode":"strict","original":'
                       '{"termination":"exception","stdout":"","stderr":"",'
                       '"exit_code":1,"exception_type":"ValueError"},"improvised":null,"repairs":[]}'),
            completion('{"schema_version":1,"mode":"strict","original":'
                       '{"termination":"completed","stdout":"","stderr":"",'
                       '"exit_code":0,"exception_type":null},"improvised":null,"repairs":[]}',
                       refusal="I cannot help"),
            completion('{"schema_version":1,"mode":"strict","original":'
                       '{"termination":"completed","stdout":"","stderr":"",'
                       '"exit_code":0,"exception_type":null},"improvised":null,"repairs":[]}',
                       finish_reason="length"),
            completion('{"schema_version":1,"mode":"strict","original":'
                       '{"termination":"completed","stdout":"\\ud800","stderr":"",'
                       '"exit_code":0,"exception_type":null},"improvised":null,"repairs":[]}'),
        )
        for response in bad_responses:
            with self.subTest(response=response[:30]):
                with self.assertRaises(InvalidResponse):
                    predict("x", model="openai/gpt-6-luna", api_key="test", timeout=1,
                            context_limit=2048, output_limit=128, max_spend_usd=1,
                            send_to_provider=True, transport=lambda *a, r=response: r)

    def test_usage_may_be_absent_and_raw_response_requires_opt_in(self):
        raw = completion('{"schema_version":1,"mode":"strict","original":'
                         '{"termination":"unknown","stdout":"","stderr":"",'
                         '"exit_code":null,"exception_type":null},"improvised":null,"repairs":[]}')
        result = predict("x", model="openai/gpt-6-luna", api_key="test", timeout=1,
                         context_limit=2048, output_limit=128, max_spend_usd=1,
                         send_to_provider=True, retain_raw_response=True,
                         transport=lambda *a: raw)
        self.assertIsNone(result.input_tokens)
        self.assertIsNone(result.output_tokens)
        self.assertIsNone(result.actual_cost_usd)
        self.assertEqual(raw, result.raw_response)

    def test_requesty_usage_cost_is_parsed_without_inventing_cost_when_missing(self):
        response = completion('{"schema_version":1,"mode":"strict","original":'
                              '{"termination":"completed","stdout":"","stderr":"",'
                              '"exit_code":0,"exception_type":null},"improvised":null,"repairs":[]}',
                              usage={"prompt_tokens": 2, "completion_tokens": 3,
                                     "total_tokens": 5, "cost": 0.000012})
        result = predict("x", model="openai/gpt-6-luna", api_key="test", timeout=1,
                         context_limit=2048, output_limit=128, max_spend_usd=1,
                         send_to_provider=True, transport=lambda *a: response)
        self.assertEqual(0.000012, result.actual_cost_usd)
        self.assertEqual(2, result.input_tokens)
        self.assertEqual(3, result.output_tokens)

    def test_huge_integer_usage_cost_is_an_invalid_response(self):
        response = completion('{"schema_version":1,"mode":"strict","original":'
                              '{"termination":"completed","stdout":"","stderr":"",'
                              '"exit_code":0,"exception_type":null},"improvised":null,"repairs":[]}',
                              usage={"cost": 10**4000})
        with self.assertRaises(InvalidResponse):
            predict("x", model="openai/gpt-6-luna", api_key="test", timeout=1,
                    context_limit=2048, output_limit=128, max_spend_usd=1,
                    send_to_provider=True, transport=lambda *a: response)

    def test_duplicate_json_keys_are_invalid(self):
        response = completion('{"schema_version":1,"schema_version":1,"mode":"strict",'
                              '"original":{"termination":"completed","stdout":"",'
                              '"stderr":"","exit_code":0,"exception_type":null},'
                              '"improvised":null,"repairs":[]}')
        with self.assertRaises(InvalidResponse):
            predict("x", model="openai/gpt-6-luna", api_key="test", timeout=1,
                    context_limit=2048, output_limit=128, max_spend_usd=1,
                    send_to_provider=True, transport=lambda *a: response)


if __name__ == "__main__":
    unittest.main()
