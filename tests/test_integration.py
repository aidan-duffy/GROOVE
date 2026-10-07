"""Scientific and stage-contract regressions on seeded synthetic observations."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import pytest
from groove import config, pipeline
from groove.cli import main
from groove.select import criteria, settings as selection
from groove.clean import cuts, loading
from groove.periods import settings as period_settings


def make_config(tmp_path):
    path = tmp_path/'run.yaml'
    path.write_text('''name: T
output_folder: out
clean:
  make_summary_plots: false
  make_reason_plot: false
  make_example_plots: false
periods:
  max_period_days: 30
  run_bls: false
  plot_mode: none
  auto_plot_harmonic_suspects: false
morphology:
  mode: classify
  n_jobs: 1
''')
    cfg = config.load(path)
    cfg.raw_lightcurves.mkdir(parents=True)
    from test_pipeline import synthetic_raw
    synthetic_raw(cfg.raw_lightcurves, n=500)
    return cfg


def test_end_to_end_period_recovery_and_single_star_classification(tmp_path):
    cfg = make_config(tmp_path)
    pipeline.run_all(cfg, skip_download=True)
    table = pd.read_csv(cfg.periods_dir/'tables/source_period_recommendations.csv', dtype={'source_id':str})
    assert table.source_id.tolist() == ['3216489845356186496']
    assert abs(table.recommended_period_days[0] / 12.7 - 1) < 0.01
    morphology = pd.read_csv(cfg.morphology_dir/'classification/tables/all_sources.csv', dtype={'source_id':str})
    assert morphology.source_id.tolist() == table.source_id.tolist()
    assert morphology.final_primary_tag[0] == 'wavelike'
    assert abs(morphology.recommended_period_days[0] / table.recommended_period_days[0] - 1) < 1e-9
    staged = pd.read_csv(cfg.selected_dir/'selected_sources.csv', dtype={'gaia_dr3':str})
    assert staged.gaia_dr3.tolist() == table.source_id.tolist()
    assert len(list((cfg.output_folder/'plots/ML/classification/source_plots').rglob('*.png'))) == 1
    manifest = json.loads((cfg.output_folder/'pipeline_run.json').read_text())
    assert manifest['stages'] == ['clean','select','periods','morphology']


def test_cached_periods_recompute_when_range_changes(tmp_path):
    cfg = make_config(tmp_path)
    pipeline.run_clean(cfg)
    pipeline.run_select(cfg)
    pipeline.run_periods(cfg)
    cfg.periods['max_period_days'] = 8
    pipeline.run_periods(cfg)
    table = pd.read_csv(cfg.periods_dir/'tables/ls_period_search_summary.csv')
    assert table.raw_ls_best_period_days.dropna().le(8.01).all()


def test_stage_overrides_do_not_leak(tmp_path, monkeypatch):
    path=tmp_path/'run.yaml'; path.write_text('output_folder: out\n')
    cfg=config.load(path)
    from groove.periods import run
    monkeypatch.setattr(run, 'main', lambda: None)
    cfg.periods={'max_period_days':100, 'plot_time_segments':4}
    pipeline.run_periods(cfg)
    assert period_settings.MAX_PERIOD_DAYS == 100
    assert len(period_settings.PLOT_TIME_SEGMENT_COLORS) == 4
    cfg.periods={}
    pipeline.run_periods(cfg)
    assert period_settings.MAX_PERIOD_DAYS == 200
    assert len(period_settings.PLOT_TIME_SEGMENT_COLORS) == period_settings.PLOT_TIME_SEGMENTS


def test_morphology_nested_settings_and_reference_paths(tmp_path):
    path=tmp_path/'run.yaml'
    path.write_text('output_folder: out\nmorphology:\n  thresholds: {flare_min_events: 7}\n  output_root: shared_models\n')
    cfg=config.load(path); m=pipeline.morphology_config(cfg)
    assert m['thresholds']['flare_min_events'] == 7
    assert 'transit_dip_snr' in m['thresholds']
    assert m['output_root'] == str(tmp_path/'shared_models')
    assert m['datasets'][0]['existing_plot_directories'] == [str(cfg.period_plots)]


def test_eligible_band_must_also_meet_error_cut():
    table=pd.DataFrame({'n_final_keep':[600], 'n_c_clean':[1], 'n_o_clean':[599],
                        'baseline_days_clean':[1000], 'fraction_kept':[.9],
                        'median_dm_c_clean':[.01], 'median_dm_o_clean':[.5], 'status':['ok']})
    assert not criteria.evaluate(table).selected[0]


def test_cleaner_keeps_noise_consistent_negative_flux_and_metadata():
    frame=pd.DataFrame({'MJD':[58000,58001,58002], 'F':['o']*3,
                        'uJy':[-1.,10.,-100.], 'duJy':[2.]*3,
                        'target_GaiaDR3':['3216489845356186496']*3,
                        'target_group':['A']*3, 'target_catalogue_period_days':[12.7]*3,
                        'target_ra_used':[84.]*3,'target_dec_used':[-2.5]*3})
    out, summary=cuts.clean_atlas_df(frame)
    assert out.final_keep.tolist() == [True,True,False]
    metadata=loading.get_metadata_from_df(out,'example')
    assert metadata[1] == '3216489845356186496'
    assert metadata[3] == 'A'
    assert metadata[5] == 12.7


@pytest.mark.parametrize('text', ['[]','output_folder: ""','output_folder: out\nwrong_key: true', 'output_folder: out\nperiods: []', 'output_folder: out\nphotometry: invalid'])
def test_invalid_config_is_clear(tmp_path,text):
    path=tmp_path/'bad.yaml'; path.write_text(text)
    with pytest.raises(ValueError): config.load(path)
    assert main(['run','-c',str(path)]) == 1


def test_pipeline_stops_if_download_fails(tmp_path,monkeypatch):
    cfg=make_config(tmp_path)
    monkeypatch.setattr(pipeline,'run_download',lambda cfg:1)
    def unexpected(cfg): raise AssertionError('next stage must not run')
    monkeypatch.setattr(pipeline,'run_clean',unexpected)
    with pytest.raises(RuntimeError,match='download stopped'): pipeline.run_all(cfg)


def test_cyan_only_morphology_plot_has_observations():
    import matplotlib.pyplot as plt
    from groove.morphology.plots import _fold_scatter
    frame=pd.DataFrame({'time':np.linspace(0,100,100), 'mag':14+np.sin(np.linspace(0,20,100)), 'filter':['c']*100})
    fig,ax=plt.subplots()
    _fold_scatter(ax,frame,12.7,0)
    assert any(len(line.get_xdata()) for line in ax.lines)
    assert not ax.texts
    plt.close(fig)


def test_highlight_loads_cyan_only_source(tmp_path, monkeypatch):
    from argparse import Namespace
    from groove.morphology import modes, settings, loading
    gid = '3216489845356186496'
    key = 'T::' + gid
    raw = tmp_path / 'raw'
    raw.mkdir()
    pd.DataFrame({'MJD': np.linspace(58000, 59000, 100),
                  'm': 14 + .2 * np.sin(np.linspace(0, 50, 100)),
                  'dm': .02, 'F': 'c', 'source_id': gid}).to_csv(
        raw / ('GaiaDR3_' + gid + '_cleaned.csv'), index=False)
    version = tmp_path / 'model'
    (version / 'tables').mkdir(parents=True)
    pd.DataFrame({'source_id': [gid], 'source_key': [key], 'dataset': ['T'],
                  'final_primary_tag': ['wavelike'],
                  'recommended_period_days': [12.7],
                  'combined_umap_1': [0.], 'combined_umap_2': [0.]}).to_csv(
        version / 'tables/all_sources.csv', index=False)
    monkeypatch.setattr(modes._persistence, 'resolve_version_dir',
                        lambda *a: ('test', version))
    monkeypatch.setattr(modes._embedding, 'frozen_source_neighbours',
                        lambda *a: (pd.DataFrame(columns=['space', 'source_key', 'distance']), [key]))
    monkeypatch.setattr(modes._plots, 'make_static_map', lambda *a: None)
    seen = {}
    original = loading.load_selected_lightcurves
    def record_inputs(*args):
        records = original(*args)
        seen.update(records)
        return records
    monkeypatch.setattr(loading, 'load_selected_lightcurves', record_inputs)
    cfg = dict(settings.DEFAULTS)
    cfg.update(output_root=str(tmp_path), datasets=[{
        'name': 'T', 'lightcurve_inputs': [str(raw)]}])
    args = Namespace(verbose=False, source_id=gid, source_label='cyan_test',
                     map_name='combined', nearest_neighbours=3, diagnostic_folds=True)
    modes.highlight_source_mode(cfg, args)
    assert gid in seen
    assert len(seen[gid]['data']) == 100
    assert set(seen[gid]['data']['filter']) == {'c'}
    assert len(list((version / 'maps/additions/cyan_test').glob('*.png'))) == 3


def test_corrupt_period_png_is_not_reused(tmp_path):
    from groove.periods.files import output_file_is_complete, save_figure
    import matplotlib.pyplot as plt
    path = tmp_path / 'plot.png'
    path.write_bytes(b'\x89PNG\r\n\x1a\ninterrupted')
    assert not output_file_is_complete(path)
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    save_figure(fig, path)
    plt.close(fig)
    assert output_file_is_complete(path)
    assert not list(tmp_path.glob('plot_*.tmp'))


def test_interactive_map_links_to_saved_phase_image(tmp_path):
    from groove.morphology.plots import make_interactive_map
    import matplotlib.pyplot as plt
    gid = '3216489845356186496'
    picture = tmp_path / 'source_plots/phase_folded' / (gid + '__phase_fold.png')
    picture.parent.mkdir(parents=True)
    fig, ax = plt.subplots(); ax.plot([0, 1], [0, 1]); fig.savefig(picture); plt.close(fig)
    table = pd.DataFrame({'source_id': [gid], 'dataset': ['test'],
                          'final_primary_tag': ['wavelike'],
                          'recommended_period_days': [12.7],
                          'combined_umap_1': [0.], 'combined_umap_2': [1.]})
    make_interactive_map(table, 'combined_umap_1', 'combined_umap_2', 'Test',
                         'test', tmp_path, {}, False)
    text = (tmp_path / 'maps/test_interactive.html').read_text()
    assert gid in text and 'plotly_click' in text
    assert '__phase_fold.png' in text and 'cdn.plot.ly' not in text.split('<script')[0]
    assert 'plotly.js v' in text
