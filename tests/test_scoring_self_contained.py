"""codeloop/scoring must not import other codeloop modules (it is frozen by tree hash at Phase 3)."""

import ast
from pathlib import Path

SCORING = Path(__file__).resolve().parents[1] / "codeloop" / "scoring"
ALLOWED_THIRD_PARTY = {"pydantic", "yaml"}


def test_scoring_imports_only_stdlib_pydantic_yaml_and_itself():
    import sys

    stdlib = set(sys.stdlib_module_names)
    for path in sorted(SCORING.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                top = name.split(".")[0]
                if name.startswith("codeloop."):
                    assert name.startswith("codeloop.scoring"), f"{path.name} imports {name}"
                else:
                    assert top in stdlib or top in ALLOWED_THIRD_PARTY, f"{path.name} imports {name}"
