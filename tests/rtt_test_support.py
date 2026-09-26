"""RTT 참조 엔진 경로를 일반 체크아웃과 Git worktree에서 찾는다."""

import os
from pathlib import Path


def rules_path(test_file: str) -> Path:
    override = os.environ.get("RTT_RULES_PATH")
    if override:
        return Path(override)
    root = Path(test_file).resolve().parents[1]
    folder = "Rally the Troops_paths-of-glory-master"
    for base in (root, root.parent.parent):
        candidate = base / folder / "rules.js"
        if candidate.is_file():
            return candidate
    return root / folder / "rules.js"
