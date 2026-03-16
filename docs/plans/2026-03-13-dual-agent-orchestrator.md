# Dual Agent Orchestrator Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a reusable Python-based orchestration layer for OpenCode that coordinates a GLM builder agent and a GPT reviewer agent through a dual-agent workflow.

**Architecture:** The project will provide a CLI entrypoint, provider adapters, workflow state models, and a small orchestration engine that can run across repositories using global OpenCode configuration. The first milestone focuses on a portable scaffold with typed configuration, workflow contracts, and a command-generation layer rather than a full end-to-end external API integration.

**Tech Stack:** Python 3.12, uv, Typer, Pydantic, pytest

---

### Task 1: Scaffold Python Package

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `src/dual_agents/__init__.py`
- Create: `src/dual_agents/cli.py`
- Create: `tests/test_cli.py`

**Step 1: Write the failing test**

```python
from typer.testing import CliRunner

from dual_agents.cli import app


def test_cli_shows_help():
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "dual-agent workflow" in result.stdout.lower()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py::test_cli_shows_help -v`
Expected: FAIL with `ModuleNotFoundError` or missing app implementation

**Step 3: Write minimal implementation**

```python
import typer

app = typer.Typer(help="CLI for the dual-agent workflow.")
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli.py::test_cli_shows_help -v`
Expected: PASS

**Step 5: Commit**

```bash
git add pyproject.toml README.md src/dual_agents/__init__.py src/dual_agents/cli.py tests/test_cli.py
git commit -m "feat: scaffold dual agent cli"
```

### Task 2: Model Workflow Configuration

**Files:**
- Create: `src/dual_agents/config.py`
- Create: `tests/test_config.py`

**Step 1: Write the failing test**

```python
from dual_agents.config import ProviderConfig


def test_provider_config_requires_model():
    ProviderConfig(name="glm")
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py::test_provider_config_requires_model -v`
Expected: FAIL with validation error or missing implementation

**Step 3: Write minimal implementation**

```python
from pydantic import BaseModel


class ProviderConfig(BaseModel):
    name: str
    model: str
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py::test_provider_config_requires_model -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/dual_agents/config.py tests/test_config.py
git commit -m "feat: add workflow configuration models"
```

### Task 3: Encode Workflow Stages

**Files:**
- Create: `src/dual_agents/workflow.py`
- Create: `tests/test_workflow.py`

**Step 1: Write the failing test**

```python
from dual_agents.workflow import WorkflowStage, next_stage


def test_workflow_loops_back_on_blocking_review():
    assert next_stage(WorkflowStage.CRITICAL_REVIEW, has_blocking_issues=True) == WorkflowStage.IMPLEMENTATION
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_workflow.py::test_workflow_loops_back_on_blocking_review -v`
Expected: FAIL because workflow stage logic does not exist yet

**Step 3: Write minimal implementation**

```python
from enum import Enum


class WorkflowStage(str, Enum):
    IMPLEMENTATION = "implementation"
    CRITICAL_REVIEW = "critical_review"


def next_stage(stage: WorkflowStage, has_blocking_issues: bool = False) -> WorkflowStage:
    if stage == WorkflowStage.CRITICAL_REVIEW and has_blocking_issues:
        return WorkflowStage.IMPLEMENTATION
    return stage
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_workflow.py::test_workflow_loops_back_on_blocking_review -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/dual_agents/workflow.py tests/test_workflow.py
git commit -m "feat: add workflow stage transitions"
```

### Task 4: Generate OpenCode Assets

**Files:**
- Create: `src/dual_agents/opencode_assets.py`
- Create: `tests/test_opencode_assets.py`

**Step 1: Write the failing test**

```python
from dual_agents.opencode_assets import build_command_markdown


def test_build_command_mentions_dual_trigger():
    markdown = build_command_markdown()
    assert "/dual" in markdown
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_opencode_assets.py::test_build_command_mentions_dual_trigger -v`
Expected: FAIL because asset generator is missing

**Step 3: Write minimal implementation**

```python
def build_command_markdown() -> str:
    return "# /dual\n"
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_opencode_assets.py::test_build_command_mentions_dual_trigger -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/dual_agents/opencode_assets.py tests/test_opencode_assets.py
git commit -m "feat: add opencode asset generator"
```

### Task 5: Document Setup and Required Secrets

**Files:**
- Modify: `README.md`
- Create: `.env.example`

**Step 1: Write the failing test**

```python
from pathlib import Path


def test_env_example_mentions_glm_and_openai():
    content = Path(".env.example").read_text()
    assert "GLM_API_KEY" in content
    assert "OPENAI_API_KEY" in content
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_readme_contract.py::test_env_example_mentions_glm_and_openai -v`
Expected: FAIL because `.env.example` does not exist yet

**Step 3: Write minimal implementation**

```text
GLM_API_KEY=
OPENAI_API_KEY=
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_readme_contract.py::test_env_example_mentions_glm_and_openai -v`
Expected: PASS

**Step 5: Commit**

```bash
git add README.md .env.example
git commit -m "docs: add setup instructions and secret contract"
```
