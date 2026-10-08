"""Selection stage: read the cleaning summary, keep usable stars, stage them for the period search."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pandas as pd

from . import settings as S
from . import criteria
from .. import resume as R


def place(src: Path, dst: Path) -> None:
    if dst.exists():
        if not getattr(S, 'FORCE_RERUN', False) and R.digest(src) == R.digest(dst):
            return
        dst.unlink()
    if S.LINK_INSTEAD_OF_COPY:
        try:
            os.link(src, dst)
            return
        except OSError:
            pass
    shutil.copy2(src, dst)


def main() -> pd.DataFrame:
    cleaned = Path(S.CLEANED_DIR)
    selected_dir = Path(S.SELECTED_DIR)
    summary_path = cleaned / S.SUMMARY_NAME
    if not summary_path.exists():
        raise FileNotFoundError(f"Cleaning summary not found: {summary_path} (run the clean stage first)")
    summary = pd.read_csv(summary_path, dtype={"gaia_dr3": str})
    table = criteria.evaluate(summary)

    selected_dir.mkdir(parents=True, exist_ok=True)
    desired = set(table.loc[table['selected'], 'cleaned_file'].astype(str))
    for old in selected_dir.glob("*_cleaned.csv"):
        if old.name not in desired:
            old.unlink()
    n_placed = 0
    for _, row in table[table["selected"]].iterrows():
        src = Path(str(row.get("cleaned_path", "")))
        if not src.exists():
            src = cleaned / str(row.get("cleaned_file", ""))
        if not src.is_file():
            raise FileNotFoundError(f"Selected light curve is missing: {src}")
        if src.is_file():
            place(src, selected_dir / src.name)
            n_placed += 1

    table.to_csv(cleaned / "source_selection.csv", index=False)
    table[table["selected"]].to_csv(selected_dir / "selected_sources.csv", index=False)
    counts = (
        table.loc[~table["selected"], "selection_reasons"].str.split(";").explode().value_counts()
    )
    counts.rename_axis("reason").reset_index(name="n_sources").to_csv(
        cleaned / "source_selection_reason_counts.csv", index=False)

    print("=" * 70)
    print("SOURCE SELECTION")
    print(f"  cleaning summary : {summary_path}")
    print(f"  sources evaluated: {len(table)}")
    print(f"  selected         : {int(table['selected'].sum())}  ({n_placed} files staged in {selected_dir})")
    for reason, n in counts.items():
        print(f"    rejected, {reason}: {n}")
    print("=" * 70)
    return table
