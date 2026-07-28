"""Integrity checks for resumable run directories and baseline comparisons."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def verify_run(run_dir: Path) -> dict[str, Any]:
    manifest = pd.read_parquet(run_dir / "task_manifest.parquet")
    status = pd.read_parquet(run_dir / "task_status.parquet")
    exact_path = run_dir / "raw" / "exact_results.parquet"
    quantized_path = run_dir / "raw" / "quantized_results.parquet"
    exact = pd.read_parquet(exact_path) if exact_path.exists() else pd.DataFrame()
    quantized = pd.read_parquet(quantized_path) if quantized_path.exists() else pd.DataFrame()
    raw = pd.concat([exact, quantized], ignore_index=True)
    errors: list[str] = []
    if not status.status.eq("complete").all():
        errors.append("not every manifest task is complete")
    if raw.task_id.duplicated().any() if "task_id" in raw else bool(len(manifest)):
        errors.append("raw task IDs are missing or duplicated")
    if set(raw.get("task_id", [])) != set(manifest.task_id):
        errors.append("manifest and raw task IDs differ")
    if not raw.empty:
        joined = raw.merge(manifest, on="task_id", suffixes=("", "_manifest"), how="inner")
        if len(joined) != len(manifest):
            errors.append("raw rows do not join one-to-one to manifest")
        for seed in ("workload_seed", "tie_seed", "quantization_seed"):
            manifest_column = f"{seed}_manifest"
            if seed in joined and manifest_column in joined and not joined[seed].eq(joined[manifest_column]).all():
                errors.append(f"{seed} differs from manifest")
        if (
            "raw_schema_version" in manifest
            and "raw_schema_version" in raw
            and not raw.raw_schema_version.eq(
                manifest.set_index("task_id").loc[raw.task_id, "raw_schema_version"].to_numpy()
            ).all()
        ):
            errors.append("raw schema versions differ from manifest")
        if "workload_id" in raw and raw.workload_id.isna().any():
            errors.append("schema-v2 rows have missing workload IDs")
    hashes = {}
    for path in (exact_path, quantized_path):
        if path.exists():
            hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"run_dir": str(run_dir), "ok": not errors, "errors": errors, "raw_hashes": hashes, "task_count": len(manifest)}


def compare_baseline(left_dir: Path, right_dir: Path, tolerance: float = 1e-12) -> dict[str, Any]:
    """Compare common raw tasks and report semantic/schema drift without mutation."""
    report: dict[str, Any] = {"left": str(left_dir), "right": str(right_dir), "tables": {}}
    for name in ("exact_results.parquet", "quantized_results.parquet"):
        left = left_dir / "raw" / name
        right = right_dir / "raw" / name
        if not left.exists() or not right.exists():
            continue
        a = pd.read_parquet(left).set_index("task_id")
        b = pd.read_parquet(right).set_index("task_id")
        common = a.index.intersection(b.index)
        numeric = [column for column in a.columns.intersection(b.columns) if pd.api.types.is_numeric_dtype(a[column])]
        different = {}
        for column in numeric:
            x, y = a.loc[common, column], b.loc[common, column]
            mask = ~np.isclose(x.fillna(0), y.fillna(0), atol=tolerance, rtol=0, equal_nan=True)
            if mask.any():
                different[column] = int(mask.sum())
        report["tables"][name] = {
            "common_task_ids": len(common), "exact_numeric_matches": not different,
            "numeric_differences": different,
            "semantic_drift": sorted(set(a.columns) ^ set(b.columns)),
        }
    return report
