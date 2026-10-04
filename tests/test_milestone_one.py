import base64
import json
import re
import unittest
from pathlib import Path

from llmthon.compare import compare
from llmthon.contracts import validate_case, validate_observation, validate_prediction, validate_run_record


FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def outcome(*, termination="completed", stdout="hello\n", stderr="", exit_code=0, exception_type=None):
    return {
        "termination": termination,
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
        "exception_type": exception_type,
    }


def observation(*, stdout=b"hello\n", stderr=b"", return_code=0, termination="completed",
                exception_type=None, eligible=True, exclusion_reason=None, limit_event=None):
    return {
        "schema_version": 1,
        "stdout_b64": base64.b64encode(stdout).decode("ascii"),
        "stderr_b64": base64.b64encode(stderr).decode("ascii"),
        "return_code": return_code,
        "elapsed_seconds": 0.01,
        "termination": termination,
        "exception_type": exception_type,
        "limit_event": limit_event,
        "eligible": eligible,
        "exclusion_reason": exclusion_reason,
    }


def attempt(status="valid_prediction", prediction=None):
    return {"status": status, "prediction": prediction or {
        "schema_version": 1,
        "mode": "strict",
        "original": outcome(),
        "improvised": None,
        "repairs": [],
    }}


def run_row(observed, attempted):
    return {**attempted, "observation": observed}


class ContractFixtureTests(unittest.TestCase):
    def test_valid_and_invalid_fixture_sets_match_contracts(self):
        validators = {
            "case": validate_case,
            "prediction": validate_prediction,
            "observation": validate_observation,
            "run_record": validate_run_record,
        }
        for name, validator in validators.items():
            with self.subTest(contract=name, validity="valid"):
                self.assertEqual([], validator(load_fixture(f"{name}.valid.json")))
            with self.subTest(contract=name, validity="invalid"):
                self.assertTrue(validator(load_fixture(f"{name}.invalid.json")))

    def test_mode_and_failure_fixtures_are_valid_contract_examples(self):
        for name in ("prediction.system-exit.json", "prediction.abstention.json"):
            with self.subTest(fixture=name):
                self.assertEqual([], validate_prediction(load_fixture(name)))
        self.assertEqual([], validate_observation(load_fixture("observation.timeout.json")))
        self.assertEqual([], validate_run_record(load_fixture("run_record.provider_failure.json")))
        self.assertTrue(validate_prediction(load_fixture("response.malformed.json")))
        system_exit = load_fixture("prediction.system-exit.json")["original"]
        self.assertEqual(("completed", 7, None),
                         (system_exit["termination"], system_exit["exit_code"], system_exit["exception_type"]))

    def test_exception_type_must_be_qualified(self):
        prediction = load_fixture("prediction.valid.json")
        prediction["original"]["exception_type"] = "ValueError"
        self.assertTrue(validate_prediction(prediction))

    def test_integer_contract_fields_accept_integral_floats_but_reject_booleans(self):
        for field, value in (("schema_version", 1.0),):
            prediction = load_fixture("prediction.valid.json")
            prediction[field] = value
            with self.subTest(field=field, value=value):
                self.assertEqual([], validate_prediction(prediction))
        prediction = load_fixture("prediction.valid.json")
        prediction["original"]["exit_code"] = 0.0
        self.assertEqual([], validate_prediction(prediction))

        for field, value in (("schema_version", True),):
            prediction = load_fixture("prediction.valid.json")
            prediction[field] = value
            with self.subTest(field=field, value=value):
                self.assertTrue(validate_prediction(prediction))
        prediction = load_fixture("prediction.valid.json")
        prediction["original"]["exit_code"] = True
        self.assertTrue(validate_prediction(prediction))

    def test_integer_contract_fields_reject_non_integral_and_non_finite_floats(self):
        for value in (1.5, float("nan"), float("inf"), float("-inf")):
            prediction = load_fixture("prediction.valid.json")
            prediction["schema_version"] = value
            with self.subTest(field="schema_version", value=value):
                self.assertTrue(validate_prediction(prediction))
            prediction = load_fixture("prediction.valid.json")
            prediction["original"]["exit_code"] = value
            with self.subTest(field="exit_code", value=value):
                self.assertTrue(validate_prediction(prediction))

    def test_versioned_json_schemas_are_parseable(self):
        for name in ("case", "prediction", "observation", "run-record"):
            with self.subTest(schema=name):
                schema_path = Path(__file__).parents[1] / "src" / "llmthon" / "schemas" / "v1" / f"{name}.schema.json"
                schema = json.loads(schema_path.read_text(encoding="utf-8"))
                self.assertEqual(1, schema["properties"]["schema_version"]["const"])
                self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])

    def test_observation_schema_base64_patterns_reject_malformed_text_using_search(self):
        schema_path = Path(__file__).parents[1] / "src" / "llmthon" / "schemas" / "v1" / "observation.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        for field in ("stdout_b64", "stderr_b64"):
            pattern = schema["properties"][field]["pattern"]
            for encoded in ("", "AA==", "AAA=", "AAAA", "YWJjZA=="):
                with self.subTest(field=field, encoded=encoded):
                    self.assertIsNotNone(re.search(pattern, encoded))
            for encoded in ("A", "A===", "YWJj=", "YWJj\n", "@@==", "abcd===", "AB==", "AAF="):
                with self.subTest(field=field, encoded=encoded):
                    self.assertIsNone(re.search(pattern, encoded))

    def test_numeric_schemas_bound_values_to_finite_float_range(self):
        schema_dir = Path(__file__).parents[1] / "src" / "llmthon" / "schemas" / "v1"
        observation_schema = json.loads((schema_dir / "observation.schema.json").read_text(encoding="utf-8"))
        run_schema = json.loads((schema_dir / "run-record.schema.json").read_text(encoding="utf-8"))
        finite_float_max = 1.7976931348623157e308
        self.assertEqual(finite_float_max, observation_schema["properties"]["elapsed_seconds"]["maximum"])
        for field in ("latency_seconds", "cost_amount"):
            with self.subTest(field=field):
                self.assertEqual(finite_float_max, run_schema["properties"][field]["maximum"])

    def test_observation_rejects_non_finite_elapsed_seconds(self):
        for elapsed in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(elapsed=elapsed):
                observed = observation()
                observed["elapsed_seconds"] = elapsed
                self.assertTrue(validate_observation(observed))

    def test_unknown_observation_without_limit_event_must_be_excluded(self):
        observed = observation(return_code=None, termination="unknown")
        self.assertTrue(validate_observation(observed))
        observed["eligible"] = False
        observed["exclusion_reason"] = "observation_unavailable"
        self.assertEqual([], validate_observation(observed))

    def test_run_record_rejects_non_finite_latency_and_cost(self):
        for field in ("latency_seconds", "cost_amount"):
            for value in (float("nan"), float("inf"), float("-inf")):
                with self.subTest(field=field, value=value):
                    record = load_fixture("run_record.valid.json")
                    record[field] = value
                    if field == "cost_amount":
                        record["cost_currency"] = "USD"
                        record["cost_provenance"] = "fixture"
                    self.assertTrue(validate_run_record(record))


