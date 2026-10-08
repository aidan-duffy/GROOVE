"""Resume contracts exercised with real cleaning and deterministic interruptions."""
from pathlib import Path
import json
import pandas as pd
import pytest
import yaml
from groove import config, pipeline, resume
from groove.demo import create
from groove.cli import build_parser


def sample(tmp_path):
    path = create(tmp_path / 'demo')
    for file in sorted((path.parent / 'raw').glob('*.csv'))[3:]:
        file.unlink()
    raw = yaml.safe_load(path.read_text())
    raw['clean'].update(make_summary_plots=False, make_reason_plot=False, make_example_plots=False)
    raw['periods'].update(run_bls=False, plot_mode='none', auto_plot_alias_suspects=False,
                          auto_plot_harmonic_suspects=False, max_period_days=20, ls_samples_per_peak=2)
    path.write_text(yaml.safe_dump(raw))
    return config.load(path)


def test_clean_interrupt_resume_and_force(tmp_path, monkeypatch):
    from groove.clean import cuts
    cfg = sample(tmp_path)
    original = cuts.clean_atlas_df
    calls = []
    def interrupted(frame):
        calls.append(1)
        if len(calls) == 2:
            raise KeyboardInterrupt()
        return original(frame)
    monkeypatch.setattr(cuts, 'clean_atlas_df', interrupted)
    with pytest.raises(KeyboardInterrupt):
        pipeline.run_clean(cfg)
    first = next(cfg.clean_dir.glob('*_cleaned.csv'))
    before = first.stat().st_mtime_ns
    monkeypatch.setattr(cuts, 'clean_atlas_df', lambda f: (calls.append(1), original(f))[1])
    pipeline.run_clean(cfg)
    assert len(calls) == 4  # First completed curve was not re-cleaned.
    assert first.stat().st_mtime_ns == before
    pipeline.run_clean(cfg)
    assert len(calls) == 4
    pipeline.run_clean(cfg, rerun=True)
    assert len(calls) == 7
    assert first.stat().st_mtime_ns != before


def test_changed_raw_and_missing_output_invalidate_only_affected_clean_source(tmp_path, monkeypatch):
    from groove.clean import cuts
    cfg = sample(tmp_path)
    pipeline.run_clean(cfg)
    calls = []
    original = cuts.clean_atlas_df
    monkeypatch.setattr(cuts, 'clean_atlas_df', lambda f: (calls.append(1), original(f))[1])
    deleted = next(cfg.clean_dir.glob('*_cleaned.csv'))
    deleted.unlink()
    pipeline.run_clean(cfg)
    assert len(calls) == 1 and deleted.is_file()
    raw = next(cfg.raw_lightcurves.glob('*.csv'))
    raw.write_text(raw.read_text() + '\n')
    pipeline.run_clean(cfg)
    assert len(calls) == 2


def test_selection_preserves_unchanged_inputs_on_resume(tmp_path):
    cfg = sample(tmp_path)
    pipeline.run_clean(cfg)
    pipeline.run_select(cfg)
    before = {str(p): p.stat().st_mtime_ns for p in cfg.selected_dir.glob('*_cleaned.csv')}
    # Invalidate the stage receipt, ensuring the staging loop itself is exercised.
    (cfg.output_folder / '.groove_state/select.json').unlink()
    pipeline.run_select(cfg)
    assert before == {str(p): p.stat().st_mtime_ns for p in cfg.selected_dir.glob('*_cleaned.csv')}


