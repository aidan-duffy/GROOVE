"""Load and validate the single YAML config that drives every stage."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

VALID_YEARS = {"2", "4", "10", "full"}


@dataclass
class Config:
    name: str
    output_folder: Path
    targets: Path | None = None
    group: str = ""
    group_column: str = ""
    filters: dict[str, Any] = field(default_factory=dict)
    gaia_id: str = ""
    years: str = "full"
    photometry: str = "reduced"
    input_folder: Path | None = None
    download: dict[str, Any] = field(default_factory=dict)
    clean: dict[str, Any] = field(default_factory=dict)
    select: dict[str, Any] = field(default_factory=dict)
    periods: dict[str, Any] = field(default_factory=dict)
    morphology: dict[str, Any] = field(default_factory=dict)
    source_path: Path | None = None

    # ---- derived folders: the contract between stages -------------------
    @property
    def raw_root(self) -> Path:
        return self.output_folder / "1_raw"

    @property
    def download_run_name(self) -> str:
        return f"atlas_{self.years}yr_{self.photometry}" if self.years != "full" else f"atlas_full_{self.photometry}"

    @property
    def raw_lightcurves(self) -> Path:
        return self.input_folder or self.raw_root / self.download_run_name / "all_lightcurves"

    @property
    def clean_dir(self) -> Path:
        return self.output_folder / "2_clean" / "lightcurves"

    # ---- all figures from every stage live under one folder ---------------
    @property
    def plots_root(self) -> Path:
        return self.output_folder / "plots"

    @property
    def clean_plots(self) -> Path:
        return self.plots_root / "clean"

    @property
    def period_plots(self) -> Path:
        return self.plots_root / "periods"



    @property
    def selected_dir(self) -> Path:
        return self.output_folder / "2_clean" / "selected"

    @property
    def periods_dir(self) -> Path:
        return self.output_folder / "3_periods"

    @property
    def morphology_dir(self) -> Path:
        return self.output_folder / "4_morphology"


def load(path: str | Path) -> Config:
    path = Path(path).expanduser().resolve()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: config must be a YAML mapping")
    allowed = set(Config.__dataclass_fields__) - {"source_path"}
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError(f"{path}: unknown config keys: {sorted(unknown)}")
    for stage in ("filters", "download", "clean", "select", "periods", "morphology"):
        if raw.get(stage) is not None and not isinstance(raw[stage], dict):
            raise ValueError(f"{stage} must be a mapping")
    if not raw.get("output_folder"):
        raise ValueError(f"{path}: 'output_folder' is required")
    base = path.parent

    def resolve(value):
        if value in (None, ""):
            return None
        p = Path(str(value)).expanduser()
        return p if p.is_absolute() else (base / p).resolve()

    years = str(raw.get("years", "full")).lower()
    if years not in VALID_YEARS:
        raise ValueError(f"years must be one of {sorted(VALID_YEARS)}, got {years!r}")
    cfg = Config(
        name=str(raw.get("name") or path.stem),
        output_folder=resolve(raw["output_folder"]),
        targets=resolve(raw.get("targets")),
        group=str(raw.get("group") or ""),
        group_column=str(raw.get("group_column") or ""),
        filters=dict(raw.get("filters") or {}),
        gaia_id=str(raw.get("gaia_id") or ""),
        years=years,
        photometry=str(raw.get("photometry", "reduced")),
        input_folder=resolve(raw.get("input_folder")),
        download=dict(raw.get("download") or {}),
        clean=dict(raw.get("clean") or {}),
        select=dict(raw.get("select") or {}),
        periods=dict(raw.get("periods") or {}),
        morphology=dict(raw.get("morphology") or {}),
        source_path=path,
    )
    if cfg.photometry not in {"reduced", "difference"}:
        raise ValueError("photometry must be reduced or difference")
    if not cfg.name or any(c in cfg.name for c in "/\\") or cfg.name in {".", ".."}:
        raise ValueError("name must be a non-empty name without path separators")
    # Settings paths share the YAML file's base, including nullable paths/lists.
    paths = {"input_dir", "cleaned_dir", "plot_dir", "output_dir", "selected_dir",
             "catalog_csv", "alias_memory_csv", "manual_labels_file", "output_root"}
    lists = {"reference_summary_csvs", "alias_selected_files", "harmonic_selected_files"}
    for stage in (cfg.download, cfg.clean, cfg.select, cfg.periods, cfg.morphology):
        for key, value in list(stage.items()):
            if key.lower() in paths and value:
                stage[key] = str(resolve(value))
            elif key.lower() in lists and value:
                stage[key] = [str(resolve(v)) for v in value]
    return cfg


def apply_overrides(settings_module, overrides: dict[str, Any], stage: str) -> None:
    """Validate settings types and preserve the module's path/container types."""
    from typing import get_type_hints
    hints = get_type_hints(settings_module)
    for key, value in overrides.items():
        name = key.upper()
        if not name.isupper() or not hasattr(settings_module, name):
            raise KeyError(f"{stage}: unknown setting {key!r} (see groove/{stage}/settings.py)")
        current = getattr(settings_module, name)
        if value is not None and (isinstance(current, Path) or "Path" in str(hints.get(name, ""))):
            value = Path(value) if not isinstance(value, list) else [Path(v) for v in value]
        elif isinstance(current, bool) and not isinstance(value, bool):
            raise ValueError(f"{stage}.{key} must be true or false, without quotes")
        elif isinstance(current, (int, float)) and not isinstance(current, bool):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{stage}.{key} must be numeric")
            if isinstance(current, int) and not isinstance(value, int):
                raise ValueError(f"{stage}.{key} must be an integer")
        elif isinstance(current, (set, tuple, list)):
            if not isinstance(value, (list, tuple, set)):
                raise ValueError(f"{stage}.{key} must be a list")
            value = type(current)(value)
        setattr(settings_module, name, value)


