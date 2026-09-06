#!/usr/bin/env python3
"""Create the immutable E2-v0R0_raw_audit snapshot without deleting sources."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE_RESULTS = HERE / "results"
TARGET = HERE / "freezes" / "E2-v0R0_raw_audit"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    if TARGET.exists():
        raise RuntimeError(f"Freeze already exists; refusing to overwrite: {TARGET}")
    if not SOURCE_RESULTS.is_dir():
        raise FileNotFoundError(SOURCE_RESULTS)

    (TARGET / "results").mkdir(parents=True)
    copied = []
    for source in sorted(SOURCE_RESULTS.iterdir()):
        if not source.is_file():
            continue
        destination = TARGET / "results" / source.name
        shutil.copy2(source, destination)
        copied.append(destination)
    for name in ("README.md", "build_empirical_components.py", "verify_empirical_components.py"):
        source = HERE / name
        destination = TARGET / name
        shutil.copy2(source, destination)
        copied.append(destination)

    readme = TARGET / "FROZEN_README.md"
    readme.write_text(
        "# E2-v0R0_raw_audit — frozen\n\n"
        "This is the non-destructive snapshot of the original single-marker-primary "
        "SE(3) audit. It is retained as a failure-mode and provenance baseline.\n\n"
        "`results/e2_hierarchical_components_se3.csv` and especially its `total_sum` "
        "rows are **PROHIBITED as formal E1-v4 replay inputs**. The snapshot used the "
        "per-marker IPPE measurements as the primary pose channel and mixed stable "
        "cross-pose and run effects into a covariance sum. It must not be silently "
        "updated or overwritten.\n",
        encoding="utf-8",
    )
    copied.append(readme)

    manifest = {
        "freeze_id": "E2-v0R0_raw_audit",
        "status": "FROZEN_DO_NOT_OVERWRITE",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_results": str(SOURCE_RESULTS),
        "role": "raw audit and single-marker IPPE failure-mode baseline",
        "formal_e1_v4_input": False,
        "prohibition": "large total_sum is not an authorized E1-v4 input",
        "files": [
            {
                "path": str(path.relative_to(TARGET)).replace("\\", "/"),
                "bytes": path.stat().st_size,
                "sha256": digest(path),
            }
            for path in copied
        ],
    }
    manifest_path = TARGET / "FREEZE_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Created frozen snapshot: {TARGET}")


if __name__ == "__main__":
    main()
