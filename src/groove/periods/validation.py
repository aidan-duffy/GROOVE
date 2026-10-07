from __future__ import annotations
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd
from . import settings as S
from . import aliases as _aliases
from . import loading as _loading




def load_external_catalogue() -> dict[str, float]:
    if S.CATALOG_CSV is None:
        return {}
    path = Path(S.CATALOG_CSV)
    if not path.exists():
        raise FileNotFoundError(f"CATALOG_CSV does not exist: {path}")
    cat = pd.read_csv(path, dtype={S.CATALOG_ID_COLUMN: str})
    missing = {S.CATALOG_ID_COLUMN, S.CATALOG_PERIOD_COLUMN} - set(cat.columns)
    if missing:
        raise ValueError(f"Catalogue is missing required columns: {sorted(missing)}")
    ids = cat[S.CATALOG_ID_COLUMN].astype(str).str.strip()
    periods = pd.to_numeric(cat[S.CATALOG_PERIOD_COLUMN], errors="coerce")
    good = ids.ne("") & np.isfinite(periods) & (periods > 0)
    return dict(zip(ids[good], periods[good].astype(float)))


def catalogue_match(period: float, catalogue_period: float) -> str:
    if not np.isfinite(catalogue_period) or catalogue_period <= 0:
        return "no_catalogue_period"
    if not np.isfinite(period) or period <= 0:
        return "no_recovered_period"
    rel = _aliases.harmonic_relation(period, catalogue_period, tolerance=S.CATALOG_MATCH_TOLERANCE_FRACTION)
    return rel if rel else "mismatch"


def catalogue_match_is_success(match: str) -> bool:
    return match == "direct" or match.startswith("P/") or match.endswith("P")


# =============================================================================
# VALIDATION SUMMARY
# =============================================================================
def validation_summary_table(summary_rows: list[dict[str, Any]], recommendations: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    summary = pd.DataFrame(summary_rows)
    if not summary.empty and {"status", "series", "catalogue_searchable"}.issubset(summary.columns):
        ok = summary.loc[summary["status"].astype(str).eq("ok")].copy()
        for series_name, group in ok.groupby("series"):
            searchable = group.loc[group["catalogue_searchable"].fillna(False).astype(bool)]
            if len(searchable) == 0:
                continue
            raw_match = searchable["raw_catalogue_match"].astype(str)
            top_match = searchable["catalogue_recovered_top_n"].fillna(False).astype(bool)
            series_match = searchable.apply(lambda r: catalogue_match(_loading.safe_float(r.get("recommended_series_period_days"), np.nan), _loading.safe_float(r.get("catalogue_period_days"), np.nan)), axis=1).astype(str)
            rows.append(
                {
                    "level": "series",
                    "series": series_name,
                    "n_catalogue_searchable": int(len(searchable)),
                    "raw_direct_rate": float(raw_match.eq("direct").mean()),
                    "raw_direct_or_harmonic_rate": float(raw_match.map(catalogue_match_is_success).mean()),
                    "top_n_direct_or_harmonic_rate": float(top_match.mean()),
                    "recommended_series_direct_rate": float(series_match.eq("direct").mean()),
                    "recommended_series_direct_or_harmonic_rate": float(series_match.map(catalogue_match_is_success).mean()),
                }
            )
    if recommendations is not None and not recommendations.empty and "catalogue_period_days" in recommendations.columns:
        searchable = recommendations.loc[np.isfinite(pd.to_numeric(recommendations["catalogue_period_days"], errors="coerce"))].copy()
        if len(searchable):
            rec_match = searchable["recommended_catalogue_match"].astype(str)
            phot_match = searchable["photometric_catalogue_match"].astype(str)
            rows.append(
                {
                    "level": "source_recommendation",
                    "series": "source",
                    "n_catalogue_searchable": int(len(searchable)),
                    "photometric_direct_rate": float(phot_match.eq("direct").mean()),
                    "photometric_direct_or_harmonic_rate": float(phot_match.map(catalogue_match_is_success).mean()),
                    "recommended_direct_rate": float(rec_match.eq("direct").mean()),
                    "recommended_direct_or_harmonic_rate": float(rec_match.map(catalogue_match_is_success).mean()),
                }
            )
    return pd.DataFrame(rows)