def test_full_run_resumes_completed_stages_and_forces_recalculation(tmp_path, monkeypatch):
    cfg = sample(tmp_path)
    from groove.periods import run as periods
    original = periods.main
    monkeypatch.setattr(periods, 'main', lambda: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        pipeline.run_all(cfg, skip_download=True, skip_morphology=True)
    cleaned = {str(p): p.stat().st_mtime_ns for p in cfg.clean_dir.glob('*_cleaned.csv')}
    selected = {str(p): p.stat().st_mtime_ns for p in cfg.selected_dir.glob('*_cleaned.csv')}
    monkeypatch.setattr(periods, 'main', original)
    pipeline.run_all(cfg, skip_download=True, skip_morphology=True)
    assert cleaned == {str(p): p.stat().st_mtime_ns for p in cfg.clean_dir.glob('*_cleaned.csv')}
    assert selected == {str(p): p.stat().st_mtime_ns for p in cfg.selected_dir.glob('*_cleaned.csv')}
    before = resume.snapshot([cfg.output_folder])
    pipeline.run_all(cfg, skip_download=True, skip_morphology=True)
    assert before == resume.snapshot([cfg.output_folder])
    pipeline.run_all(cfg, skip_download=True, skip_morphology=True, rerun=True)
    assert cleaned != {str(p): p.stat().st_mtime_ns for p in cfg.clean_dir.glob('*_cleaned.csv')}


def test_period_interrupt_reuses_source_journal_without_full_table_checkpoint(tmp_path, monkeypatch):
    from groove.periods import loading
    cfg = sample(tmp_path)
    pipeline.run_clean(cfg)
    pipeline.run_select(cfg)
    original = loading.prepare_series
    calls = []
    def interrupted(frame, band):
        calls.append(band)
        if len(calls) == 3:
            raise KeyboardInterrupt()
        return original(frame, band)
    monkeypatch.setattr(loading, 'prepare_series', interrupted)
    with pytest.raises(KeyboardInterrupt):
        pipeline.run_periods(cfg)
    assert not (cfg.periods_dir / 'tables/ls_period_search_summary.csv').exists()
    assert len(list((cfg.periods_dir / 'tables/source_checkpoints').glob('*.json'))) == 1
    calls.clear()
    monkeypatch.setattr(loading, 'prepare_series', lambda f, b: (calls.append(b), original(f, b))[1])
    pipeline.run_periods(cfg)
    assert len(calls) == 4  # Two bands for each remaining source only.
    result = pd.read_csv(cfg.periods_dir / 'tables/ls_period_search_summary.csv')
    assert len(result) == 6 and not result[['file', 'series']].duplicated().any()


def test_product_reuse_and_damage_repair(tmp_path):
    import matplotlib.pyplot as plt
    path = tmp_path / 'plot.png'
    with resume.products(tmp_path / 'receipts', 'same'):
        fig, ax = plt.subplots()
        ax.plot([1, 2])
        fig.savefig(path)
        before = path.stat().st_mtime_ns
        fig.savefig(path)
        assert path.stat().st_mtime_ns == before
        path.write_bytes(b'broken')
        fig.savefig(path)
        assert path.stat().st_mtime_ns != before
        plt.close(fig)
    assert not list(tmp_path.glob('*.tmp'))


@pytest.mark.parametrize('command', ['run', 'download', 'clean', 'select', 'periods', 'morphology'])
def test_rerun_cli_available_for_every_stage(command):
    assert build_parser().parse_args([command, '--rerun', '-c', 'run.yaml']).rerun
    assert build_parser().parse_args([command, '-c', 'run.yaml', '--rerun']).rerun


def test_period_plot_interrupt_preserves_search_and_alias_inventory(tmp_path, monkeypatch):
    from groove.periods import plots, loading
    cfg = sample(tmp_path)
    # Use the whole 12-source field for meaningful alias-memory counts.
    path = create(tmp_path / 'larger')
    large = config.load(path)
    large.clean = cfg.clean
    large.periods = cfg.periods
    pipeline.run_clean(large)
    pipeline.run_select(large)
    original = plots.plot_from_saved_results
    monkeypatch.setattr(plots, 'plot_from_saved_results', lambda *a: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        pipeline.run_periods(large)
    memory = large.periods_dir / 'tables/field_alias_memory.csv'
    before = pd.read_csv(memory) if memory.exists() else None
    monkeypatch.setattr(plots, 'plot_from_saved_results', original)
    monkeypatch.setattr(loading, 'prepare_series', lambda *a: (_ for _ in ()).throw(AssertionError('LS search repeated')))
    pipeline.run_periods(large)
    if before is not None:
        after = pd.read_csv(memory)
        pd.testing.assert_frame_equal(before.drop(columns='updated_utc'), after.drop(columns='updated_utc'))


def test_morphology_output_repair_reuses_saved_fit_and_features(tmp_path, monkeypatch):
    from groove.morphology import plots, embedding, features, persistence
    path = create(tmp_path / 'morph')
    raw = yaml.safe_load(path.read_text())
    raw['clean'].update(make_summary_plots=False, make_reason_plot=False, make_example_plots=False)
    raw['periods'].update(run_bls=False, plot_mode='none', auto_plot_alias_suspects=False,
                          auto_plot_harmonic_suspects=False, max_period_days=20, ls_samples_per_peak=2)
    raw['morphology'].update(make_maps=False, make_category_appendix=False,
                              make_category_folds=False, n_jobs=1)
    path.write_text(yaml.safe_dump(raw))
    cfg = config.load(path)
    real_extractor = features.extract_source_features
    # Keep the scientific fits real, but omit expensive example/neighbour sheets.
    monkeypatch.setattr(plots, 'build_neighbour_review_pages', lambda *a, **k: None)
    pipeline.run_all(cfg, skip_download=True)
    _, model = persistence.resolve_version_dir(cfg.morphology_dir, cfg.morphology['model_version'])
    checkpoint = persistence.finalisation_checkpoint_path(model)
    assert checkpoint.is_file()
    phase = persistence.figure_directory(model) / 'source_plots/phase_folded'
    files = sorted(phase.glob('*.png'))
    assert len(files) == 12
    unchanged = files[1].stat().st_mtime_ns
    before = resume.snapshot([model / 'models'])
    files[0].write_bytes(b'interrupted PNG')
    monkeypatch.setattr(embedding, 'fit_representation', lambda *a, **k: (_ for _ in ()).throw(AssertionError('UMAP refitted')))
    monkeypatch.setattr(features, 'extract_source_features', lambda *a, **k: (_ for _ in ()).throw(AssertionError('Features repeated')))
    pipeline.run_all(cfg, skip_download=True)
    assert resume.snapshot([model / 'models']) == before
    assert files[1].stat().st_mtime_ns == unchanged
    from PIL import Image
    with Image.open(files[0]) as picture:
        picture.verify()
    # A third full invocation skips the repaired completed stages, including fit.
    pipeline.run_all(cfg, skip_download=True)

    # Interrupt a transform after its numerical work but before its output pass.
    import dataclasses
    from groove.morphology import modes
    new_root = tmp_path / 'new_sample'
    new_raw = new_root / 'raw'
    new_raw.mkdir(parents=True)
    first_raw = sorted(cfg.raw_lightcurves.glob('*.csv'))[0]
    old_id = '3216489845356186496'
    new_id = '3216489845356187777'
    (new_raw / f'synthetic__GaiaDR3_{new_id}.csv').write_text(first_raw.read_text().replace(old_id, new_id))
    transformed = dataclasses.replace(cfg, name='second_sample', input_folder=new_raw,
        output_folder=new_root / 'results', clean=dict(cfg.clean), periods=dict(cfg.periods),
        morphology={**cfg.morphology, 'mode': 'transform', 'output_root': str(cfg.morphology_dir),
                    'batch_id': 'second_sample'})
    monkeypatch.setattr(features, 'extract_source_features', real_extractor)
    real_finalise = modes.finalise
    monkeypatch.setattr(modes, 'finalise', lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        pipeline.run_all(transformed, skip_download=True)
    assert list((model / 'cache').glob('transform_*.joblib'))
    monkeypatch.setattr(modes, 'finalise', real_finalise)
    monkeypatch.setattr(embedding, 'transform_representation', lambda *a, **k: (_ for _ in ()).throw(AssertionError('Transform repeated')))
    pipeline.run_all(transformed, skip_download=True)
    catalogue = pd.read_csv(model / 'tables/all_sources.csv', dtype={'source_id': str})
    assert len(catalogue) == 13 and new_id in set(catalogue.source_id)
    assert not catalogue.source_id.duplicated().any()
    pipeline.run_all(transformed, skip_download=True)


def test_visual_period_setting_change_does_not_repeat_search(tmp_path, monkeypatch):
    from groove.periods import loading
    cfg = sample(tmp_path)
    pipeline.run_clean(cfg)
    pipeline.run_select(cfg)
    pipeline.run_periods(cfg)
    cfg.periods['plot_dpi'] = 111
    monkeypatch.setattr(loading, 'prepare_series', lambda *a: (_ for _ in ()).throw(AssertionError('Scientific search repeated')))
    pipeline.run_periods(cfg)


def test_failed_period_source_is_retried(tmp_path, monkeypatch):
    from groove.periods import loading
    cfg = sample(tmp_path)
    pipeline.run_clean(cfg)
    pipeline.run_select(cfg)
    original = loading.prepare_series
    calls = []
    def fail_once(frame, band):
        calls.append(band)
        if len(calls) == 1:
            raise ValueError('simulated bad source')
        return original(frame, band)
    monkeypatch.setattr(loading, 'prepare_series', fail_once)
    with pytest.raises(RuntimeError, match='sources failed'):
        pipeline.run_periods(cfg)
    calls.clear()
    monkeypatch.setattr(loading, 'prepare_series', lambda f, b: (calls.append(b), original(f, b))[1])
    pipeline.run_periods(cfg)
    assert len(calls) == 2
    result = pd.read_csv(cfg.periods_dir / 'tables/ls_period_search_summary.csv')
    assert len(result) == 6 and not result.status.eq('failed').any()


def test_clean_plot_interrupt_reuses_existing_product(tmp_path, monkeypatch):
    from groove.clean import plots, cuts
    cfg = sample(tmp_path)
    cfg.clean.update(make_summary_plots=True, make_reason_plot=True, save_pdf=False)
    original = plots.make_reason_figure
    monkeypatch.setattr(plots, 'make_reason_figure', lambda *a: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        pipeline.run_clean(cfg)
    png = next(cfg.clean_plots.glob('*.png'))
    before = png.stat().st_mtime_ns
    monkeypatch.setattr(plots, 'make_reason_figure', original)
    monkeypatch.setattr(cuts, 'clean_atlas_df', lambda *a: (_ for _ in ()).throw(AssertionError('Cleaning repeated')))
    pipeline.run_clean(cfg)
    assert png.stat().st_mtime_ns == before


def test_empty_period_summary_is_recovered_from_source_journals(tmp_path, monkeypatch):
    from groove.periods import loading
    cfg = sample(tmp_path)
    pipeline.run_clean(cfg)
    pipeline.run_select(cfg)
    pipeline.run_periods(cfg)
    summary = cfg.periods_dir / 'tables/ls_period_search_summary.csv'
    summary.write_bytes(b'')
    monkeypatch.setattr(loading, 'prepare_series', lambda *a: (_ for _ in ()).throw(AssertionError('Search repeated during table repair')))
    pipeline.run_periods(cfg)
    assert len(pd.read_csv(summary)) == 6
