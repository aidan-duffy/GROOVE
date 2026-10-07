"""Plot changes preserve scientific state and identify dataset membership."""
import argparse
import hashlib
import pandas as pd
import pytest
from groove.morphology import plots, persistence


def table():
    return pd.DataFrame({'source_id': ['100', '101', '102', '103'],
        'source_key': ['a100', 'a101', 'b102', 'b103'],
        'dataset': ['reference', 'reference', 'demo', 'demo'],
        'final_primary_tag': ['wavelike'] * 4,
        'recommended_period_days': [8.] * 4,
        'is_latest_batch': [False, False, True, True],
        **{name + '_umap_' + str(axis): [0., 1., 2., 3.]
           for name in ['combined', 'periodic', 'classification_evidence'] for axis in [1, 2]}})


def test_marker_mapping_validation():
    assert plots.validate_dataset_markers(None) == {}
    assert plots.validate_dataset_markers({'demo': 'diamond'}) == {'demo': 'diamond'}
    with pytest.raises(ValueError):
        plots.validate_dataset_markers({'demo': 'typo'})


def test_interactive_dataset_shapes_and_comparison_controls(tmp_path):
    plots.make_interactive_map(table(), 'combined_umap_1', 'combined_umap_2',
        'Test', 'test', tmp_path, {}, True, dataset_markers={'demo': 'diamond'})
    html = (tmp_path / 'maps/test_interactive.html').read_text()
    assert '"symbol":"diamond"' in html and '"symbol":"circle"' in html
    assert 'Dataset: demo' in html and 'Dataset: reference' in html
    assert 'plotly_selected' in html and 'Compare selected light curves' in html
    assert 'selected.has(key)' in html and 'Clear selection' in html


def test_map_only_preserves_catalogue_and_models(tmp_path, monkeypatch):
    state = persistence.version_directory(tmp_path / 'results/4_morphology', 'ref')
    persistence.ensure_structure(state)
    catalogue = state / 'tables/all_sources.csv'
    table().to_csv(catalogue, index=False)
    model = state / 'models/frozen.joblib'
    model.write_bytes(b'frozen model must never be loaded or changed')
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in [catalogue, model]}
    def forbidden(*args, **kwargs):
        raise AssertionError('map-only must not recompute scientific state')
    monkeypatch.setattr(plots._embedding, 'fit_representation', forbidden)
    monkeypatch.setattr(plots._classify, 'classify_table', forbidden)
    monkeypatch.setattr(plots._features, 'extract_all_features', forbidden)
    config = {'output_root': str(state.parent.parent), 'model_version': 'ref',
              'dataset_markers': {'demo': 'diamond'}, 'outline_new_sources': True}
    plots.map_only(config, argparse.Namespace(outline_new=False, no_outline_new=False))
    maps = persistence.figure_directory(state) / 'maps'
    assert len(list(maps.glob('*interactive.html'))) == 3
    assert before == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in before}
    config['maps_to_plot'] = ['classification_evidence', 'combined']
    plots.map_only(config, argparse.Namespace(outline_new=False, no_outline_new=False))
    assert len(list(maps.glob('*interactive.html'))) == 2
