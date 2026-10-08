from __future__ import annotations
import json
import numpy as np
import pandas as pd
from . import settings as S
from . import cuts as _cuts
from . import loading as _loading
from . import plots as _plots
from .. import resume as R




def write_run_summary(summary_df: pd.DataFrame) -> None:
    """Write a concise plain-text summary of the cleaning run."""
    ok = summary_df.loc[summary_df["status"].eq("ok")].copy()
    failed = summary_df.loc[summary_df["status"].eq("failed")].copy()

    for column in ["n_raw", "n_final_keep", "n_removed", "fraction_kept"]:
        if column in ok.columns:
            ok[column] = pd.to_numeric(ok[column], errors="coerce")

    S.PLOT_DIR.mkdir(parents=True, exist_ok=True)
    output = S.PLOT_DIR / "cleaning_run_summary.txt"
    with output.open("w", encoding="utf-8") as handle:
        handle.write("ATLAS CLEANING RUN SUMMARY\n")
        handle.write("=" * 60 + "\n")
        handle.write(f"Input directory:   {S.INPUT_DIR}\n")
        handle.write(f"Cleaned directory: {S.CLEANED_DIR}\n")
        handle.write(f"Plot directory:    {S.PLOT_DIR}\n\n")
        handle.write(f"Input files found: {len(summary_df):,}\n")
        handle.write(f"Files cleaned:     {len(ok):,}\n")
        handle.write(f"Files failed:      {len(failed):,}\n")

        if len(ok):
            raw_total = int(ok["n_raw"].sum())
            kept_total = int(ok["n_final_keep"].sum())
            removed_total = int(ok["n_removed"].sum())
            total_removed_fraction = (
                removed_total / raw_total if raw_total else np.nan
            )
            median_removed_fraction = float((1.0 - ok["fraction_kept"]).median())

            handle.write(f"Total raw points:  {raw_total:,}\n")
            handle.write(f"Total kept points: {kept_total:,}\n")
            handle.write(f"Points removed:    {removed_total:,}\n")
            handle.write(
                f"Overall fraction removed: {total_removed_fraction:.5f}\n"
            )
            handle.write(
                f"Median per-star fraction removed: "
                f"{median_removed_fraction:.5f}\n"
            )

        if len(failed):
            handle.write("\nFAILED FILES\n")
            handle.write("-" * 60 + "\n")
            for _, row in failed.iterrows():
                handle.write(f"{row.get('file', '')}: {row.get('error', '')}\n")


# ============================================================================
# MAIN BATCH
# ============================================================================


