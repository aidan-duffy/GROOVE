from __future__ import annotations
import argparse
import hashlib
import math
import re
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple
import pandas as pd
from . import settings as S
from . import run as _run




def clean_cell(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "<na>"}:
        return ""
    return text


def normalise_integer_id(value: object) -> str:
    text = clean_cell(value)
    if re.fullmatch(r"[+-]?\d+\.0", text):
        return text[:-2]
    return text


def normalise_group_for_match(value: object) -> str:
    """Case-fold a value and ignore spaces, underscores and hyphens."""
    return re.sub(r"[\s_-]+", "", clean_cell(value).casefold())



def resolve_column(
    df: pd.DataFrame,
    explicit: Optional[str],
    kind: str,
    required: bool = False,
) -> Optional[str]:
    columns = list(df.columns)
    lower_map = {str(col).strip().lower(): col for col in columns}

    if explicit:
        if explicit in df.columns:
            return explicit
        match = lower_map.get(explicit.strip().lower())
        if match is not None:
            return str(match)
        raise KeyError(
            f"Requested --{kind.replace('_', '-')}-col '{explicit}' was not found. "
            f"Available columns: {columns}"
        )

    for candidate in S.COLUMN_CANDIDATES[kind]:
        if candidate in df.columns:
            return candidate
        match = lower_map.get(candidate.lower())
        if match is not None:
            return str(match)

    if required:
        raise KeyError(
            f"Could not detect a {kind} column. Supply --{kind.replace('_', '-')}-col. "
            f"Available columns: {columns}"
        )
    return None


def format_optional_number(value: object, digits: int = 8) -> str:
    text = clean_cell(value)
    if not text:
        return ""
    try:
        number = float(text)
    except (TypeError, ValueError):
        return text
    if not math.isfinite(number):
        return ""
    return f"{number:.{digits}g}"


def make_target_key(gaia_id: str, ra: float, dec: float) -> str:
    if gaia_id:
        return f"gaia:{gaia_id}"
    return f"coord:{ra:.7f},{dec:.7f}"


def make_target_id(target_key: str) -> str:
    return "T" + hashlib.sha1(target_key.encode("utf-8")).hexdigest()[:14]


