"""No em dashes in anything a reader sees.

They set a clause apart with a mark instead of a sentence, and across a report
they piled up: the InaRISK reading alone carried one per hazard layer, nine to a
page. Rewriting each as its own sentence reads the same and looks deliberate.

This guards the strings the API produces. Docstrings and comments are exempt —
they are for whoever reads the code, not for whoever reads the report. So is the
SQL, where the mark appears inside a query comment.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

EM_DASH = "—"
EN_DASH = "–"

API = Path(__file__).resolve().parent.parent / "api"


def user_facing_strings() -> list[tuple[Path, int, str]]:
    """Every string literal in `api/` that is not a docstring or a SQL body."""
    found: list[tuple[Path, int, str]] = []
    for path in sorted(API.rglob("*.py")):
        tree = ast.parse(path.read_text())
        docstrings = {
            ast.get_docstring(node, clean=False)
            for node in ast.walk(tree)
            if isinstance(
                node,
                (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
            )
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if node.value in docstrings:
                continue
            # A SQL body carries its own comments, which are not report copy.
            if "SELECT" in node.value or "WITH " in node.value:
                continue
            found.append((path, node.lineno, node.value))
    return found


@pytest.mark.parametrize(
    ("dash", "name"),
    [
        pytest.param(EM_DASH, "em dash", id="em-dash"),
        pytest.param(EN_DASH, "en dash", id="en-dash"),
    ],
)
def test_no_dash_reaches_the_reader(dash: str, name: str) -> None:
    offenders = [
        f"{path.relative_to(API.parent)}:{line} {text.strip()[:60]}"
        for path, line, text in user_facing_strings()
        if dash in text
    ]

    assert not offenders, f"{name} in report copy:\n  " + "\n  ".join(offenders)


def test_the_scan_actually_finds_strings() -> None:
    """A guard that silently matches nothing guards nothing."""
    assert len(user_facing_strings()) > 200