def main() -> None:
    S.CLEANED_DIR.mkdir(parents=True, exist_ok=True)
    S.PLOT_DIR.mkdir(parents=True, exist_ok=True)

    files = sorted(S.INPUT_DIR.glob(S.FILE_GLOB))
    files = [
        path
        for path in files
        if not path.name.endswith("_cleaned.csv")
        and path.name not in {
            "cleaning_summary.csv",
            "cleaning_reason_counts.csv",
        }
    ]
    if not files:
        raise FileNotFoundError(
            f"No input files found in {S.INPUT_DIR} matching {S.FILE_GLOB}"
        )

    print("=" * 90)
    print("ATLAS FORCED-PHOTOMETRY BATCH CLEAN")
    print("=" * 90)
    print(f"Input folder:   {S.INPUT_DIR}")
    print(f"Cleaned folder: {S.CLEANED_DIR}")
    print(f"Plot folder:    {S.PLOT_DIR}")
    print(f"Files found:    {len(files):,}")
    print(f"Dip rescue:     {S.RESCUE_ENABLE}")
    print("=" * 90)

    scientific = {k: v for k, v in R.settings_dict(S).items()
                  if not any(token in k for token in ('PLOT', 'SAVE_', 'EXAMPLE', 'PROGRESS', 'FORCE', 'OVERWRITE'))}
    clean_signature = R.hash_value({'code': R.code_hash('clean'), 'settings': scientific})
    checkpoint_dir = S.CLEANED_DIR / '.checkpoints'
    rows: list[dict] = []
    all_reason_counts: dict[str, int] = {}

    for file_number, input_file in enumerate(files, start=1):
        stem = input_file.stem
        cleaned_file = S.CLEANED_DIR / f"{stem}_cleaned.csv"

        checkpoint = checkpoint_dir / (R.hash_value(input_file.name) + '.json')
        signature = R.hash_value([clean_signature, R.digest(input_file)])
        saved = R.read_json(checkpoint)
        if (not getattr(S, 'FORCE_RERUN', False) and saved.get('signature') == signature
                and saved.get('row', {}).get('status') == 'ok'
                and saved.get('output_hash') == R.digest(cleaned_file)):
            row = saved['row']
            rows.append(row)
            for token, count in json.loads(row['reason_token_counts_json']).items():
                all_reason_counts[token] = all_reason_counts.get(token, 0) + int(count)
            if file_number % max(1, S.PROGRESS_EVERY) == 0 or file_number == len(files):
                print(f'[{file_number:,}/{len(files):,}] reused cleaned source')
            continue

        try:
            raw = pd.read_csv(input_file, dtype=str)
            all_rows, summary = _cuts.clean_atlas_df(raw)
            (
                object_name,
                gaia_dr3,
                atoid,
                cluster_name,
                atlas_class,
                catalogue_period,
                ra,
                dec,
            ) = _loading.get_metadata_from_df(all_rows, stem)

            clean = all_rows.loc[all_rows["final_keep"]].copy()
            temporary = cleaned_file.with_suffix('.csv.tmp')
            clean.to_csv(temporary, index=False)
            temporary.replace(cleaned_file)
            file_action = 'written'

            rejected_reasons = all_rows.loc[
                ~all_rows["final_keep"],
                "reject_reason",
            ].astype(str)
            tokens = rejected_reasons.str.split(";").explode()
            tokens = tokens[tokens.str.len() > 0]
            token_counts = tokens.value_counts().to_dict()

            for token, count in token_counts.items():
                all_reason_counts[token] = (
                    all_reason_counts.get(token, 0) + int(count)
                )

            top_reasons = sorted(
                token_counts.items(),
                key=lambda item: -item[1],
            )[:5]

            row = {
                "file": input_file.name,
                "cleaned_file": cleaned_file.name,
                "file_action": file_action,
                "object_name": object_name,
                "gaia_dr3": gaia_dr3,
                "atoid": atoid,
                "cluster_name": cluster_name,
                "atlas_class": atlas_class,
                "catalogue_period_days": catalogue_period,
                "ra_deg": ra,
                "dec_deg": dec,
                "n_raw": summary["raw_rows"],
                "n_hard_reject": summary["hard_reject"],
                "n_standard_keep": summary["standard_keep"],
                "n_rescued": summary["rescued"],
                "n_final_keep": summary["final_keep"],
                "n_removed": summary["removed"],
                "fraction_kept": summary["fraction_kept"],
                "mjd_min_raw": summary["mjd_min_raw"],
                "mjd_max_raw": summary["mjd_max_raw"],
                "baseline_days_raw": summary["baseline_days_raw"],
                "mjd_min_clean": summary["mjd_min_clean"],
                "mjd_max_clean": summary["mjd_max_clean"],
                "baseline_days_clean": summary["baseline_days_clean"],
                "n_c_raw": summary["n_c_raw"],
                "n_o_raw": summary["n_o_raw"],
                "n_c_clean": summary["n_c_clean"],
                "n_o_clean": summary["n_o_clean"],
                "median_dm_c_clean": summary["median_dm_c_clean"],
                "median_dm_o_clean": summary["median_dm_o_clean"],
                "median_duJy_c_clean": summary["median_duJy_c_clean"],
                "median_duJy_o_clean": summary["median_duJy_o_clean"],
                "filters_present_raw": ",".join(
                    summary["filters_present_raw"]
                ),
                "filters_present_clean": ",".join(
                    summary["filters_present_clean"]
                ),
                "cuts_applied": ",".join(summary["cuts_applied"]),
                "top_reason_1": top_reasons[0][0] if len(top_reasons) > 0 else "",
                "top_reason_1_count": int(top_reasons[0][1]) if len(top_reasons) > 0 else 0,
                "top_reason_2": top_reasons[1][0] if len(top_reasons) > 1 else "",
                "top_reason_2_count": int(top_reasons[1][1]) if len(top_reasons) > 1 else 0,
                "top_reason_3": top_reasons[2][0] if len(top_reasons) > 2 else "",
                "top_reason_3_count": int(top_reasons[2][1]) if len(top_reasons) > 2 else 0,
                "reason_token_counts_json": json.dumps(
                    token_counts,
                    ensure_ascii=False,
                ),
                "status": "ok",
                "error": "",
                "cleaned_path": str(cleaned_file),
            }
            rows.append(row)
            R.atomic_json(checkpoint, {'signature': signature, 'row': row,
                                      'output_hash': R.digest(cleaned_file)})

        except Exception as error:
            object_name, ra, dec = _loading.parse_name_ra_dec_from_filename(stem)
            rows.append(
                {
                    "file": input_file.name,
                    "cleaned_file": "",
                    "file_action": "failed",
                    "object_name": object_name,
                    "gaia_dr3": "",
                    "atoid": "",
                    "cluster_name": "",
                    "atlas_class": "",
                    "catalogue_period_days": np.nan,
                    "ra_deg": ra,
                    "dec_deg": dec,
                    "n_raw": np.nan,
                    "n_hard_reject": np.nan,
                    "n_standard_keep": np.nan,
                    "n_rescued": np.nan,
                    "n_final_keep": np.nan,
                    "n_removed": np.nan,
                    "fraction_kept": np.nan,
                    "mjd_min_raw": np.nan,
                    "mjd_max_raw": np.nan,
                    "baseline_days_raw": np.nan,
                    "mjd_min_clean": np.nan,
                    "mjd_max_clean": np.nan,
                    "baseline_days_clean": np.nan,
                    "n_c_raw": np.nan,
                    "n_o_raw": np.nan,
                    "n_c_clean": np.nan,
                    "n_o_clean": np.nan,
                    "median_dm_c_clean": np.nan,
                    "median_dm_o_clean": np.nan,
                    "median_duJy_c_clean": np.nan,
                    "median_duJy_o_clean": np.nan,
                    "filters_present_raw": "",
                    "filters_present_clean": "",
                    "cuts_applied": "",
                    "top_reason_1": "",
                    "top_reason_1_count": 0,
                    "top_reason_2": "",
                    "top_reason_2_count": 0,
                    "top_reason_3": "",
                    "top_reason_3_count": 0,
                    "reason_token_counts_json": "{}",
                    "status": "failed",
                    "error": str(error),
                    "cleaned_path": "",
                }
            )

        if (
            file_number % max(1, S.PROGRESS_EVERY) == 0
            or file_number == len(files)
        ):
            print(f"[{file_number:,}/{len(files):,}] processed")

    summary_df = pd.DataFrame(rows)
    summary_path = S.CLEANED_DIR / "cleaning_summary.csv"
    temporary = summary_path.with_suffix('.csv.tmp')
    summary_df.to_csv(temporary, index=False)
    temporary.replace(summary_path)

    reason_df = pd.DataFrame(
        [
            {"reject_reason": reason, "n_points": count}
            for reason, count in sorted(
                all_reason_counts.items(),
                key=lambda item: -item[1],
            )
        ]
    )
    reason_path = S.CLEANED_DIR / "cleaning_reason_counts.csv"
    reason_df.to_csv(reason_path, index=False)

    if S.MAKE_SUMMARY_PLOTS:
        _plots.make_summary_figure(summary_df)
    if S.MAKE_REASON_PLOT:
        _plots.make_reason_figure(reason_df)
    if S.MAKE_EXAMPLE_PLOTS:
        _plots.make_example_plots(summary_df)
    write_run_summary(summary_df)

    ok = summary_df.loc[summary_df["status"].eq("ok")].copy()
    failed = summary_df.loc[summary_df["status"].eq("failed")].copy()

    print("=" * 90)
    print("DONE")
    print(f"Cleaned files:      {S.CLEANED_DIR}")
    print(f"Cleaning plots:     {S.PLOT_DIR}")
    print(f"Summary CSV:        {summary_path}")
    print(f"Reason counts CSV:  {reason_path}")
    print(f"Files successful:   {len(ok):,}")
    print(f"Files failed:       {len(failed):,}")

    if len(ok):
        raw_total = int(pd.to_numeric(ok["n_raw"], errors="coerce").sum())
        kept_total = int(
            pd.to_numeric(ok["n_final_keep"], errors="coerce").sum()
        )
        fraction_removed = (
            (raw_total - kept_total) / raw_total if raw_total else np.nan
        )
        print(f"Total raw points:   {raw_total:,}")
        print(f"Total kept points:  {kept_total:,}")
        print(f"Fraction removed:   {fraction_removed:.5f}")

    if len(failed):
        print("Check the 'error' column in the summary CSV for failed files.")
    print("=" * 90)

    if len(failed):
        raise RuntimeError(f'{len(failed)} cleaning source(s) failed; fix inputs and resume to retry.')
