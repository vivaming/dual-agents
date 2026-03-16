from dual_agents.cli import default_workflow_config
from dual_agents.review_packet import build_review_packet, narrow_review_packet, render_review_packet


def test_build_review_packet_limits_files_to_policy() -> None:
    config = default_workflow_config()
    packet = build_review_packet(
        config=config,
        decision_name="Task sequencing",
        decision_needed="Decide whether 12b should precede 12c.",
        evidence_files=[f"/tmp/file-{index}.md" for index in range(8)],
        facts_observed=["fact 1", "fact 2", "fact 3"],
        open_questions=["question 1", "question 2"],
    )
    assert len(packet.evidence_files) == config.review_packet_max_files


def test_narrow_review_packet_drops_more_context_on_later_attempts() -> None:
    config = default_workflow_config()
    packet = build_review_packet(
        config=config,
        decision_name="Scope review",
        decision_needed="Decide whether the scope is valid.",
        evidence_files=[f"/tmp/file-{index}.md" for index in range(5)],
        facts_observed=[f"fact {index}" for index in range(1, 8)],
        open_questions=[f"question {index}" for index in range(1, 5)],
    )
    narrowed = narrow_review_packet(config=config, packet=packet, attempt=2)
    assert narrowed.was_narrowed is True
    assert len(narrowed.packet.evidence_files) <= len(packet.evidence_files)
    assert len(narrowed.packet.facts_observed) <= len(packet.facts_observed)


def test_render_review_packet_uses_decision_template_shape() -> None:
    config = default_workflow_config()
    packet = build_review_packet(
        config=config,
        decision_name="Progression review",
        decision_needed="Determine whether the next unit may start.",
        evidence_files=["/tmp/state.md", "/tmp/review.md"],
        facts_observed=["state says partial", "review note says pass"],
        open_questions=["Can the next bounded unit start?"],
    )
    rendered = render_review_packet(packet)
    assert "# Review Request: Progression review" in rendered
    assert "## Evidence Files" in rendered
    assert "## Open Questions" in rendered
