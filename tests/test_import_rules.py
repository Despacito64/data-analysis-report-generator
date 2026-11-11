"""Enforce architectural import layering rules across all da_agent packages."""

import ast
from pathlib import Path

import pytest


def get_imported_modules(py_file: Path) -> set[str]:
    """Parse a Python source file with AST and extract all top-level and relative module imports."""
    with py_file.open("r", encoding="utf-8") as f:
        try:
            tree = ast.parse(f.read(), filename=str(py_file))
        except SyntaxError:
            return set()

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


def test_contracts_imports_nothing_from_da_agent() -> None:
    """Layer 1: contracts must not import anything from da_agent."""
    contracts_dir = Path("src/da_agent/contracts")
    if not contracts_dir.exists():
        return

    for py_file in contracts_dir.glob("*.py"):
        imported = get_imported_modules(py_file)
        for mod in imported:
            if mod.startswith("da_agent.") and not mod.startswith("da_agent.contracts"):
                pytest.fail(f"Layer 1 violation in {py_file}: imports '{mod}'")


def test_core_imports_only_contracts() -> None:
    """Layer 2: core may only import da_agent.contracts."""
    core_dir = Path("src/da_agent/core")
    if not core_dir.exists():
        return

    disallowed_prefixes = (
        "da_agent.data",
        "da_agent.validation",
        "da_agent.tools",
        "da_agent.agent",
        "da_agent.reports",
        "da_agent.pipeline",
    )
    for py_file in core_dir.glob("*.py"):
        imported = get_imported_modules(py_file)
        for mod in imported:
            for dis in disallowed_prefixes:
                if mod.startswith(dis):
                    pytest.fail(f"Layer 2 violation in {py_file}: imports '{mod}'")


def test_data_imports_only_contracts_and_core() -> None:
    """Layer 3: data may only import contracts and core."""
    data_dir = Path("src/da_agent/data")
    if not data_dir.exists():
        return

    disallowed_prefixes = (
        "da_agent.validation",
        "da_agent.tools",
        "da_agent.agent",
        "da_agent.reports",
        "da_agent.pipeline",
    )
    for py_file in data_dir.glob("*.py"):
        imported = get_imported_modules(py_file)
        for mod in imported:
            for dis in disallowed_prefixes:
                if mod.startswith(dis):
                    pytest.fail(f"Layer 3 violation in {py_file}: imports '{mod}'")


def test_validation_never_imports_tools() -> None:
    """Layer 4: validation must NEVER import da_agent.tools."""
    val_dir = Path("src/da_agent/validation")
    if not val_dir.exists():
        return

    for py_file in val_dir.glob("*.py"):
        imported = get_imported_modules(py_file)
        for mod in imported:
            if mod.startswith("da_agent.tools"):
                pytest.fail(f"Validation layer rule violation in {py_file}: imports '{mod}'")


def test_tools_imports_only_allowed_layers() -> None:
    """Layer 5: tools may only import contracts, core, data, and validation."""
    tools_dir = Path("src/da_agent/tools")
    if not tools_dir.exists():
        return

    disallowed_prefixes = (
        "da_agent.agent",
        "da_agent.reports",
        "da_agent.pipeline",
    )
    for py_file in tools_dir.glob("*.py"):
        imported = get_imported_modules(py_file)
        for mod in imported:
            for dis in disallowed_prefixes:
                if mod.startswith(dis):
                    pytest.fail(f"Layer 5 violation in {py_file}: imports '{mod}'")


def test_oracle_independence() -> None:
    """Oracle must import no tool, agent, validation or report code."""
    oracle_file = Path("evaluation/oracle.py")
    if not oracle_file.exists():
        return

    imported = get_imported_modules(oracle_file)
    forbidden = (
        "da_agent.tools",
        "da_agent.agent",
        "da_agent.validation",
        "da_agent.reports",
    )
    for mod in imported:
        for f in forbidden:
            if mod.startswith(f):
                pytest.fail(f"Oracle independence violation in {oracle_file}: imports '{mod}'")


def test_planner_independence() -> None:
    """Planner must never import evaluation, oracle, or baseline templates."""
    planner_file = Path("src/da_agent/agent/planner.py")
    if not planner_file.exists():
        return

    imported = get_imported_modules(planner_file)
    forbidden = (
        "evaluation",
        "da_agent.agent.baseline",
    )
    for mod in imported:
        for f in forbidden:
            if mod.startswith(f):
                pytest.fail(f"Planner independence violation in {planner_file}: imports '{mod}'")

    # AST check: planner functions must never have 'question_id' parameter
    with planner_file.open("r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=str(planner_file))

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            arg_names = [arg.arg for arg in node.args.args + node.args.kwonlyargs]
            if "question_id" in arg_names:
                pytest.fail(
                    f"Planner function '{node.name}' violates rule: must never see 'question_id'"
                )
