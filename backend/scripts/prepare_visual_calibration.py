"""Build the verified Calibration manifest without reading holdout answers."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.visual_calibration import (
    CalibrationPaths,
    locate_annotated_root,
    write_manifest,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).parents[2])
    parser.add_argument("--database", type=Path)
    args = parser.parse_args()
    root = args.project_root.resolve()
    annotated, alias = locate_annotated_root(root)
    target = write_manifest(CalibrationPaths(
        project_root=root,
        annotated_root=annotated,
        output_root=root / "evaluation" / "visual-analysis",
        database_path=(args.database or root / "backend" / "design_assets.db").resolve(),
    ))
    print(f"source={alias}")
    print(f"manifest={target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
