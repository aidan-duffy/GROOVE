"""Audit generated demonstrations without assuming forced morphology labels."""
from pathlib import Path
import json
import pandas as pd
from matplotlib.image import imread
from . import config
from .morphology import persistence, settings as morphology_settings


def check(directory: str | Path) -> dict:
    root = Path(directory).expanduser().resolve()
    cfg = config.load(root / 'run.yaml')
    truth = pd.read_csv(root / 'truth.csv', dtype={'source_id': str})
    tables = cfg.periods_dir / 'tables'
    periods = pd.read_csv(tables / 'source_period_recommendations.csv', dtype={'source_id': str})
    version = cfg.morphology.get('model_version', 'demo')
    _, model = persistence.resolve_version_dir(cfg.morphology_dir, version)
    figures = persistence.figure_directory(model)
    shapes = pd.read_csv(model / 'tables/all_sources.csv', dtype={'source_id': str})
    errors = []
    ids = set(truth.source_id)
    for name, table in [('periods', periods), ('morphology', shapes)]:
        if table.source_id.duplicated().any() or set(table.source_id) != ids:
            errors.append(f'{name}: duplicate or missing demo IDs')
    merged = truth.merge(periods, on='source_id', validate='one_to_one')
    merged = merged.merge(shapes[['source_id', 'final_primary_tag']], on='source_id', validate='one_to_one')
    known = merged.injected_shape.isin(['wavelike', 'dipping', 'cyan_only', 'orange_only'])
    merged['period_error_fraction'] = abs(merged.recommended_period_days / merged.injected_period_days - 1)
    if (merged.loc[known, 'period_error_fraction'].isna().any()
            or (merged.loc[known, 'period_error_fraction'] > .001).any()):
        errors.append('one or more coherent injected periods missed the 0.1% tolerance')
    if merged.loc[known, 'recommendation_label'].eq('weak_or_ambiguous').any():
        errors.append('coherent injected source routed to weak_or_ambiguous')
    expected_shapes = {'wavelike': 'wavelike', 'dipping': 'transit', 'nonvar': 'nonvar'}
    for kind, expected in expected_shapes.items():
        if not merged.loc[merged.injected_shape.eq(kind), 'final_primary_tag'].eq(expected).all():
            errors.append(f'baseline {kind} morphology differs from {expected}')
    manifest_path = tables / 'extra_phase_fold_diagnostics.csv'
    manifest = pd.read_csv(manifest_path, dtype={'source_id': str}) if manifest_path.exists() else pd.DataFrame()
    coverage = {}
    for kind, diagnostic in [('daily_systematic', 'alias_candidates'), ('unequal_eclipses', 'harmonic_tests'), ('alias_promoted', 'alias_candidates')]:
        source_ids = set(truth.loc[truth.injected_shape.eq(kind), 'source_id'])
        if not source_ids:
            continue
        matches = manifest.loc[manifest.source_id.isin(source_ids) & manifest.diagnostic_type.eq(diagnostic)]
        made = matches.loc[matches.status.isin(['made', 'reused'])]
        coverage[diagnostic] = coverage.get(diagnostic, 0) + len(made)
        if made.empty or not all(Path(p).is_file() for p in made.output_path):
            errors.append(f'{kind}: missing completed {diagnostic} figure')
    promoted_ids = set(truth.loc[truth.injected_shape.eq('alias_promoted'), 'source_id'])
    if promoted_ids:
        series = pd.read_csv(tables / 'ls_period_search_summary.csv', dtype={'source_id': str})
        promoted = series.loc[series.source_id.isin(promoted_ids) & series.series.isin(cfg.periods.get('series_to_run', ['o', 'c']))]
        valid = (len(promoted) >= len(promoted_ids) and set(promoted.source_id) == promoted_ids
                 and promoted.alias_correction_applied.astype(str).str.lower().eq('true').all()
                 and (abs(promoted.raw_ls_best_period_days - 1) < .02).all()
                 and (abs(promoted.alias_corrected_period_days / 8.3 - 1) < .001).all())
        if not valid:
            errors.append('alias_promoted: rank-1 daily alias did not promote the 8.3-day alternative')
    pngs = sorted(cfg.output_folder.rglob('*.png'))
    for path in pngs:
        try:
            imread(path)
        except Exception as exc:
            errors.append(f'Unreadable PNG {path}: {exc}')
    htmls = sorted((figures / 'maps').glob('*interactive.html'))
    expected_maps = morphology_settings.selected_maps(cfg.morphology) if cfg.morphology.get('make_maps', True) else []
    for name in expected_maps:
        basename = morphology_settings.MAP_DEFINITIONS[name][2]
        if not (figures / 'maps' / (basename + '_interactive.html')).is_file():
            errors.append(f'missing interactive map: {name}')
    series = pd.read_csv(tables / 'ls_period_search_summary.csv')
    if not set(series.series.dropna()).issubset(set(cfg.periods.get('series_to_run', ['o', 'c']))):
        errors.append('unexpected period-search series')
    summary = pd.read_csv(cfg.clean_dir / 'cleaning_summary.csv')
    # Detailed original cut boundaries are covered by the supplied audit_outputs.py.
    report = {'passed': not errors, 'errors': errors, 'sources': len(truth),
        'cleaned_summary_rows': len(summary), 'pngs_checked': len(pngs),
        'interactive_maps': len(htmls), 'diagnostic_coverage': coverage,
        'morphology_counts': shapes.final_primary_tag.value_counts().to_dict()}
    output = root / 'demo_check.json'
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    merged.to_csv(root / 'demo_source_review.csv', index=False)
    print(json.dumps(report, indent=2))
    print(f'Source-by-source review: {root / "demo_source_review.csv"}')
    if errors:
        raise RuntimeError('Demo audit failed; inspect demo_check.json')
    return report
