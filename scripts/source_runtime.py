"""Bounded source requests and provenance; no process-wide HTTP patches."""

from __future__ import annotations

import json
import math
import random
import re
import time
from datetime import datetime, timedelta, timezone
from inspect import unwrap
from subprocess import TimeoutExpired
from types import FunctionType
from urllib.parse import urlsplit
from uuid import uuid4

import requests


BJ_TZ = timezone(timedelta(hours=8))
RUNTIME_VERSION = "2026-10-20-research-consistency-1"
SOURCE_STATUSES = {"ok", "no_record", "source_failure", "stale", "not_supported",
                   "rate_limited", "malformed", "partial"}


def classify_exception(exc: BaseException) -> str:
    if isinstance(exc, SourceError):
        return exc.result["error_type"]
    status = getattr(getattr(exc, "response", None), "status_code", getattr(exc, "status_code", None))
    if status in (403, 429):
        return "rate_limit_or_anti_bot"
    if isinstance(exc, (requests.Timeout, TimeoutError, TimeoutExpired)):
        return "timeout"
    if isinstance(exc, (requests.ConnectionError, ConnectionError)):
        return "connection_error"
    if isinstance(exc, requests.HTTPError):
        return "http_error"
    if isinstance(exc, (AttributeError, ImportError)):
        return "adapter_error"
    if isinstance(exc, (ValueError, KeyError, IndexError, UnicodeError)):
        return "parse_error"
    if exc.__cause__ is not None and exc.__cause__ is not exc:
        return classify_exception(exc.__cause__)
    return "unknown"


def checked_source_url(value: str) -> str:
    if isinstance(value, str):
        if re.fullmatch(r"adapter:[A-Za-z0-9_.-]+", value):
            return value
        parsed = urlsplit(value)
        if (parsed.scheme in {"http", "https"} and parsed.hostname and not re.search(r"\s", value)
                and not (parsed.username or parsed.password)):
            return value
    raise ValueError("Source needs an HTTP(S) URL or adapter:<name> identifier")


def validate_source_result(result: dict, *, require_source_url: bool = False) -> None:
    """New metadata is optional so existing v1/v2 snapshots stay readable."""
    if not isinstance(result, dict) or not result.get("source") or result.get("status") not in SOURCE_STATUSES:
        raise ValueError("Invalid source result")
    if require_source_url:
        checked_source_url(result.get("source_url"))
    for key in ("attempts", "http_status", "elapsed_ms"):
        if key not in result:
            continue
        value = result[key]
        if key == "http_status" and value is None:
            continue
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value < 0
                or (key != "elapsed_ms" and not isinstance(value, int))):
            raise ValueError(f"Invalid source {key}")
    for key in ("fallback_from", "coverage"):
        if key in result:
            expected = (list, dict) if key == "coverage" else (str, list)
            if not isinstance(result[key], expected):
                raise ValueError(f"Invalid source {key}")
            if key == "fallback_from" and isinstance(result[key], list) and not all(
                    isinstance(item, str) and item for item in result[key]):
                raise ValueError("fallback_from must list source names")
            try:
                json.dumps(result[key], allow_nan=False)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Source {key} must be JSON serializable") from exc
    if "error_type" in result and not isinstance(result["error_type"], str):
        raise ValueError("Invalid source error_type")
    if "retrieved_at" in result:
        try:
            stamp = datetime.fromisoformat(result["retrieved_at"])
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid source retrieved_at") from exc
        if stamp.utcoffset() != timedelta(hours=8):
            raise ValueError("Source retrieved_at must use Beijing time")


class SourceError(RuntimeError):
    def __init__(self, result: dict):
        super().__init__(result.get("detail", "Source request failed"))
        self.result = result


