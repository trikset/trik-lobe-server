# Copyright 2026 Iakov Kirilenko. Licensed under the Apache License, Version 2.0.

from pathlib import Path

import yaml

_ROOT = Path(__file__).parent.parent
_WORKFLOW = _ROOT / ".github/workflows/python-app.yml"
_README = _ROOT / "README.md"


def _release_files() -> list[str]:
    data = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    steps = data["jobs"]["release"]["steps"]
    publish = next(step for step in steps if step.get("name") == "Publish draft release")
    return publish["with"]["files"].splitlines()


def test_release_artifact_names_documented_in_readme() -> None:
    """Renaming release assets without updating README must fail CI."""
    readme = _README.read_text(encoding="utf-8")
    missing = [name for name in _release_files() if name.replace("${{ github.ref_name }}", "v26.08.03") not in readme]
    assert not missing, f"Release assets missing from README.md: {missing}"
