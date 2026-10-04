"""Pure comparison and denominator accounting for version 1 benchmark runs."""

import base64


_FAILURE_STATUSES = ("invalid_response", "provider_failure", "abstention")


def _component(matches, scored):
    return {"matches": matches, "scored": scored}


def compare(rows):
    """Compare validated version 1 run records, one planned attempt per row.

    Each row contains an observation and the attempt status/prediction from the
    run-record contract. No input source is executed or normalized. Exclusions
    and observed limit events are accounted separately from accuracy.
    """
    result = {
        "planned_attempts": 0,
        "denominator": 0,
        "exact_matches": 0,
        "stdout": _component(0, 0),
        "stderr": _component(0, 0),
        "termination_exit_code": _component(0, 0),
        "exception_type": _component(0, 0),
        "coverage": {"valid_predictions": 0, "scored": 0},
        "attempt_failures": {name: 0 for name in _FAILURE_STATUSES},
        "exclusions": {},
        "limit_events": {},
        "limit_event_attempts": 0,
        "nontermination_predictions": 0,
    }

    for row in rows:
        observation = row["observation"]
        attempt = row
        if not attempt.get("planned", True):
            continue
        result["planned_attempts"] += 1
        supplied_prediction = attempt.get("prediction") if attempt.get("status") in {"valid_prediction", "abstention"} else None
        if supplied_prediction is not None and supplied_prediction.get("original", {}).get("termination") == "nonterminating":
            result["nontermination_predictions"] += 1

        status = attempt["status"]
        prediction = attempt.get("prediction") if status in {"valid_prediction", "abstention"} else None
        is_abstention = (status == "abstention" or (prediction is not None
                         and prediction.get("original", {}).get("termination") == "unknown"))
        if is_abstention:
            result["attempt_failures"]["abstention"] += 1
        elif status in {"invalid_response", "provider_failure"}:
            result["attempt_failures"][status] += 1
        elif status == "valid_prediction" and prediction is not None:
            try:
                prediction["original"]["stdout"].encode("utf-8")
                prediction["original"]["stderr"].encode("utf-8")
            except UnicodeEncodeError:
                result["attempt_failures"]["invalid_response"] += 1
                prediction = None

        if not observation["eligible"]:
            reason = observation["exclusion_reason"]
            result["exclusions"][reason] = result["exclusions"].get(reason, 0) + 1
            continue
        limit_event = observation["limit_event"]
        if limit_event is not None:
            result["limit_events"][limit_event] = result["limit_events"].get(limit_event, 0) + 1
            result["limit_event_attempts"] += 1
            continue
        if observation["termination"] == "unknown":
            reason = "unknown_termination"
            result["exclusions"][reason] = result["exclusions"].get(reason, 0) + 1
            continue

        observed_stdout = base64.b64decode(observation["stdout_b64"], validate=True)
        observed_stderr = base64.b64decode(observation["stderr_b64"], validate=True)
        try:
            observed_stdout.decode("utf-8")
            observed_stderr.decode("utf-8")
        except UnicodeDecodeError:
            reason = "non_utf8_output"
            result["exclusions"][reason] = result["exclusions"].get(reason, 0) + 1
            continue

        result["denominator"] += 1
        result["coverage"]["scored"] += 1
        if is_abstention:
            prediction = None
        if status == "valid_prediction" and prediction is not None:
            result["coverage"]["valid_predictions"] += 1

        for component in ("stdout", "stderr", "termination_exit_code"):
            result[component]["scored"] += 1
        if observation["termination"] == "exception" and observation["exception_type"] is not None:
            result["exception_type"]["scored"] += 1

        if prediction is None:
            continue
        predicted = prediction["original"]
        predicted_stdout = predicted["stdout"].encode("utf-8")
        predicted_stderr = predicted["stderr"].encode("utf-8")
        stdout_match = predicted_stdout == observed_stdout
        stderr_match = predicted_stderr == observed_stderr
        term_exit_match = (predicted["termination"] == observation["termination"]
                           and predicted["exit_code"] == observation["return_code"])
        result["stdout"]["matches"] += int(stdout_match)
        result["stderr"]["matches"] += int(stderr_match)
        result["termination_exit_code"]["matches"] += int(term_exit_match)

        exception_applicable = observation["termination"] == "exception" and observation["exception_type"] is not None
        exception_match = None
        if exception_applicable:
            exception_match = predicted["termination"] == "exception" and predicted["exception_type"] == observation["exception_type"]
            result["exception_type"]["matches"] += int(exception_match)

        normally_observed = observation["termination"] in {"completed", "exception"}
        full_match = (normally_observed and stdout_match and stderr_match and term_exit_match
                      and (not exception_applicable or exception_match is True)
                      and not (observation["termination"] == "exception" and observation["exception_type"] is None))
        result["exact_matches"] += int(full_match)

    result["full_match_accuracy"] = _rate(result["exact_matches"], result["denominator"])
    result["coverage_rate"] = _rate(result["coverage"]["valid_predictions"], result["coverage"]["scored"])
    for name in ("stdout", "stderr", "termination_exit_code", "exception_type"):
        result[name]["rate"] = _rate(result[name]["matches"], result[name]["scored"])
    return result


def _rate(numerator, denominator):
    return None if denominator == 0 else numerator / denominator