EXAMPLE = """# groove pipeline config - copy this file and edit it for your run.
# Paths are relative to this file unless absolute.

name: my_run                        # dataset name
output_folder: results/my_run

# ---- which targets (download stage) -----------------------------------------
targets: my_targets.csv   # CSV with an ID column plus RA and Dec (degrees)
group: ""                           # one value of the grouping column, e.g. a field or cluster name
group_column: ""                    # name of that column; "" = auto-detect (Name/field/group/cluster...)
filters: {}                         # any other cuts, e.g. {Tier: 3, Quality: good}
gaia_id: ""                         # a single Gaia DR3 ID, e.g. "1234567890123456789"
years: full                         # 2, 4, 10 or full (full ATLAS history)
photometry: reduced                 # reduced (recommended) or difference

# input_folder: my_existing_lightcurves  # optional raw CSV folder; use --skip-download

# ---- advanced: override any setting of a stage ------------------------------
# Keys are the UPPER_CASE names in src/groove/<stage>/settings.py
download:
  dry_run: false                    # true = list targets and time estimate, submit nothing
  limit_targets: null               # e.g. 5 for a test run
clean:
  rescue_enable: false              # restore dip points that only failed the soft cuts
select:                             # source-level usability cuts
  min_points: 100
  min_points_per_band: 30
  min_baseline_days: 365
  max_removed_fraction: 0.5
  max_median_uncertainty_mag: 0.2
periods:
  series_to_run: [o, c]             # add combined to compute combined photometry
  plot_series: [o, c]               # add combined to also save its plots
  min_period_days: 0.5
  max_period_days: 200.0
morphology:                         # keys from src/groove/morphology/defaults.yaml
  maps_to_plot: [classification_evidence, combined, periodic]
  mode: fit                         # fit for the first run, transform to add targets to an existing map
  model_version: null               # e.g. reference_v1
"""