class SourceRuntime:
    def __init__(self, *, cooldown_seconds: int = 300):
        self.started_monotonic = time.monotonic()
        self.cooldown_seconds = cooldown_seconds
        self.cooldowns: dict[str, tuple[float, dict]] = {}
        self.events: dict[str, list[dict]] = {}
        self.reported: dict[str, int] = {}
        self.calendar: list = []
        self.calendar_verified: bool | None = None
        self.run_id = uuid4().hex

    def observation_time(self, reference_time: datetime) -> datetime:
        """Advance the run's supplied start time by actual elapsed collection time."""
        return reference_time.astimezone(BJ_TZ) + timedelta(seconds=time.monotonic() - self.started_monotonic)

    def is_cooled_down(self, source: str) -> bool:
        return time.monotonic() < self.cooldowns.get(source, (0, {}))[0]

    def request(self, source: str, url: str, *, http_get, params=None, headers=None,
                timeout=(5, 15), max_attempts=3, **kwargs) -> tuple[object | None, dict]:
        """Buffer and close normal responses; streaming consumers must close after reading."""
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or not 1 <= max_attempts <= 3:
            raise ValueError("max_attempts must be between 1 and 3")
        started = time.monotonic()
        meta = {"source": source, "source_url": url, "status": "source_failure", "attempts": 0,
                "elapsed_ms": 0, "retrieved_at": datetime.now(BJ_TZ).isoformat(), "attempt_log": [],
                "run_id": self.run_id, "http_status": None}
        if self.is_cooled_down(source):
            prior = self.cooldowns[source][1]
            meta.update(status=prior["status"], error_type=prior["error_type"],
                        detail="Source cooling down after: " + prior.get("detail", "failure"),
                        cooldown_until=prior["cooldown_until"])
        else:
            for attempt in range(1, max_attempts + 1):
                response = None
                try:
                    meta["attempts"] = attempt
                    response = http_get(url, params=params,
                        headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*", **(headers or {})},
                        timeout=timeout or (5, 15), **kwargs)
                    status = getattr(response, "status_code", None)
                    if isinstance(status, int):
                        meta["http_status"] = status
                    response.raise_for_status()
                    if not kwargs.get("stream") and getattr(response, "content", None) == b"":
                        raise ValueError("HTTP success with empty response body")
                    if not kwargs.get("stream"):
                        response.close()
                    meta["attempt_log"].append({"attempt": attempt, "status": "ok", "http_status": status})
                    meta.update(status="ok", error_type="", detail="")
                    meta["elapsed_ms"] = round((time.monotonic() - started) * 1000, 2)
                    self.events.setdefault(source, []).append(meta)
                    return response, meta
                except Exception as exc:
                    kind = classify_exception(exc)
                    status = getattr(response, "status_code", None)
                    meta.update(status="rate_limited" if kind == "rate_limit_or_anti_bot" else
                                "malformed" if kind == "parse_error" else "source_failure",
                                error_type=kind, detail=f"{type(exc).__name__}: {exc}")
                    meta["attempt_log"].append({"attempt": attempt, "error_type": kind,
                                               "http_status": status, "detail": meta["detail"]})
                    if response is not None:
                        response.close()
                    retryable = kind in {"timeout", "connection_error"} or status == 429 or (
                        isinstance(status, int) and 500 <= status <= 599)
                    if not retryable or attempt == max_attempts:
                        if kind in {"timeout", "connection_error", "rate_limit_or_anti_bot"} or retryable:
                            seconds = max(self.cooldown_seconds, 900 if source.startswith(
                                ("eastmoney_heat", "eastmoney_top", "xueqiu", "ths_", "eastmoney_news")) else 0)
                            meta["cooldown_until"] = (datetime.now(BJ_TZ) + timedelta(seconds=seconds)).isoformat()
                            self.cooldowns[source] = (time.monotonic() + seconds, dict(meta))
                        break
                    time.sleep(min(4, 0.5 * 2 ** (attempt - 1)) + random.uniform(0, 0.25))
        meta["elapsed_ms"] = round((time.monotonic() - started) * 1000, 2)
        self.events.setdefault(source, []).append(meta)
        return None, meta

    def http(self, source: str, http_get):
        def request(url, **kwargs):
            response, result = self.request(source, url, http_get=http_get, **kwargs)
            if response is None:
                raise SourceError(result)
            return response
        return request

    def call(self, source: str, operation, *args, response_validator=None, **kwargs):
        """Bind this provider's requests locally, including same-module helpers."""
        if self.is_cooled_down(source):
            _, meta = self.request(source, "", http_get=requests.get)
            raise SourceError(meta)
        started = time.monotonic()
        event_start = len(self.events.get(source, []))
        bound = {}
        streaming_responses = []
        def bind(function):
            function = unwrap(function)
            if not isinstance(function, FunctionType):
                return function
            if function in bound:
                return bound[function]
            namespace = dict(function.__globals__)
            if "requests" in namespace:
                namespace["requests"] = _ProviderHTTP(self, source, response_validator, streaming_responses)
            cloned = FunctionType(function.__code__, namespace, function.__name__,
                                  function.__defaults__, function.__closure__)
            cloned.__kwdefaults__ = function.__kwdefaults__
            bound[function] = cloned
            for name in function.__code__.co_names:
                helper = namespace.get(name)
                if callable(helper) and str(getattr(helper, "__module__", "")).startswith("akshare."):
                    namespace[name] = bind(helper)
            return cloned
        operation = bind(operation)
        try:
            return operation(*args, **kwargs)
        except SourceError:
            raise
        except Exception as exc:
            had_requests = len(self.events.get(source, [])) > event_start
            self.events.setdefault(source, []).append({"source": source, "attempts": 0 if had_requests else 1,
                "elapsed_ms": 0 if had_requests else round((time.monotonic() - started) * 1000, 2),
                "retrieved_at": datetime.now(BJ_TZ).isoformat(), "error_type": classify_exception(exc),
                "status": "source_failure", "detail": str(exc)})
            raise
        finally:
            for response in streaming_responses:
                response.close()

    def result(self, result: dict, *, error: Exception | None = None, events: list | None = None) -> dict:
        source = result["source"]
        result.setdefault("coverage", {"query_range": result.get("query_range", "source-defined")})
        if events is None:
            all_events = self.events.get(source, [])
            events = all_events[self.reported.get(source, 0):]
            self.reported[source] = len(all_events)
        if not events and isinstance(error, SourceError):
            events = error.result.get("request_log") or [error.result]
        result.setdefault("attempts", sum(item["attempts"] for item in events))
        result.setdefault("elapsed_ms", round(sum(item["elapsed_ms"] for item in events), 2))
        result.setdefault("retrieved_at", datetime.now(BJ_TZ).isoformat())
        result.setdefault("request_log", events)
        result.setdefault("run_id", self.run_id)
        result.setdefault("runtime_version", RUNTIME_VERSION)
        result.setdefault("fallback_from", [])
        for key in ("http_status", "error_type", "cooldown_until"):
            latest = next((event[key] for event in reversed(events) if event.get(key) is not None), None)
            if latest is not None:
                result.setdefault(key, latest)
        result.setdefault("http_status", None)
        result.setdefault("error_type", "")
        if error is not None:
            kind = classify_exception(error)
            result.update(error_type=kind, detail=f"{type(error).__name__}: {error}",
                          status=error.result["status"] if isinstance(error, SourceError) else
                          "malformed" if kind == "parse_error" else "source_failure")
        return result

    def run_chain(self, source_specs, invoke) -> tuple[object | None, list[dict]]:
        results = []
        partial_payload = None
        partial_result = None
        for spec in source_specs:
            payload, result = invoke(spec)
            results.append(result)
            if result["status"] == "partial" and payload and (
                    partial_payload is None or len(payload) > len(partial_payload)):
                partial_payload, partial_result = payload, result
            if result["status"] == "ok":
                result["selected_for_payload"] = True
                if len(results) > 1:
                    result["fallback_from"] = [item["source"] for item in results[:-1]]
                return payload, results
        if partial_result is not None:
            partial_result["selected_for_payload"] = True
            partial_result["fallback_from"] = [item["source"] for item in results[:results.index(partial_result)]]
        return partial_payload, results


class _ProviderHTTP:
    """AKShare's module-local requests facade; never replace the real module."""
    def __init__(self, runtime: SourceRuntime, source: str, validator=None, streaming_responses=None):
        self.runtime, self.source = runtime, source
        self.validator = validator
        self.streaming_responses = streaming_responses

    def __getattr__(self, name):
        if name in {"get", "post", "head"}:
            get = self.runtime.http(self.source, getattr(requests, name))
            def request(url, **kwargs):
                response = get(url, **kwargs)
                if kwargs.get("stream") and self.streaming_responses is not None:
                    self.streaming_responses.append(response)
                if self.validator is not None:
                    try:
                        self.validator(url, response, kwargs)
                    except Exception:
                        response.close()
                        raise
                return response
            return request
        return getattr(requests, name)
