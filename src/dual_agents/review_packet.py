from __future__ import annotations

import re
from dataclasses import dataclass, replace

from dual_agents.config import WorkflowConfig


@dataclass(frozen=True)
class ReviewPacket:
    decision_name: str
    decision_needed: str
    evidence_files: tuple[str, ...]
    facts_observed: tuple[str, ...]
    open_questions: tuple[str, ...]


@dataclass(frozen=True)
class NarrowingResult:
    packet: ReviewPacket
    was_narrowed: bool
    dropped_file_count: int
    dropped_fact_count: int
    dropped_question_count: int


SECTION_FIELDS = {
    "decision needed": "decision_needed",
    "evidence files": "evidence_files",
    "facts observed": "facts_observed",
    "open questions": "open_questions",
}
TITLE_PATTERN = re.compile(r"^\s*#\s+Review Request:\s*(.+?)\s*$", re.IGNORECASE)
SECTION_PATTERN = re.compile(r"^\s*##\s+(.+?)\s*$")
LIST_ITEM_PATTERN = re.compile(r"^\s*(?:[-*]|\d+\.)\s+(.*\S)\s*$")
WHITESPACE_PATTERN = re.compile(r"\s+")
FAILURE_TERMS = ("fail", "failing", "failure", "error", "regression", "blocked", "timeout")
TEST_TERMS = ("test", "pytest", "verification", "validated")
DIFF_TERMS = ("diff", "patch", "git diff")
ARTIFACT_TERMS = ("artifact", "final-review", "lead-review", "run-state", "builder_result")


def estimate_packet_size(packet: ReviewPacket) -> int:
    return len(render_review_packet(packet))


def parse_review_packet(raw_request: str) -> ReviewPacket | None:
    lines = raw_request.splitlines()
    decision_name: str | None = None
    sections: dict[str, list[str]] = {field: [] for field in SECTION_FIELDS.values()}
    current_field: str | None = None

    for line in lines:
        if decision_name is None:
            title_match = TITLE_PATTERN.match(line)
            if title_match:
                decision_name = _clean_text(title_match.group(1))
                continue
        section_match = SECTION_PATTERN.match(line)
        if section_match:
            current_field = SECTION_FIELDS.get(section_match.group(1).strip().lower())
            continue
        if current_field is None:
            continue
        item = _extract_item(line)
        if item is not None:
            sections[current_field].append(item)

    if not decision_name:
        return None

    decision_candidates = _dedupe_items(sections["decision_needed"], truncate_to=320)
    if not decision_candidates:
        return None

    return ReviewPacket(
        decision_name=decision_name,
        decision_needed=" ".join(decision_candidates),
        evidence_files=tuple(sections["evidence_files"]),
        facts_observed=tuple(sections["facts_observed"]),
        open_questions=tuple(sections["open_questions"]),
    )


def build_review_packet(
    *,
    config: WorkflowConfig,
    decision_name: str,
    decision_needed: str,
    evidence_files: list[str],
    facts_observed: list[str],
    open_questions: list[str],
) -> ReviewPacket:
    packet = ReviewPacket(
        decision_name=_clean_text(decision_name),
        decision_needed=_clean_text(decision_needed),
        evidence_files=tuple(_rank_evidence_files(_dedupe_items(evidence_files, truncate_to=None))),
        facts_observed=tuple(_rank_facts(_dedupe_items(facts_observed, truncate_to=280))),
        open_questions=tuple(_rank_questions(_dedupe_items(open_questions, truncate_to=220))),
    )
    return narrow_review_packet(config=config, packet=packet, attempt=1).packet


def narrow_review_packet(
    *,
    config: WorkflowConfig,
    packet: ReviewPacket,
    attempt: int,
) -> NarrowingResult:
    narrowed = packet
    original_files = len(packet.evidence_files)
    original_facts = len(packet.facts_observed)
    original_questions = len(packet.open_questions)

    file_limit = max(1, config.review_packet_max_files - max(0, attempt - 1))
    if len(narrowed.evidence_files) > file_limit:
        narrowed = replace(narrowed, evidence_files=narrowed.evidence_files[:file_limit])

    size_limit = max(1200, config.review_packet_target_max_chars - max(0, attempt - 1) * 1000)
    while estimate_packet_size(narrowed) > size_limit and len(narrowed.facts_observed) > 2:
        narrowed = replace(narrowed, facts_observed=narrowed.facts_observed[:-1])
    while estimate_packet_size(narrowed) > size_limit and len(narrowed.open_questions) > 1:
        narrowed = replace(narrowed, open_questions=narrowed.open_questions[:-1])
    while estimate_packet_size(narrowed) > size_limit and len(narrowed.evidence_files) > 1:
        narrowed = replace(narrowed, evidence_files=narrowed.evidence_files[:-1])

    return NarrowingResult(
        packet=narrowed,
        was_narrowed=narrowed != packet,
        dropped_file_count=original_files - len(narrowed.evidence_files),
        dropped_fact_count=original_facts - len(narrowed.facts_observed),
        dropped_question_count=original_questions - len(narrowed.open_questions),
    )


