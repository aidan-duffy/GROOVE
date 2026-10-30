"""Plot changes preserve scientific state and identify dataset membership."""
import argparse
import hashlib
import json
import shutil
import subprocess

import pandas as pd
import pytest

from groove.morphology import persistence, plots


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
    html = (tmp_path / 'maps/test_interactive.html').read_text(encoding='utf-8')
    assert '"symbol":"diamond"' in html and '"symbol":"circle"' in html
    assert 'Dataset: demo' in html and 'Dataset: reference' in html
    assert 'plotly_selected' in html and 'Compare selected light curves' in html
    assert 'selected.has(key)' in html and 'Clear selection' in html
    assert 'width:420px;max-width:100%' in html
    assert 'height:320px;object-fit:contain' in html
    assert 'flex-wrap:wrap' in html
    assert '"scrollZoom": true' in html and '"displayModeBar": true' in html
    assert '"itemclick":"toggle"' in html
    assert '"itemdoubleclick":"toggleothers"' in html


@pytest.mark.skipif(shutil.which('node') is None, reason='Node.js is needed for the DOM event check')
def test_interactive_preview_click_toggles_and_selection_remains_additive(tmp_path):
    plots.make_interactive_map(table(), 'combined_umap_1', 'combined_umap_2',
        'Test', 'test', tmp_path, {}, False)
    html = (tmp_path / 'maps/test_interactive.html').read_text(encoding='utf-8')
    script = 'const graph = document.getElementById' + html.rsplit(
        'const graph = document.getElementById', 1)[1].split('</script>', 1)[0]
    script = script.rsplit('updateCount();', 1)[0] + 'updateCount();'
    harness = r'''
const assert = require('node:assert/strict');
const vm = require('node:vm');
const handlers = {};
class Element {
    constructor(tag) { this.tag = tag; this.children = []; this.style = {}; this.listeners = {}; }
    append(...items) { items.forEach(item => { item.parent = this; this.children.push(item); }); }
    appendChild(item) { this.append(item); }
    replaceChildren(...items) { this.children = []; this.append(...items); }
    setAttribute() {}
    addEventListener(name, handler) { this.listeners[name] = handler; }
    remove() { this.parent.children = this.parent.children.filter(item => item !== this); }
    after() {}
}
const graph = {id: 'test', on: (event, handler) => { handlers[event] = handler; }, after() {}};
const document = {getElementById: () => graph, createElement: tag => new Element(tag)};
const check = `
const a = ['100', 'reference', 'wavelike', 8, '', ''];
const b = ['101', 'reference', 'wavelike', 8, '', ''];
const point = detail => ({points: [{customdata: detail}]});
handlers.plotly_click(point(a)); assert.equal(board.children.length, 1);
handlers.plotly_click(point(a)); assert.equal(board.children.length, 0);
handlers.plotly_click(point(a)); assert.equal(board.children.length, 1);
handlers.plotly_click({points: [{customdata: a}, {customdata: a}]});
assert.equal(board.children.length, 0);
handlers.plotly_selected({points: [{customdata: a}, {customdata: b}]});
handlers.plotly_selected(point(a)); assert.equal(board.children.length, 2);
handlers.plotly_selected(null); assert.equal(board.children.length, 2);
handlers.plotly_click(point(a)); assert.equal(board.children.length, 1);
handlers.plotly_click(point(a)); assert.equal(board.children.length, 2);
board.children[0].children[1].listeners.click(); assert.equal(board.children.length, 1);
clear.listeners.click(); assert.equal(board.children.length, 0);
assert.equal(status.textContent, '0 selected'); assert.equal(clear.disabled, true);
`;
vm.runInNewContext(SCRIPT + check, {document, handlers, assert});
'''
    check = tmp_path / 'preview_events.cjs'
    check.write_text('const SCRIPT = ' + json.dumps(script) + ';\n' + harness, encoding='utf-8')
    result = subprocess.run([shutil.which('node'), str(check)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


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
