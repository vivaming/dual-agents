import subprocess
import sys
from pathlib import Path

from dual_agents.cli import build_review_validator_script


VALID_LEAD_REVIEW = """
1. Verdict: APPROVED
2. Current unit status: NOT_STARTED
3. Blocking issues: None
4. Non-blocking issues: None
5. Cause classification: NOT_APPLICABLE
6. Delivery proof status: NOT_APPLICABLE
7. Next bounded unit may start: YES
8. Suggested next action: Start implementation for the bounded unit.
"""

VALID_FINAL_REVIEW = """
1. Verdict: APPROVED
2. Current unit status: PASS
3. Blocking issues: None
4. Non-blocking issues: None
5. Cause classification: NOT_APPLICABLE
6. Delivery proof status: PROVEN
7. Next bounded unit may start: YES
8. Suggested next action: Close the unit and move to the next bounded task.
"""


def _write_validator(tmp_path: Path) -> Path:
    validator_path = tmp_path / "validate_review.py"
    validator_path.write_text(build_review_validator_script())
    return validator_path


def test_review_validator_accepts_valid_lead_review(tmp_path: Path) -> None:
    validator_path = _write_validator(tmp_path)
    review_path = tmp_path / "lead-review.txt"
    review_path.write_text(VALID_LEAD_REVIEW)

    result = subprocess.run(
        [sys.executable, str(validator_path), "--mode", "lead", "--review-file", str(review_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "OK"


def test_review_validator_rejects_missing_review_file(tmp_path: Path) -> None:
    validator_path = _write_validator(tmp_path)
    review_path = tmp_path / "missing-final-review.txt"

    result = subprocess.run(
        [sys.executable, str(validator_path), "--mode", "final", "--review-file", str(review_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "review artifact not found" in result.stderr


def test_review_validator_rejects_non_passing_final_review(tmp_path: Path) -> None:
    validator_path = _write_validator(tmp_path)
    review_path = tmp_path / "final-review.txt"
    review_path.write_text(VALID_LEAD_REVIEW)

    result = subprocess.run(
        [sys.executable, str(validator_path), "--mode", "final", "--review-file", str(review_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "does not certify a passing unit state" in result.stderr


def test_review_validator_enforces_delivery_proof_requirement(tmp_path: Path) -> None:
    validator_path = _write_validator(tmp_path)
    review_path = tmp_path / "final-review.txt"
    review_path.write_text(VALID_FINAL_REVIEW.replace("PROVEN", "NOT_PROVEN"))

    result = subprocess.run(
        [
            sys.executable,
            str(validator_path),
            "--mode",
            "final",
            "--require-delivery-proof",
            "PROVEN",
            "--review-file",
            str(review_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "expected PROVEN" in result.stderr