def render_review_packet(packet: ReviewPacket) -> str:
    evidence_block = "\n".join(f"- {path}" for path in packet.evidence_files)
    facts_block = "\n".join(f"- {fact}" for fact in packet.facts_observed)
    questions_block = "\n".join(
        f"{index}. {question}" for index, question in enumerate(packet.open_questions, start=1)
    )
    return (
        f"# Review Request: {packet.decision_name}\n\n"
        f"## Decision Needed\n"
        f"- {packet.decision_needed}\n\n"
        f"## Evidence Files\n"
        f"{evidence_block}\n\n"
        f"## Facts Observed\n"
        f"{facts_block}\n\n"
        f"## Open Questions\n"
        f"{questions_block}"
    )


def _extract_item(line: str) -> str | None:
    match = LIST_ITEM_PATTERN.match(line)
    if match:
        return _clean_text(match.group(1))
    cleaned = _clean_text(line)
    return cleaned or None


def _clean_text(value: str) -> str:
    return WHITESPACE_PATTERN.sub(" ", value).strip()


def _dedupe_items(values: list[str], *, truncate_to: int | None) -> list[str]:
    seen: set[str] = set()
    cleaned_items: list[str] = []
    for value in values:
        cleaned = _clean_text(value)
        if not cleaned:
            continue
        if truncate_to is not None and len(cleaned) > truncate_to:
            cleaned = cleaned[: truncate_to - 3].rstrip() + "..."
        dedupe_key = cleaned.casefold()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        cleaned_items.append(cleaned)
    return cleaned_items


def _rank_evidence_files(values: list[str]) -> list[str]:
    return sorted(values, key=_evidence_sort_key)


def _rank_facts(values: list[str]) -> list[str]:
    return sorted(values, key=_fact_sort_key)


def _rank_questions(values: list[str]) -> list[str]:
    return sorted(values, key=_question_sort_key)


def _evidence_sort_key(value: str) -> tuple[int, int, str]:
    lowered = value.casefold()
    score = 0
    if "final-review.txt" in lowered or "lead-review.txt" in lowered:
        score -= 80
    if "run-state.json" in lowered:
        score -= 70
    if any(term in lowered for term in DIFF_TERMS):
        score -= 60
    if any(term in lowered for term in TEST_TERMS):
        score -= 50
    if "builder" in lowered:
        score -= 45
    if any(term in lowered for term in ARTIFACT_TERMS):
        score -= 35
    if lowered.endswith(".md"):
        score += 5
    return (score, len(value), lowered)


def _fact_sort_key(value: str) -> tuple[int, int, str]:
    lowered = value.casefold()
    score = 0
    if any(term in lowered for term in FAILURE_TERMS):
        score -= 80
    if any(term in lowered for term in TEST_TERMS):
        score -= 65
    if any(term in lowered for term in DIFF_TERMS):
        score -= 95
    if any(term in lowered for term in ARTIFACT_TERMS):
        score -= 45
    if "current unit" in lowered or "bounded unit" in lowered:
        score -= 40
    if "proved" in lowered or "proven" in lowered or "not proven" in lowered:
        score -= 35
    return (score, len(value), lowered)


def _question_sort_key(value: str) -> tuple[int, int, str]:
    lowered = value.casefold()
    score = 0
    if "next bounded unit" in lowered or "can the next unit" in lowered:
        score -= 50
    if "blocking" in lowered or "blocker" in lowered:
        score -= 45
    if "evidence" in lowered:
        score -= 35
    if "delivery" in lowered or "proof" in lowered:
        score -= 30
    return (score, len(value), lowered)
