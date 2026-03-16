from __future__ import annotations

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


def estimate_packet_size(packet: ReviewPacket) -> int:
    return len(render_review_packet(packet))


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
        decision_name=decision_name.strip(),
        decision_needed=decision_needed.strip(),
        evidence_files=tuple(path.strip() for path in evidence_files if path.strip()),
        facts_observed=tuple(fact.strip() for fact in facts_observed if fact.strip()),
        open_questions=tuple(question.strip() for question in open_questions if question.strip()),
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
