"""Plot discovery, legacy loading and actual alias correction regressions."""
from pathlib import Path
import pandas as pd
import yaml
from groove.morphology import persistence, plots


def test_visuals_and_saved_state_have_separate_clear_paths(tmp_path):
    root = tmp_path / 'results/4_morphology'
    state = persistence.version_directory(root, 'demo')
    persistence.ensure_structure(state)
    assert state == root / 'saved_runs/demo'
    figures = persistence.figure_directory(state)
    assert figures == tmp_path / 'results/plots/ML/demo'
    assert (figures / 'maps').is_dir() and (figures / 'source_plots').is_dir()
    assert (state / 'models').is_dir() and not (state / 'maps').exists()
    assert persistence.figure_directory(root / 'classification') == tmp_path / 'results/plots/ML/classification'


def test_legacy_models_can_be_loaded_without_retraining(tmp_path):
    root = tmp_path / 'results/4_morphology'
    old = root / 'model_versions/model_demo'
    old.mkdir(parents=True)
    assert persistence.resolve_version_dir(root, 'demo') == ('demo', old)
    assert persistence.figure_directory(old) == tmp_path / 'results/plots/ML/demo'
    new = persistence.version_directory(root, 'demo')
    new.mkdir(parents=True)
    assert persistence.resolve_version_dir(root, 'demo') == ('demo', new)


def test_new_map_links_to_the_new_phase_plot_location(tmp_path):
    import matplotlib.pyplot as plt
    state = persistence.version_directory(tmp_path / 'results/4_morphology', 'demo')
    persistence.ensure_structure(state)
    figures = persistence.figure_directory(state)
    gid = '3216489845356186496'
    picture = figures / 'source_plots/phase_folded' / (gid + '__phase_fold.png')
    picture.parent.mkdir(parents=True)
    fig, ax = plt.subplots(); ax.plot([0, 1], [0, 1]); fig.savefig(picture); plt.close(fig)
    table = pd.DataFrame({'source_id': [gid], 'dataset': ['T'],
        'final_primary_tag': ['wavelike'], 'recommended_period_days': [8.3],
        'combined_umap_1': [0.], 'combined_umap_2': [1.]})
    plots.make_interactive_map(table, 'combined_umap_1', 'combined_umap_2',
        'Test', 'test', state, {}, False)
    html = (figures / 'maps/test_interactive.html').read_text()
    import json, re
    data = json.loads(re.search(r'"customdata":(\[\[.*?\]\])', html).group(1))
    assert data[0][0] == gid
    assert (figures / 'maps' / data[0][5]).resolve() == picture.resolve()
    assert not (state / 'maps').exists()


def test_alias_rank_two_recovers_injected_stellar_period(tmp_path):
    from groove.demo import create
    from groove import config, pipeline
    path = create(tmp_path / 'alias', extended=True)
    for file in (path.parent / 'raw').glob('*.csv'):
        if '3216489845356186519' not in file.name:
            file.unlink()
    raw = yaml.safe_load(path.read_text())
    raw['clean'].update(make_summary_plots=False, make_reason_plot=False, make_example_plots=False)
    raw['periods'].update(series_to_run=['combined', 'o', 'c'], run_bls=False, plot_mode='none',
        auto_plot_alias_suspects=False, auto_plot_harmonic_suspects=False)
    path.write_text(yaml.safe_dump(raw))
    cfg = config.load(path)
    pipeline.run_clean(cfg); pipeline.run_select(cfg); pipeline.run_periods(cfg)
    tables = cfg.periods_dir / 'tables'
    summary = pd.read_csv(tables / 'ls_period_search_summary.csv')
    combined = summary.loc[summary.series.eq('combined')].iloc[0]
    assert abs(combined.raw_ls_best_period_days - 1) < .01
    assert combined.alias_correction_applied
    assert abs(combined.alias_corrected_period_days / 8.3 - 1) < .001
    peaks = pd.read_csv(tables / 'ls_period_search_peaks.csv')
    ranked = peaks.loc[peaks.series.eq('combined')].sort_values('rank')
    assert abs(ranked.iloc[1].period_days / 8.3 - 1) < .001
    assert ranked.iloc[0].power > ranked.iloc[1].power
    recommendations = pd.read_csv(tables / 'source_period_recommendations.csv')
    assert abs(recommendations.recommended_period_days.iloc[0] / 8.3 - 1) < .001


def test_distinct_custom_model_roots_do_not_share_visuals(tmp_path):
    first = persistence.version_directory(tmp_path / 'first', 'demo')
    second = persistence.version_directory(tmp_path / 'second', 'demo')
    assert persistence.figure_directory(first) != persistence.figure_directory(second)
    assert persistence.figure_directory(first).is_relative_to(tmp_path / 'first')
