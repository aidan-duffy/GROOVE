"""User-facing output choices must not silently change the scientific inputs."""
import importlib
import pytest
from groove.periods import settings, plots
from groove.morphology import settings as ml


def test_default_and_opt_in_maps():
    assert ml.selected_maps({}) == ['classification_evidence', 'combined', 'periodic']
    assert ml.selected_maps({'maps_to_plot': ['classification_evidence', 'transient']}) == ['classification_evidence', 'transient']
    with pytest.raises(ValueError):
        ml.selected_maps({'maps_to_plot': ['typo']})


def test_analysis_and_diagnostic_plot_series_are_independent(monkeypatch):
    monkeypatch.setattr(settings, 'SERIES_TO_RUN', ['o', 'c', 'combined'])
    monkeypatch.setattr(settings, 'PLOT_SERIES', ['o', 'c'])
    monkeypatch.setattr(settings, 'EXTRA_FOLD_SERIES_MODE', 'all')
    rows = [{'series': s} for s in ['combined', 'o', 'c']]
    assert [r['series'] for r in plots.choose_extra_fold_series_rows(rows, {})] == ['o', 'c']
    monkeypatch.setattr(settings, 'PLOT_SERIES', ['o', 'c', 'combined'])
    assert len(plots.choose_extra_fold_series_rows(rows, {})) == 3
    monkeypatch.setattr(settings, 'PLOT_SERIES', [])
    assert plots.choose_extra_fold_series_rows(rows, {}) == []


def test_defaults_exclude_combined_photometry():
    fresh = importlib.reload(settings)
    assert fresh.SERIES_TO_RUN == ['o', 'c']
    assert fresh.PLOT_SERIES == ['o', 'c']


def test_automatic_alias_folds_respect_plot_series(tmp_path, monkeypatch):
    import pandas as pd
    p = tmp_path / 'input.csv'
    p.write_text('time,mag\n1,14\n')
    monkeypatch.setattr(settings, 'SERIES_TO_RUN', ['o', 'c', 'combined'])
    monkeypatch.setattr(settings, 'PLOT_SERIES', ['combined'])
    monkeypatch.setattr(settings, 'OUTPUT_DIR', tmp_path)
    monkeypatch.setattr(settings, 'AUTO_PLOT_ALIAS_SUSPECTS', True)
    monkeypatch.setattr(settings, 'AUTO_PLOT_HARMONIC_SUSPECTS', False)
    monkeypatch.setattr(settings, 'ALIAS_SELECTED_FILES', [])
    monkeypatch.setattr(settings, 'HARMONIC_SELECTED_FILES', [])
    monkeypatch.setattr(plots._aliases, 'source_is_alias_suspect', lambda r: True)
    monkeypatch.setattr(plots._loading, 'normalise_columns', lambda df: df)
    monkeypatch.setattr(plots._loading, 'extract_metadata', lambda df, path: {'source_id': 's'})
    called = []
    def prepare(df, series):
        called.append(series)
        return {'series_name': series}
    monkeypatch.setattr(plots._loading, 'prepare_series', prepare)
    monkeypatch.setattr(plots, 'plot_alias_candidate_folds', lambda *args: None)
    rows = [{'file': p.name, 'source_id': 's', 'status': 'ok', 'series': s} for s in ['o', 'c', 'combined']]
    plots.generate_extra_phase_fold_diagnostics([p], rows, [], pd.DataFrame(), pd.DataFrame())
    assert called == ['combined']