def prepare_targets(
    args: argparse.Namespace,
) -> Tuple[pd.DataFrame, Dict[str, Optional[str]], Dict[str, Any]]:
    input_path = Path(args.input_csv).expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Input CSV not found: {input_path}")

    raw = pd.read_csv(input_path, dtype=str, keep_default_na=False)
    if raw.empty:
        raise ValueError("The input CSV contains no targets.")

    input_rows_total = len(raw)
    columns = {
        "gaia": resolve_column(raw, args.gaia_col, "gaia", required=False),
        "group": resolve_column(raw, S.GROUP_COLUMN or args.group_col, "group", required=False),
        "ra": resolve_column(raw, args.ra_col, "ra", required=True),
        "dec": resolve_column(raw, args.dec_col, "dec", required=True),
        "atlas_id": resolve_column(raw, args.atlas_id_col, "atlas_id", required=False),
        "var_class": resolve_column(raw, args.class_col, "var_class", required=False),
        "period": resolve_column(raw, args.period_col, "period", required=False),
        "angdist": resolve_column(raw, args.angdist_col, "angdist", required=False),
    }

    targets = pd.DataFrame(index=raw.index)
    targets["input_row_number"] = raw.index + 2  # CSV header is line 1.
    targets["gaia_dr3_id"] = (
        raw[columns["gaia"]].map(normalise_integer_id)
        if columns["gaia"]
        else ""
    )
    targets["group"] = (
        raw[columns["group"]].map(clean_cell)
        if columns["group"]
        else "ungrouped"
    )
    targets["group"] = targets["group"].replace("", "ungrouped")
    targets["ra"] = pd.to_numeric(raw[columns["ra"]], errors="coerce")
    targets["dec"] = pd.to_numeric(raw[columns["dec"]], errors="coerce")
    targets["atlas_id"] = (
        raw[columns["atlas_id"]].map(clean_cell)
        if columns["atlas_id"]
        else ""
    )
    targets["variability_class"] = (
        raw[columns["var_class"]].map(clean_cell)
        if columns["var_class"]
        else ""
    )
    targets["catalogue_period_days"] = (
        raw[columns["period"]].map(lambda x: format_optional_number(x, digits=10))
        if columns["period"]
        else ""
    )

    # Apply catalogue filters before coordinate validation so the report can
    # distinguish filtering from invalid-coordinate removal.
    if args.gaia_id:
        if not columns["gaia"]:
            raise KeyError(
                "--gaia-id was supplied, but no Gaia DR3 ID column was detected. "
                "Supply --gaia-col."
            )
        requested_gaia_id = normalise_integer_id(args.gaia_id)
        keep = targets["gaia_dr3_id"] == requested_gaia_id
        targets = targets.loc[keep].copy()
        if targets.empty:
            raise ValueError(
                f"No target matched Gaia DR3 source ID {requested_gaia_id!r}."
            )

    for column, wanted in (S.FILTERS or {}).items():
        if column not in raw.columns:
            raise SystemExit(
                f"filters: column {column!r} is not in the target list. "
                f"Available columns: {', '.join(raw.columns)}"
            )
        wanted_text = normalise_group_for_match(wanted)
        keep = raw[column].map(normalise_group_for_match) == wanted_text
        targets = targets.loc[keep.reindex(targets.index, fill_value=False)].copy()
        if targets.empty:
            available = sorted(set(raw[column].map(clean_cell)))[:20]
            raise SystemExit(f"No targets matched {column}={wanted!r}. Examples: {available}")


    if args.group:
        if not columns["group"]:
            raise SystemExit(
                "group was supplied, but no grouping column was detected. "
                "Set group_column in your config."
            )
        requested_group = normalise_group_for_match(args.group)
        keep = targets["group"].map(normalise_group_for_match) == requested_group
        if not keep.any():
            available = sorted(raw[columns["group"]].map(clean_cell).drop_duplicates())[:20]
            raise SystemExit(
                f"No targets matched group {args.group!r}. Matching ignores case, "
                f"spaces, underscores and hyphens. Examples: {available}"
            )
        targets = targets.loc[keep].copy()

    rows_after_catalogue_filters = len(targets)

    invalid = (
        targets["ra"].isna()
        | targets["dec"].isna()
        | ~targets["ra"].between(0.0, 360.0)
        | ~targets["dec"].between(-90.0, 90.0)
    )
    invalid_coordinate_rows = int(invalid.sum())
    if invalid_coordinate_rows:
        bad_rows = targets.loc[invalid, "input_row_number"].tolist()[:15]
        _run.print_safe(
            f"Skipping {invalid_coordinate_rows} row(s) with missing/invalid coordinates. "
            f"First CSV row numbers: {bad_rows}"
        )
        targets = targets.loc[~invalid].copy()

    if args.match_radius is not None:
        if not columns["angdist"]:
            raise KeyError(
                "--match-radius was supplied, but no angular-separation column was "
                "detected. Supply --angdist-col."
            )
        angdist = pd.to_numeric(raw.loc[targets.index, columns["angdist"]], errors="coerce")
        keep = angdist.notna() & (angdist <= float(args.match_radius))
        _run.print_safe(
            f"Angular-separation cut: kept {int(keep.sum())}/{len(keep)} rows "
            f"within {args.match_radius:g} arcsec."
        )
        targets = targets.loc[keep].copy()

    targets["target_key"] = [
        make_target_key(normalise_integer_id(gaia), float(ra), float(dec))
        for gaia, ra, dec in zip(
            targets["gaia_dr3_id"], targets["ra"], targets["dec"]
        )
    ]
    targets["target_id"] = targets["target_key"].map(make_target_id)

    before_dedup = len(targets)
    targets = targets.sort_values(
        ["target_key", "input_row_number"], kind="stable"
    ).drop_duplicates("target_key", keep="first")
    duplicate_count = before_dedup - len(targets)
    if duplicate_count:
        _run.print_safe(
            f"Removed {duplicate_count} duplicate target row(s) using Gaia DR3 ID, "
            "with coordinates as the fallback key."
        )

    targets = targets.sort_values("target_key", kind="stable").reset_index(drop=True)
    

    if args.start_index:
        targets = targets.iloc[int(args.start_index):].copy()
    if args.limit is not None:
        targets = targets.head(int(args.limit)).copy()

    if targets.empty:
        raise ValueError("No targets remain after filtering and limits.")

    targets = targets.reset_index(drop=True)
    selection = {
        "input_rows_total": input_rows_total,
        "rows_after_catalogue_filters": rows_after_catalogue_filters,
        "invalid_coordinate_rows": invalid_coordinate_rows,
        "duplicate_rows_removed": duplicate_count,
        "final_targets": len(targets),
        "group_count": int(targets["group"].nunique()),
    }
    return targets, columns, selection
