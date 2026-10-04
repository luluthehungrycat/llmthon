"""Version 1 contracts for cases, predictions, observations, and attempts."""

from collections.abc import Mapping
import math
import re


SCHEMA_VERSION = 1
STATUSES = {"valid_prediction", "invalid_response", "provider_failure", "abstention"}
TERMINATIONS = {"completed", "exception", "nonterminating", "unknown"}
QUALIFIED_TYPE = re.compile(r"^[^.\r\n]+(?:\.[^.\r\n]+)+$")


def _is_int(value):
    return (isinstance(value, int) and not isinstance(value, bool)) or (
        isinstance(value, float) and math.isfinite(value) and value.is_integer()
    )


def _is_finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and (
        not isinstance(value, float) or math.isfinite(value)
    )


def _object(document, required, where, allowed=None):
    if not isinstance(document, Mapping):
        return [f"{where} must be an object"]
    errors = [f"{where}.{key} is required" for key in required if key not in document]
    known = set(required if allowed is None else allowed)
    errors.extend(f"{where}.{key} is not allowed" for key in document if key not in known)
    return errors


def _version(document, errors, where):
    if document.get("schema_version") != SCHEMA_VERSION or not _is_int(document.get("schema_version")):
        errors.append(f"{where}.schema_version must be {SCHEMA_VERSION}")


def _outcome(value, where):
    errors = _object(value, ("termination", "stdout", "stderr", "exit_code", "exception_type"), where)
    if errors:
        return errors
    termination = value["termination"]
    if not isinstance(termination, str) or termination not in TERMINATIONS:
        errors.append(f"{where}.termination is invalid")
    if not isinstance(value["stdout"], str) or not isinstance(value["stderr"], str):
        errors.append(f"{where}.stdout and stderr must be strings")
    code = value["exit_code"]
    if isinstance(termination, str) and termination in {"completed", "exception"}:
        if not _is_int(code):
            errors.append(f"{where}.exit_code must be an integer for {termination}")
    elif isinstance(termination, str) and code is not None:
        errors.append(f"{where}.exit_code must be null for {termination}")
    exception_type = value["exception_type"]
    if termination == "exception":
        if not isinstance(exception_type, str) or not QUALIFIED_TYPE.fullmatch(exception_type):
            errors.append(f"{where}.exception_type must be a qualified type for exception")
    elif exception_type is not None:
        errors.append(f"{where}.exception_type must be null unless termination is exception")
    return errors


