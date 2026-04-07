from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class StopCategory(str, Enum):
    STREAM_TIMEOUT = "STREAM_TIMEOUT"
    TOOL_SCHEMA_ERROR = "TOOL_SCHEMA_ERROR"
    OUTPUT_CORRUPTION = "OUTPUT_CORRUPTION"
    DATA_SHAPE_MISMATCH = "DATA_SHAPE_MISMATCH"
    CAPABILITY_MISMATCH = "CAPABILITY_MISMATCH"
    BACKGROUND_SERVICE = "BACKGROUND_SERVICE"
    SESSION_DEGRADATION = "SESSION_DEGRADATION"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class StopSignal:
    category: StopCategory
    evidence: tuple[str, ...]
    recovery: str
    requires_fresh_session: bool
    matched_categories: tuple[StopCategory, ...]


STOP_PATTERN_MAP: dict[StopCategory, tuple[re.Pattern[str], ...]] = {
    StopCategory.STREAM_TIMEOUT: (
        re.compile(r"SSE read timed out", re.IGNORECASE),
        re.compile(r"review times? out", re.IGNORECASE),
    ),
    StopCategory.TOOL_SCHEMA_ERROR: (
        re.compile(r"invalid arguments", re.IGNORECASE),
        re.compile(r"expected string, received undefined", re.IGNORECASE),
        re.compile(r"subagent_type", re.IGNORECASE),
        re.compile(r"unknown runtime schema", re.IGNORECASE),
    ),
    StopCategory.OUTPUT_CORRUPTION: (
        re.compile(r"^\s*Thinking:", re.IGNORECASE | re.MULTILINE),
        re.compile(r"<(?:parameter|invoke|system)\b", re.IGNORECASE),
        re.compile(r"zsh:1: unmatched", re.IGNORECASE),
        re.compile(r"\}\s*else\s*,\}", re.IGNORECASE),
    ),
    StopCategory.DATA_SHAPE_MISMATCH: (
        re.compile(r"AttributeError: 'str' object has no attribute 'get'", re.IGNORECASE),
        re.compile(r"Traceback \(most recent call last\):", re.IGNORECASE),
        re.compile(r"json.*unexpected", re.IGNORECASE),
    ),
    StopCategory.CAPABILITY_MISMATCH: (
        re.compile(r"can't view images", re.IGNORECASE),
        re.compile(r"don't have multimodal", re.IGNORECASE),
        re.compile(r"browser or app may not be secure", re.IGNORECASE),
        re.compile(r"couldn't sign you in", re.IGNORECASE),
    ),
    StopCategory.BACKGROUND_SERVICE: (
        re.compile(r"python\s+-m\s+http\.server\b", re.IGNORECASE),
        re.compile(r"\b(?:npm|pnpm|yarn)\s+run\s+dev\b", re.IGNORECASE),
        re.compile(r"\buvicorn\b", re.IGNORECASE),
        re.compile(r"\bgunicorn\b", re.IGNORECASE),
        re.compile(r"\bflask\s+run\b", re.IGNORECASE),
        re.compile(r"\bnext\s+dev\b", re.IGNORECASE),
        re.compile(r"\bvite\b", re.IGNORECASE),
        re.compile(r"^\$\s+.+\s&\s*$", re.IGNORECASE | re.MULTILINE),
    ),
}


def _extract_evidence(text: str, patterns: tuple[re.Pattern[str], ...]) -> tuple[str, ...]:
    evidence: list[str] = []
    for line in text.splitlines():
        if any(pattern.search(line) for pattern in patterns):
            stripped = line.strip()
            if stripped:
                evidence.append(stripped)
    return tuple(dict.fromkeys(evidence))


def _recovery_for(category: StopCategory) -> tuple[str, bool]:
    recovery_map = {
        StopCategory.STREAM_TIMEOUT: (
            "Save a bounded checkpoint, restart in a fresh session, and retry only the smallest unresolved unit.",
            True,
        ),
        StopCategory.TOOL_SCHEMA_ERROR: (
            "Stop speculative subagent/tool retries, record the missing runtime field, and either use a known-good path or restart fresh.",
            True,
        ),
        StopCategory.OUTPUT_CORRUPTION: (
            "Discard the malformed output, save a concise stop report, and continue in a fresh session with a bounded next action.",
            True,
        ),
        StopCategory.DATA_SHAPE_MISMATCH: (
            "Inspect the real data shape first, then rerun the bounded analysis with a parser that matches the artifact schema.",
            False,
        ),
        StopCategory.CAPABILITY_MISMATCH: (
            "Use a capability that the current runtime actually supports, or switch to a manual or alternate path without looping.",
            False,
        ),
        StopCategory.BACKGROUND_SERVICE: (
            "Treat the service launch as complete once the listening port is confirmed, report the local URL, and detach stdout/stderr instead of continuing to monitor the server process.",
            False,
        ),
        StopCategory.SESSION_DEGRADATION: (
            "Stop the current session, save a stop report with evidence, and resume from a fresh session with one bounded next step.",
            True,
        ),
        StopCategory.UNKNOWN: (
            "Capture the transcript snippet and classify it manually before retrying.",
            False,
        ),
    }
    return recovery_map[category]


def classify_stop(raw_text: str) -> StopSignal:
    text = raw_text.strip()
    if not text:
        recovery, fresh = _recovery_for(StopCategory.UNKNOWN)
        return StopSignal(
            category=StopCategory.UNKNOWN,
            evidence=(),
            recovery=recovery,
            requires_fresh_session=fresh,
            matched_categories=(),
        )

    matched: list[StopCategory] = []
    evidence: list[str] = []
    for category, patterns in STOP_PATTERN_MAP.items():
        category_evidence = _extract_evidence(text, patterns)
        if category_evidence:
            matched.append(category)
            evidence.extend(category_evidence)

    unique_matched = tuple(dict.fromkeys(matched))
    if len(unique_matched) >= 2 or text.lower().count("invalid arguments") >= 2:
        recovery, fresh = _recovery_for(StopCategory.SESSION_DEGRADATION)
        return StopSignal(
            category=StopCategory.SESSION_DEGRADATION,
            evidence=tuple(dict.fromkeys(evidence)),
            recovery=recovery,
            requires_fresh_session=fresh,
            matched_categories=unique_matched,
        )

    category = unique_matched[0] if unique_matched else StopCategory.UNKNOWN
    recovery, fresh = _recovery_for(category)
    return StopSignal(
        category=category,
        evidence=tuple(dict.fromkeys(evidence)),
        recovery=recovery,
        requires_fresh_session=fresh,
        matched_categories=unique_matched,
    )


def format_stop_report(signal: StopSignal, *, unit_name: str = "current unit") -> str:
    evidence_lines = "\n".join(f"- {item}" for item in signal.evidence[:4]) or "- none captured"
    matched = ", ".join(category.value for category in signal.matched_categories) or signal.category.value
    return (
        f"Current unit: {unit_name}\n"
        f"Stop signal: {signal.category.value}\n"
        f"Matched categories: {matched}\n"
        "Evidence:\n"
        f"{evidence_lines}\n"
        f"Next recovery step: {signal.recovery}"
    )
