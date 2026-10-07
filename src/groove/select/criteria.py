"""Apply the source-level usability criteria to the cleaning summary table."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import settings as S


def _num(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def evaluate(summary: pd.DataFrame) -> pd.DataFrame:
    """Return the summary with `selected` (bool) and `selection_reasons` columns."""
    out = summary.copy()
    n_total = _num(out, "n_final_keep")
    n_c = _num(out, "n_c_clean").fillna(0)
    n_o = _num(out, "n_o_clean").fillna(0)
    baseline = _num(out, "baseline_days_clean")
    kept = _num(out, "fraction_kept")
    dm_c = _num(out, "median_dm_c_clean")
    dm_o = _num(out, "median_dm_o_clean")
    status_ok = out.get("status", pd.Series("ok", index=out.index)).astype(str).str.lower().eq("ok")

    reasons = []
    for i in out.index:
        r = []
        if not status_ok[i]:
            r.append("cleaning_failed")
        if not np.isfinite(n_total[i]) or n_total[i] < S.MIN_POINTS:
            r.append(f"fewer_than_{S.MIN_POINTS}_points")
        if max(n_c[i], n_o[i]) < S.MIN_POINTS_PER_BAND:
            r.append(f"no_band_with_{S.MIN_POINTS_PER_BAND}_points")
        if not np.isfinite(baseline[i]) or baseline[i] < S.MIN_BASELINE_DAYS:
            r.append(f"baseline_under_{S.MIN_BASELINE_DAYS:g}_days")
        if np.isfinite(kept[i]) and (1.0 - kept[i]) > S.MAX_REMOVED_FRACTION:
            r.append(f"more_than_{S.MAX_REMOVED_FRACTION:.0%}_removed")
        eligible_dm = [err for n, err in ((n_c[i], dm_c[i]), (n_o[i], dm_o[i])) if n >= S.MIN_POINTS_PER_BAND and np.isfinite(err)]
        best_dm = min(eligible_dm) if eligible_dm else np.nan
        if not np.isfinite(best_dm) or best_dm > S.MAX_MEDIAN_UNCERTAINTY_MAG:
            r.append(f"median_uncertainty_over_{S.MAX_MEDIAN_UNCERTAINTY_MAG:g}_mag")
        reasons.append(";".join(r))
    out["selection_reasons"] = reasons
    out["selected"] = [r == "" for r in reasons]
    return out
