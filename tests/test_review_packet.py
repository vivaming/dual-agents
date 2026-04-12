from dual_agents.cli import default_workflow_config
from dual_agents.review_packet import build_review_packet, narrow_review_packet, parse_review_packet, render_review_packet


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


def test_parse_review_packet_reads_structured_template_sections() -> None:
    packet = parse_review_packet(
        "# Review Request: Packet hygiene\n\n"
        "## Decision Needed\n"
        "- Decide whether the packet is bounded.\n\n"
        "## Evidence Files\n"
        "- /tmp/a.md\n"
        "- /tmp/b.md\n\n"
        "## Facts Observed\n"
        "- fact 1\n"
        "- fact 2\n\n"
        "## Open Questions\n"
        "1. question 1\n"
        "2. question 2\n"
    )
    assert packet is not None
    assert packet.decision_name == "Packet hygiene"
    assert packet.decision_needed == "Decide whether the packet is bounded."
    assert packet.evidence_files == ("/tmp/a.md", "/tmp/b.md")
    assert packet.open_questions == ("question 1", "question 2")


def test_parse_review_packet_keeps_multiple_decision_constraints() -> None:
    packet = parse_review_packet(
        "# Review Request: Progression gate\n\n"
        "## Decision Needed\n"
        "- Decide whether the unit can advance.\n"
        "- Confirm the current evidence is sufficient.\n"
    )
    assert packet is not None
    assert packet.decision_needed == "Decide whether the unit can advance. Confirm the current evidence is sufficient."


def test_build_review_packet_dedupes_and_truncates_verbose_items() -> None:
    config = default_workflow_config()
    verbose_fact = "fact " + ("x" * 400)
    packet = build_review_packet(
        config=config,
        decision_name="  Review   quality  ",
        decision_needed="Decide whether the same fact appears twice.",
        evidence_files=[" /tmp/a.md ", "/tmp/a.md", "/tmp/b.md"],
        facts_observed=[verbose_fact, verbose_fact],
        open_questions=["  Can the next unit start?  ", "Can the next unit start?"],
    )
    assert packet.decision_name == "Review quality"
    assert packet.evidence_files == ("/tmp/a.md", "/tmp/b.md")
    assert len(packet.facts_observed) == 1
    assert packet.facts_observed[0].endswith("...")
    assert packet.open_questions == ("Can the next unit start?",)


def test_build_review_packet_prioritizes_high_value_evidence_and_facts() -> None:
    config = default_workflow_config()
    packet = build_review_packet(
        config=config,
        decision_name="Review quality",
        decision_needed="Decide whether the current unit can advance.",
        evidence_files=[
            "docs/notes/context.md",
            ".dual-agents/reviews/task-02/final-review.txt",
            ".dual-agents/run-state.json",
            "artifacts/git-diff.patch",
            "logs/pytest-output.txt",
        ],
        facts_observed=[
            "A general note about implementation context.",
            "Pytest failed on the bounded unit verification command.",
            "Current unit final review artifact is still missing.",
            "Git diff shows the bounded remediation touched two files.",
        ],
        open_questions=[
            "What follow-up docs should be updated?",
            "Can the next bounded unit start?",
            "Is there a remaining blocking issue?",
        ],
    )
    assert packet.evidence_files[:4] == (
        ".dual-agents/reviews/task-02/final-review.txt",
        ".dual-agents/run-state.json",
        "artifacts/git-diff.patch",
        "logs/pytest-output.txt",
    )
    assert packet.facts_observed[:3] == (
        "Pytest failed on the bounded unit verification command.",
        "Git diff shows the bounded remediation touched two files.",
        "Current unit final review artifact is still missing.",
    )
    assert packet.open_questions[:2] == (
        "Can the next bounded unit start?",
        "Is there a remaining blocking issue?",
    )
