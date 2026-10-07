from __future__ import annotations
import re
import numpy as np
import pandas as pd




# ============================================================================
# HELPERS: INPUT NORMALISATION
# ============================================================================


def _rename_first_available(
    df: pd.DataFrame,
    candidates: list[str],
    canonical: str,
) -> pd.DataFrame:
    """Rename the first available candidate to a canonical column name."""
    if canonical in df.columns:
        return df
    for name in candidates:
        if name in df.columns:
            return df.rename(columns={name: canonical})
    return df


def normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise common ATLAS-VAR and forced-photometry column names."""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    df = _rename_first_available(df, ["###MJD", "mjd", "Mjd"], "MJD")
    df = _rename_first_available(df, ["filter", "Filter", "filt"], "F")
    df = _rename_first_available(df, ["mag", "m_mag"], "m")
    df = _rename_first_available(df, ["mag_err", "m_err", "emag"], "dm")
    df = _rename_first_available(df, ["flux", "Flux", "ujy"], "uJy")
    df = _rename_first_available(df, ["flux_err", "Flux_err", "dujy"], "duJy")

    if "MJD" not in df.columns:
        raise ValueError(f"No MJD/mjd column found. Columns={list(df.columns)}")
    if "F" not in df.columns:
        raise ValueError(f"No filter/F column found. Columns={list(df.columns)}")

    return df


def safe_numeric(df: pd.DataFrame, col: str) -> None:
    """Convert a column to numeric values where it exists."""
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")


def abmag_to_uJy(m: np.ndarray) -> np.ndarray:
    """Convert AB magnitude to microJy."""
    with np.errstate(over="ignore", invalid="ignore"):
        return 10.0 ** ((23.9 - m) / 2.5)


def dm_to_duJy(uJy: np.ndarray, dm: np.ndarray) -> np.ndarray:
    """Propagate magnitude uncertainty to microJy uncertainty."""
    return uJy * (np.log(10.0) / 2.5) * dm


def parse_name_ra_dec_from_filename(stem: str):
    """Best-effort extraction of object name and coordinates from a filename."""
    forced_match = re.search(
        r"^\d+_(?P<name>.+?)_ra(?P<ra>-?\d+(\.\d+)?)_dec"
        r"(?P<dec>-?\d+(\.\d+)?)(?:_|$)",
        stem,
    )
    if forced_match:
        return (
            forced_match.group("name"),
            float(forced_match.group("ra")),
            float(forced_match.group("dec")),
        )

    dr1_match = re.search(r"GaiaDR3[_-](?P<gaia>\d+)", stem, flags=re.IGNORECASE)
    if dr1_match:
        return f"GaiaDR3_{dr1_match.group('gaia')}", np.nan, np.nan

    return stem, np.nan, np.nan


# ============================================================================
# METADATA EXTRACTION
# ============================================================================


def get_metadata_from_df(df_all: pd.DataFrame, stem: str):
    """Extract common source metadata from the light curve or filename."""
    object_name, ra_from_name, dec_from_name = parse_name_ra_dec_from_filename(
        stem
    )

    def first_nonnull(columns: list[str]):
        for column in columns:
            if column in df_all.columns:
                values = df_all[column].dropna()
                if len(values):
                    return values.iloc[0]
        return ""

    gaia_dr3 = first_nonnull(["target_GaiaDR3", "gaia_dr3", "GaiaDR3", "source_id"])
    atoid = first_nonnull(["target_ATLAS_ID", "atoid", "ATOID", "ATO_ID"])
    cluster_name = first_nonnull(["target_group", "target_cluster", "cluster_name", "Name", "cluster"])
    atlas_class = first_nonnull(
        ["target_variability_class", "xmatch_class", "atlas_class", "atlas_object_class", "Class", "class"]
    )

    catalogue_period = np.nan
    for column in [
        "target_catalogue_period_days",
        "xmatch_fp_period",
        "atlas_object_period",
        "fp_period",
        "period",
        "xmatch_ls_pday",
        "ls_pday",
    ]:
        if column in df_all.columns:
            values = pd.to_numeric(df_all[column], errors="coerce")
            values = values[np.isfinite(values)]
            if len(values):
                catalogue_period = float(values.iloc[0])
                break

    ra = ra_from_name
    dec = dec_from_name
    for ra_column, dec_column in [
        ("target_ra_used", "target_dec_used"),
        ("ra", "dec"),
        ("RA", "Dec"),
        ("atlas_ra", "atlas_dec"),
    ]:
        if (
            (not np.isfinite(ra) or not np.isfinite(dec))
            and ra_column in df_all.columns
            and dec_column in df_all.columns
        ):
            ra_value = pd.to_numeric(df_all[ra_column], errors="coerce").median()
            dec_value = pd.to_numeric(df_all[dec_column], errors="coerce").median()
            if np.isfinite(ra_value):
                ra = float(ra_value)
            if np.isfinite(dec_value):
                dec = float(dec_value)

    return (
        object_name,
        gaia_dr3,
        atoid,
        cluster_name,
        atlas_class,
        catalogue_period,
        ra,
        dec,
    )
