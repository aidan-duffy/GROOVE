"""The `groove` command."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, config, pipeline


def cmd_init(args):
    out = Path(args.path)
    if out.exists() and not args.force:
        sys.exit(f"{out} exists (use --force to overwrite)")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(config.EXAMPLE, encoding="utf-8")
    print(f"Wrote {out}. Edit it, then run:  groove run --config {out}")


def cmd_targets(args):
    """Summarise a target list: how many rows, and the values of a grouping column."""
    import pandas as pd
    df = pd.read_csv(args.targets, dtype=str)
    print(f"{args.targets}: {len(df):,} rows, {len(df.columns)} columns")
    print("Columns:", ", ".join(df.columns))
    column = args.by
    if column is None:
        column = next((c for c in ("group", "Group", "field", "Field", "sample",
                                   "cluster_name", "Cluster", "cluster", "Name")
                       if c in df.columns), None)
    if column is None:
        print("\nNo grouping column detected. Use --by <column> to summarise one.")
        return
    if column not in df.columns:
        raise SystemExit(f"Column {column!r} not in {args.targets}. Columns: {', '.join(df.columns)}")
    counts = df[column].value_counts()
    print(f"\nValues of {column!r} ({len(counts)} distinct):\n")
    for value, n in counts.head(args.limit).items():
        print(f"  {value:<40} {n:>8,}")
    if len(counts) > args.limit:
        print(f"  ... and {len(counts) - args.limit} more (use --limit)")
    print(f"\nUse one of these as `group:` in your config (with group_column: {column}).")


def cmd_stage(args):
    cfg = config.load(args.config)
    stage = args.command
    if stage == "run":
        pipeline.run_all(cfg, skip_download=args.skip_download, skip_morphology=args.skip_morphology)
    elif stage == "download":
        return pipeline.run_download(cfg, dry_run=args.dry_run, limit=args.limit)
    elif stage == "clean":
        pipeline.run_clean(cfg)
    elif stage == "select":
        pipeline.run_select(cfg)
    elif stage == "periods":
        pipeline.run_periods(cfg)
    elif stage == "morphology":
        pipeline.run_morphology(cfg, extra_args=args.morphology_args)


def cmd_demo(args):
    from .demo import create
    path = create(args.path)
    print(f"Created synthetic demonstration. Run: groove run -c {path} --skip-download")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="groove", description="ATLAS light-curve variability and occultation search.")
    p.add_argument("--version", action="version", version=f"groove {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("init", help="write an example config file")
    s.add_argument("path", nargs="?", default="my_cluster.yaml")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("demo", help="create a token-free synthetic example")
    s.add_argument("path", nargs="?", default="groove_demo")
    s.set_defaults(func=cmd_demo)

    s = sub.add_parser("targets", help="summarise a target list and its grouping column")
    s.add_argument("targets")
    s.add_argument("--by", help="column to group by (default: auto-detect)")
    s.add_argument("--limit", type=int, default=40, help="how many values to print")
    s.set_defaults(func=cmd_targets)

    for name, helptext in (
        ("run", "run every stage in order"),
        ("download", "1. fetch ATLAS forced photometry"),
        ("clean", "2. point-level quality cuts"),
        ("select", "3. source-level usability cuts"),
        ("periods", "4. period search"),
        ("morphology", "5. morphology families and UMAP maps"),
    ):
        s = sub.add_parser(name, help=helptext)
        s.add_argument("--config", "-c", required=True)
        if name == "download":
            s.add_argument("--dry-run", action="store_true", help="list targets and estimate time; submit nothing")
            s.add_argument("--limit", type=int, help="only the first N targets (test run)")
        if name == "run":
            s.add_argument("--skip-morphology", action="store_true", help="stop after period search")
            s.add_argument("--skip-download", action="store_true", help="raw light curves already exist")
        if name == "morphology":
            s.add_argument("morphology_args", nargs=argparse.REMAINDER,
                           help="extra flags passed to the morphology stage, e.g. -- --mode transform --model-version X")
        s.set_defaults(func=cmd_stage)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args) or 0
    except (ValueError, KeyError, OSError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted; rerun the same command to resume.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
