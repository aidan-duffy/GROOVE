"""Download one target at a time, checkpointing every remote job before polling."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Optional, Sequence
import pandas as pd
from . import settings as S, client as api, storage, targets as target_io


def print_safe(*parts):
    print(*parts, flush=True)


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def token_lock(token):
    """An OS lock prevents two GROOVE processes from using this token together."""
    digest = hashlib.sha256(token.encode()).hexdigest()[:24]
    directory = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".cache"))) / "groove"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / f"atlas_{digest}.lock").open("a+b") as handle:
        handle.seek(0)
        if handle.read(1) == b"":
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("Another GROOVE download is already using this token. Let it finish or stop it first.") from exc
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def parse_args(argv: Optional[Sequence[str]] = None):
    p = argparse.ArgumentParser(description="Serial ATLAS downloads using ATLAS_TOKEN.")
    for flag, default in (("input-csv", S.INPUT_CSV), ("outroot", S.OUTPUT_ROOT),
                          ("run-name", S.RUN_NAME), ("gaia-id", S.GAIA_ID_FILTER),
                          ("group", S.GROUP_FILTER), ("end-date", S.END_DATE_UTC)):
        p.add_argument("--" + flag, default=default)
    p.add_argument("--years", choices=["2", "4", "10", "full"], default=str(S.YEARS_TO_DOWNLOAD))
    p.add_argument("--mode", choices=["reduced", "difference"], default=S.ATLAS_MODE)
    p.add_argument("--dry-run", action="store_true", default=S.DRY_RUN)
    p.add_argument("--limit", type=int, default=S.LIMIT_TARGETS)
    p.add_argument("--start-index", type=int, default=S.START_INDEX)
    p.add_argument("--force-redownload", action="store_true", default=S.FORCE_REDOWNLOAD)
    p.add_argument("--retry-failed", action=argparse.BooleanOptionalAction, default=S.RETRY_FAILED_TARGETS)
    for flag, default, type_ in (("poll-seconds", S.POLL_SECONDS, float),
                                ("max-retries", S.MAX_RETRIES, int),
                                ("retry-delay", S.RETRY_DELAY_SECONDS, float),
                                ("max-poll-hours", S.MAX_POLL_HOURS, float),
                                ("minutes-per-target", S.MINUTES_PER_TARGET_ESTIMATE, float),
                                ("match-radius", S.MATCH_RADIUS_ARCSEC, float)):
        p.add_argument("--" + flag, type=type_, default=default)
    for column in ("gaia", "group", "ra", "dec", "atlas-id", "class", "period", "angdist"):
        p.add_argument(f"--{column}-col")
    args = p.parse_args(argv)
    if not args.input_csv or not args.outroot:
        p.error("input-csv and outroot must be provided by the pipeline config")
    if args.years == "full" and args.end_date:
        p.error("end_date cannot be used with years: full")
    if args.limit is not None and args.limit < 1:
        p.error("limit must be positive")
    if args.poll_seconds <= 0 or args.minutes_per_target <= 0:
        p.error("poll_seconds and minutes_per_target must be positive")
    if min(args.start_index, args.max_retries, args.retry_delay, args.max_poll_hours) < 0:
        p.error("start_index, max_retries, retry_delay and max_poll_hours cannot be negative")
    return args


def run_config(args, directory):
    path = directory / "run_config.json"
    expected = {"years": str(args.years), "mode": args.mode, "end_date": args.end_date}
    if path.exists():
        cfg = json.loads(path.read_text())
        if any(cfg.get(key) != value for key, value in expected.items()):
            raise ValueError("Download time range or photometry mode changed. Use a new output folder.")
        return cfg
    end = datetime.now(timezone.utc)
    if args.end_date:
        text = str(args.end_date)
        end = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            end = end.replace(hour=23, minute=59, second=59)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
    mjd_max = None if args.years == "full" else end.timestamp() / 86400 + 40587
    cfg = dict(expected, created=utc_now_iso(), mjd_max=mjd_max,
               mjd_min=None if mjd_max is None else mjd_max - float(args.years) * 365.25)
    storage.atomic_write_json(cfg, path)
    return cfg


def output_path(directory, row, args):
    label = "GaiaDR3_" + row["gaia_dr3_id"] if row["gaia_dr3_id"] else row["target_id"]
    group = storage.safe_component(row["group"], 32)
    return directory / "all_lightcurves" / f"{group}__{label}__{args.mode}_{args.years}.csv"


def download(args, frame, directory, token):
    """Resume stored task/result URLs and stop on an unresolved active request."""
    cfg = run_config(args, directory)
    progress_path = directory / "download_progress.csv"
    previous = pd.read_csv(progress_path, dtype=str, keep_default_na=False).to_dict("records") if progress_path.exists() else []
    rows = {r["target_key"]: r for r in previous}
    # Resume active work first, including a target excluded by a new filter/limit.
    keys = [k for k, r in rows.items() if r.get("status") not in ("completed", "no_data") and (r.get("task_url") or r.get("result_url") or r.get("status") == "submission_unknown")]
    for row in frame.to_dict("records"):
        key = row["target_key"]
        if key in rows:
            old = rows[key]
            if (float(old["ra"]), float(old["dec"])) != (float(row["ra"]), float(row["dec"])):
                raise ValueError("Coordinates changed for an existing target. Use a new output folder.")
            # Keep the frozen metadata and URLs for an unfinished job.
        else:
            rows[key] = dict(row, status="pending", task_url="", result_url="", attempt_count=0,
                             error_message="", all_lightcurves_path=str(output_path(directory, row, args)))
        if key not in keys:
            keys.append(key)
    def save(row, **changes):
        row.update(changes, last_update_utc=utc_now_iso())
        storage.atomic_write_dataframe(pd.DataFrame(rows.values()), progress_path)
    storage.atomic_write_dataframe(frame, directory / "selected_targets.csv")
    storage.atomic_write_dataframe(pd.DataFrame(rows.values()), progress_path)
    client = api.AtlasClient(token, args)
    try:
        client.validate_authentication()
        for index, key in enumerate(keys, 1):
            row = rows[key]
            path = Path(row["all_lightcurves_path"])
            status = row["status"]
            label = row.get("gaia_dr3_id") or row["target_id"]
            if status == "submission_unknown":
                raise RuntimeError("A previous submission has an unknown outcome. Check your ATLAS queue; set its task_url in download_progress.csv to resume, or status=pending after confirming no job exists.")
            active = bool(row.get("task_url") or row.get("result_url")) and status not in ("completed", "no_data")
            if not active and not args.force_redownload:
                if path.is_file() and path.stat().st_size > 0:
                    save(row, status="completed", error_message="")
                    print_safe(f"[{index}/{len(keys)}] {label}: existing file kept")
                    continue
                if status == "no_data":
                    continue
                if status == "failed" and not args.retry_failed:
                    continue
            try:
                result_url = row.get("result_url", "") if active else ""
                task_url = row.get("task_url", "") if active else ""
                if not result_url:
                    if not task_url:
                        # Persist before POST, so a crash never silently repeats an ambiguous submission.
                        save(row, status="submission_unknown", task_url="", result_url="", error_message="", attempt_count=int(row.get("attempt_count") or 0) + 1)
                        task_url, job_id = client.submit_job(float(row["ra"]), float(row["dec"]), cfg["mjd_min"], cfg["mjd_max"], args.mode)
                        save(row, status="submitted", task_url=task_url, active_job_id=job_id)
                    print_safe(f"[{index}/{len(keys)}] {label}: polling saved task")
                    def callback(state, task):
                        save(row, status="running" if state == "completed" else state,
                             result_url=api.extract_result_url(task) or row.get("result_url", ""))
                    task = client.poll_job(task_url, callback)
                    result_url = api.extract_result_url(task)
                    if not result_url:
                        if re.search(r"\bno\s+data\b", str(task), re.I):
                            save(row, status="no_data", number_of_points=0, error_message="")
                            continue
                        raise api.PermanentJobError("ATLAS finished without a result URL")
                    save(row, status="running", result_url=result_url)
                curve = client.download_result(result_url)
                if curve.empty:
                    save(row, status="no_data", number_of_points=0, error_message="")
                else:
                    storage.atomic_write_dataframe(storage.add_target_metadata(curve, row), path)
                    save(row, status="completed", number_of_points=len(curve), error_message="", completion_time_utc=utc_now_iso())
                print_safe(f"[{index}/{len(keys)}] {label}: {row['status']}")
            except (api.AuthenticationError, api.RetryableError, OSError) as exc:
                save(row, status="submission_unknown" if row["status"] == "submission_unknown" else "retry_required", error_message=str(exc))
                print_safe(f"Download paused: {exc}. Rerun to resume saved work.")
                return 1
            except api.PermanentJobError as exc:
                save(row, status="failed", task_url="", result_url="", error_message=str(exc))
                print_safe(f"{label}: {exc}")
    finally:
        client.close()
    counts = pd.Series([rows[k]["status"] for k in keys]).value_counts().to_dict()
    print_safe("Download summary:", counts)
    return 0 if all(rows[k]["status"] in ("completed", "no_data") for k in keys) else 1


def main(argv: Optional[Sequence[str]] = None):
    args = parse_args(argv)
    frame, columns, selection = target_io.prepare_targets(args)
    directory = Path(args.outroot).expanduser().resolve() / storage.safe_component(args.run_name, 80)
    print_safe(f"Selected {len(frame)} targets; time range: {args.years}; photometry: {args.mode}")
    print_safe("Targets per group:", frame["group"].value_counts().to_dict())
    print_safe(f"Estimated service time: {len(frame) * args.minutes_per_target / 60:.1f} hours (queue dependent)")
    if args.dry_run:
        print_safe("Dry run complete; no token read, requests submitted, or files changed.")
        return 0
    token = api.load_token()
    S.STOP_EVENT.clear()
    try:
        with token_lock(token):
            return download(args, frame, directory, token)
    except KeyboardInterrupt:
        S.STOP_EVENT.set()
        print_safe("Interrupted. Rerun the same command to resume saved task URLs.")
        return 130