def validate_case(document):
    required = ("schema_version", "case_id", "source_sha256", "source", "mode", "reference_profile")
    errors = _object(document, required, "case")
    if errors:
        return errors
    _version(document, errors, "case")
    if not isinstance(document["case_id"], str) or not document["case_id"]:
        errors.append("case.case_id must be a non-empty string")
    if not isinstance(document["source"], str):
        errors.append("case.source must be a string")
    if not isinstance(document["source_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", document["source_sha256"]):
        errors.append("case.source_sha256 must be 64 lowercase hexadecimal characters")
    elif isinstance(document["source"], str):
        import hashlib
        try:
            actual_hash = hashlib.sha256(document["source"].encode("utf-8")).hexdigest()
        except UnicodeEncodeError:
            errors.append("case.source must be valid UTF-8 text")
        else:
            if document["source_sha256"] != actual_hash:
                errors.append("case.source_sha256 does not match the UTF-8 source")
    if not isinstance(document["mode"], str) or document["mode"] not in {"strict", "vibes"}:
        errors.append("case.mode must be strict or vibes")
    errors.extend(_validate_profile(document["reference_profile"], "case.reference_profile"))
    return errors


def _validate_profile(profile, where):
    profile_keys = ("implementation", "version", "operating_environment", "encoding", "locale", "timezone",
                    "working_directory_policy", "environment_allowlist", "argv", "stdin", "hash_seed",
                    "resource_limits")
    errors = _object(profile, profile_keys, where)
    if errors:
        return errors
    for key in ("implementation", "version", "operating_environment", "encoding", "locale", "timezone",
                "working_directory_policy", "stdin", "hash_seed"):
        if not isinstance(profile[key], str):
            errors.append(f"{where}.{key} must be a string")
    for key in ("environment_allowlist", "argv"):
        if not isinstance(profile[key], list) or not all(isinstance(x, str) for x in profile[key]):
            errors.append(f"{where}.{key} must be an array of strings")
    if profile["stdin"] != "":
        errors.append(f"{where}.stdin must be empty in version 1")
    limits = profile["resource_limits"]
    limit_keys = ("cpu_seconds", "wall_seconds", "memory_bytes", "process_count", "output_bytes")
    limit_errors = _object(limits, limit_keys, f"{where}.resource_limits")
    errors.extend(limit_errors)
    if not limit_errors:
        for key in limit_keys:
            if not _is_int(limits[key]) or limits[key] < 1:
                errors.append(f"{where}.resource_limits.{key} must be a positive integer")
    return errors


def validate_prediction(document):
    required = ("schema_version", "mode", "original", "improvised", "repairs")
    errors = _object(document, required, "prediction")
    if errors:
        return errors
    _version(document, errors, "prediction")
    if not isinstance(document["mode"], str) or document["mode"] not in {"strict", "vibes"}:
        errors.append("prediction.mode must be strict or vibes")
    errors.extend(_outcome(document["original"], "prediction.original"))
    repairs = document["repairs"]
    if not isinstance(repairs, list) or not all(isinstance(item, str) and item for item in repairs):
        errors.append("prediction.repairs must be an array of non-empty strings")
    if document["mode"] == "strict":
        if document["improvised"] is not None:
            errors.append("prediction.improvised must be null in strict mode")
        if repairs != []:
            errors.append("prediction.repairs must be empty in strict mode")
    elif document["mode"] == "vibes":
        errors.extend(_outcome(document["improvised"], "prediction.improvised"))
    return errors


def validate_observation(document):
    required = ("schema_version", "stdout_b64", "stderr_b64", "return_code", "elapsed_seconds", "termination",
                "exception_type", "limit_event", "eligible", "exclusion_reason")
    errors = _object(document, required, "observation")
    if errors:
        return errors
    _version(document, errors, "observation")
    import base64
    for key in ("stdout_b64", "stderr_b64"):
        try:
            decoded = base64.b64decode(document[key], validate=True)
            if base64.b64encode(decoded).decode("ascii") != document[key]:
                errors.append(f"observation.{key} must be canonical base64")
        except (ValueError, TypeError):
            errors.append(f"observation.{key} must be valid base64")
    code = document["return_code"]
    if code is not None and not _is_int(code):
        errors.append("observation.return_code must be an integer or null")
    if isinstance(document["termination"], str) and document["termination"] in {"completed", "exception"} and not _is_int(code):
        errors.append("observation.return_code must be an integer for completed or exception observations")
    if not _is_finite_number(document["elapsed_seconds"]) or document["elapsed_seconds"] < 0:
        errors.append("observation.elapsed_seconds must be non-negative")
    if not isinstance(document["termination"], str) or document["termination"] not in {"completed", "exception", "unknown"}:
        errors.append("observation.termination is invalid")
    exception_type = document["exception_type"]
    if document["termination"] != "exception" and exception_type is not None:
        errors.append("observation.exception_type must be null unless termination is exception")
    if exception_type is not None and (not isinstance(exception_type, str) or not QUALIFIED_TYPE.fullmatch(exception_type)):
        errors.append("observation.exception_type must be a qualified type or null")
    if document["limit_event"] is not None and (not isinstance(document["limit_event"], str) or document["limit_event"] not in {"timeout", "resource_limit", "signal"}):
        errors.append("observation.limit_event is invalid")
    if document["limit_event"] is not None and document["termination"] != "unknown":
        errors.append("observation termination must be unknown for a limit event")
    if not isinstance(document["eligible"], bool):
        errors.append("observation.eligible must be a boolean")
    reason = document["exclusion_reason"]
    if document["eligible"] and reason is not None:
        errors.append("observation.exclusion_reason must be null when eligible")
    if not document["eligible"] and (not isinstance(reason, str) or not reason):
        errors.append("observation.exclusion_reason is required when ineligible")
    if document["termination"] == "unknown" and document["limit_event"] is None and document["eligible"]:
        errors.append("observation with unknown termination and no limit event must be ineligible")
    return errors


def validate_run_record(document):
    required = ("schema_version", "run_id", "case_id", "source_sha256", "reference_profile", "attempt_index",
                "repetition_index", "planned", "status", "prediction", "observation", "provider", "model",
                "prompt_template", "prompt_sha256", "decoding_settings", "context_limit", "output_limit", "seed",
                "latency_seconds", "input_tokens", "output_tokens", "cost_amount", "cost_currency", "cost_provenance")
    errors = _object(document, required, "run_record")
    if errors:
        return errors
    _version(document, errors, "run_record")
    for key in ("run_id", "case_id"):
        if not isinstance(document[key], str) or not document[key]:
            errors.append(f"run_record.{key} must be a non-empty string")
    if not isinstance(document["source_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", document["source_sha256"]):
        errors.append("run_record.source_sha256 must be 64 lowercase hexadecimal characters")
    errors.extend(_validate_profile(document["reference_profile"], "run_record.reference_profile"))
    for key in ("attempt_index", "repetition_index", "context_limit", "output_limit"):
        if not _is_int(document[key]) or document[key] < (0 if key in {"attempt_index", "repetition_index"} else 1):
            errors.append(f"run_record.{key} has an invalid integer value")
    if not isinstance(document["planned"], bool):
        errors.append("run_record.planned must be a boolean")
    status = document["status"]
    if not isinstance(status, str) or status not in STATUSES:
        errors.append("run_record.status is invalid")
    if status == "valid_prediction":
        errors.extend(validate_prediction(document["prediction"]))
        original = document["prediction"].get("original") if isinstance(document["prediction"], Mapping) else None
        if isinstance(original, Mapping) and original.get("termination") == "unknown":
            errors.append("run_record.status must be abstention for an unknown prediction")
    elif status == "abstention":
        if document["prediction"] is not None:
            errors.extend(validate_prediction(document["prediction"]))
            original = document["prediction"].get("original") if isinstance(document["prediction"], Mapping) else None
            if isinstance(original, Mapping) and original.get("termination") != "unknown":
                errors.append("run_record abstention prediction must have unknown original termination")
    elif document["prediction"] is not None:
        errors.append("run_record.prediction must be null without a valid prediction")
    errors.extend(validate_observation(document["observation"]))
    for key in ("provider", "model", "prompt_template", "prompt_sha256", "cost_currency", "cost_provenance"):
        if document[key] is not None and not isinstance(document[key], str):
            errors.append(f"run_record.{key} must be a string or null")
        elif document[key] is not None and key != "prompt_sha256" and not document[key]:
            errors.append(f"run_record.{key} must be non-empty when provided")
    if not isinstance(document["decoding_settings"], Mapping):
        errors.append("run_record.decoding_settings must be an object")
    for key in ("latency_seconds", "cost_amount"):
        value = document[key]
        if value is not None and (not _is_finite_number(value) or value < 0):
            errors.append(f"run_record.{key} must be non-negative or null")
    for key in ("input_tokens", "output_tokens", "seed"):
        value = document[key]
        if value is not None and (not _is_int(value) or (key != "seed" and value < 0)):
            message = "an integer or null" if key == "seed" else "a non-negative integer or null"
            errors.append(f"run_record.{key} must be {message}")
    if document["prompt_sha256"] is not None and (not isinstance(document["prompt_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", document["prompt_sha256"])):
        errors.append("run_record.prompt_sha256 must be 64 lowercase hexadecimal characters or null")
    if document["cost_amount"] is not None and (not document["cost_currency"] or not document["cost_provenance"]):
        errors.append("run_record known cost requires currency and pricing provenance")
    return errors