class ComparisonTests(unittest.TestCase):
    def test_comparator_accepts_a_versioned_run_record_directly(self):
        result = compare([load_fixture("run_record.valid.json")])
        self.assertEqual(1, result["exact_matches"])

    def test_output_comparison_preserves_trailing_whitespace_and_newlines(self):
        predicted = {"schema_version": 1, "mode": "strict", "original": outcome(),
                     "improvised": None, "repairs": []}
        result = compare([run_row(observation(stdout=b"hello \n"), attempt(prediction=predicted))])
        self.assertEqual(0, result["stdout"]["matches"])
        self.assertEqual(0, result["exact_matches"])
        crlf = compare([run_row(observation(stdout=b"hello\r\n"), attempt(prediction=predicted))])
        self.assertEqual(0, crlf["stdout"]["matches"])

    def test_traceback_difference_does_not_erase_exception_component_match(self):
        predicted = {"schema_version": 1, "mode": "strict",
                     "original": outcome(termination="exception", exit_code=1,
                                          stderr="Traceback: line 8\n", exception_type="builtins.ValueError"),
                     "improvised": None, "repairs": []}
        observed = observation(stdout=b"", stderr=b"Traceback: line 9\n", return_code=1,
                               termination="exception", exception_type="builtins.ValueError")
        result = compare([run_row(observed, attempt(prediction=predicted))])
        self.assertEqual(1, result["exception_type"]["matches"])
        self.assertEqual(0, result["stderr"]["matches"])
        self.assertEqual(0, result["exact_matches"])

    def test_missing_observed_exception_metadata_is_unscored_and_blocks_exact_match(self):
        predicted = {"schema_version": 1, "mode": "strict",
                     "original": outcome(termination="exception", exit_code=1,
                                          stderr="ValueError\n", exception_type="builtins.ValueError"),
                     "improvised": None, "repairs": []}
        result = compare([run_row(observation(stdout=b"", stderr=b"ValueError\n",
                                              return_code=1, termination="exception"),
                                  attempt(prediction=predicted))])
        self.assertEqual({"matches": 0, "scored": 0, "rate": None}, result["exception_type"])
        self.assertEqual(0, result["exact_matches"])

    def test_exit_code_is_part_of_termination_component(self):
        predicted = {"schema_version": 1, "mode": "strict",
                     "original": outcome(exit_code=0), "improvised": None, "repairs": []}
        result = compare([run_row(observation(return_code=3), attempt(prediction=predicted))])
        self.assertEqual(0, result["termination_exit_code"]["matches"])

    def test_invalid_provider_failure_and_abstention_remain_in_denominator(self):
        rows = [run_row(observation(), {"status": status, "prediction": None})
                for status in ("invalid_response", "provider_failure", "abstention")]
        result = compare(rows)
        self.assertEqual(3, result["denominator"])
        self.assertEqual(0, result["exact_matches"])
        self.assertEqual({"invalid_response": 1, "provider_failure": 1, "abstention": 1},
                         result["attempt_failures"])
        unplanned = run_row(observation(), {"planned": False, "status": "provider_failure", "prediction": None})
        with_unplanned = compare([*rows, unplanned])
        self.assertEqual(3, with_unplanned["planned_attempts"])
        self.assertEqual(3, with_unplanned["denominator"])

    def test_unknown_prediction_is_an_abstention_not_a_correct_unknown_match(self):
        predicted = load_fixture("prediction.abstention.json")
        result = compare([run_row(observation(), attempt("abstention", predicted))])
        self.assertEqual(1, result["denominator"])
        self.assertEqual(0, result["exact_matches"])
        self.assertEqual(1, result["attempt_failures"]["abstention"])

    def test_excluded_reference_is_reported_outside_denominator(self):
        row = run_row(observation(eligible=False, exclusion_reason="profile_mismatch"),
                      attempt("provider_failure", None))
        result = compare([row])
        self.assertEqual(0, result["denominator"])
        self.assertEqual({"profile_mismatch": 1}, result["exclusions"])

    def test_planned_provider_failure_is_counted_with_limit_event_reference(self):
        observed = observation(return_code=None, termination="unknown", limit_event="timeout")
        result = compare([run_row(observed, attempt("provider_failure", None))])
        self.assertEqual(0, result["denominator"])
        self.assertEqual({"timeout": 1}, result["limit_events"])
        self.assertEqual(1, result["attempt_failures"]["provider_failure"])

    def test_planned_provider_failure_is_counted_with_ineligible_reference(self):
        observed = observation(eligible=False, exclusion_reason="profile_mismatch")
        result = compare([run_row(observed, attempt("provider_failure", None))])
        self.assertEqual(0, result["denominator"])
        self.assertEqual({"profile_mismatch": 1}, result["exclusions"])
        self.assertEqual(1, result["attempt_failures"]["provider_failure"])

    def test_unknown_observation_without_limit_event_is_excluded_even_when_eligibility_is_incorrect(self):
        observed = observation(return_code=None, termination="unknown")
        result = compare([run_row(observed, attempt())])
        self.assertEqual(0, result["denominator"])
        self.assertEqual({"unknown_termination": 1}, result["exclusions"])

    def test_planned_provider_failure_is_counted_with_non_utf8_reference(self):
        result = compare([run_row(observation(stdout=b"\xff"), attempt("provider_failure", None))])
        self.assertEqual(0, result["denominator"])
        self.assertEqual({"non_utf8_output": 1}, result["exclusions"])
        self.assertEqual(1, result["attempt_failures"]["provider_failure"])

    def test_timeout_and_resource_limit_are_separate_and_excluded(self):
        rows = [run_row(observation(return_code=None, termination="unknown", limit_event=event),
                        attempt("abstention", None)) for event in ("timeout", "resource_limit")]
        result = compare(rows)
        self.assertEqual(0, result["denominator"])
        self.assertEqual({"timeout": 1, "resource_limit": 1}, result["limit_events"])
        self.assertEqual(2, result["limit_event_attempts"])

    def test_non_utf8_observation_is_disclosed_as_exclusion(self):
        result = compare([run_row(observation(stdout=b"\xff"), attempt())])
        self.assertEqual(0, result["denominator"])
        self.assertEqual({"non_utf8_output": 1}, result["exclusions"])

    def test_vibes_scores_original_outcome_and_reports_nontermination_predictions(self):
        predicted = {"schema_version": 1, "mode": "vibes",
                     "original": outcome(stdout="hello\n"),
                     "improvised": outcome(stdout="different\n"), "repairs": []}
        self.assertEqual(1, compare([run_row(observation(), attempt(prediction=predicted))])["exact_matches"])
        looping = {"schema_version": 1, "mode": "strict",
                   "original": outcome(termination="nonterminating", stdout="", exit_code=None),
                   "improvised": None, "repairs": []}
        self.assertEqual(1, compare([run_row(observation(), attempt(prediction=looping))])["nontermination_predictions"])


if __name__ == "__main__":
    unittest.main()
