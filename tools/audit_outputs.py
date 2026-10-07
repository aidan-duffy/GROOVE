"""Audit a GROOVE synthetic demo; optionally compare supplied original scripts.

Usage: python audit_outputs.py demo --originals ../upload
Requires GROOVE plus Pillow (installed with matplotlib).
"""
from pathlib import Path
import argparse
import importlib.util
import json
import sys
import numpy as np
import pandas as pd
from PIL import Image
from groove.clean import cuts, settings as clean_settings
from groove.periods import periodograms, settings as period_settings
from groove.morphology import features, settings as morph_settings


def original(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def audit(demo, originals=None):
    report = {}
    result = demo / 'results'
    truth = pd.read_csv(demo / 'truth.csv', dtype={'source_id': str})
    periods = pd.read_csv(result / '3_periods/tables/source_period_recommendations.csv', dtype={'source_id': str})
    model = result / '4_morphology/saved_runs/demo'
    morphology = pd.read_csv(model / 'tables/all_sources.csv', dtype={'source_id': str})
    selected = pd.read_csv(result / '2_clean/selected/selected_sources.csv', dtype={'gaia_dr3': str})
    ids = set(truth.source_id)
    assert set(periods.source_id) == set(morphology.source_id) == set(selected.gaia_dr3) == ids
    joined = truth.merge(periods, on='source_id', validate='one_to_one')
    periodic = joined.loc[joined.injected_period_days.notna()]
    error = abs(periodic.recommended_period_days / periodic.injected_period_days - 1)
    assert error.max() < .001
    expected = {'wavelike': 'wavelike', 'dipping': 'transit', 'nonvar': 'nonvar'}
    labels = truth.merge(morphology, on='source_id', validate='one_to_one')
    assert (labels.injected_shape.map(expected) == labels.final_primary_tag).all()
    adopted = morphology[['source_id', 'recommended_period_days']].merge(
        periods[['source_id', 'recommended_period_days']], on='source_id', suffixes=('_morph', '_period'))
    np.testing.assert_allclose(adopted.recommended_period_days_morph, adopted.recommended_period_days_period)
    report['demo'] = {'sources': len(ids), 'periodic_sources': len(error),
                      'maximum_period_error_percent': float(100 * error.max()),
                      'shape_counts': morphology.final_primary_tag.value_counts().to_dict()}
    images = list(result.rglob('*.png'))
    assert images
    for path in images:
        with Image.open(path) as im:
            assert min(im.size) >= 100
            im.verify()
    report['png_files_decoded'] = len(images)
    html = list((result / 'plots/ML/demo').rglob('*interactive.html'))
    assert html and all(p.stat().st_size > 1000 for p in html)
    report['interactive_maps_present'] = len(html)

    # Independent known-good/bad observations, including exact cut boundaries.
    base = dict(MJD=58000., m=14., dm=.02, uJy=100., duJy=2., F='o',
                err=0, flags=0, x=5000., y=5000., maj=3., min=3.,
                apfit=-.5, mag5sig=19., Sky=19.)
    cases = [('valid', {}, True), ('invalid_time', {'MJD': np.nan}, False),
             ('invalid_flux', {'uJy': np.inf}, False),
             ('zero_flux_error', {'duJy': 0.}, False),
             ('invalid_magnitude', {'m': 31.}, False),
             ('zero_mag_error', {'dm': 0.}, False),
             ('unknown_filter', {'F': 'g'}, False),
             ('catastrophic_depth', {'mag5sig': 9.}, False),
             ('error_flag', {'err': 1}, False),
             ('excess_flux_error', {'duJy': 10001.}, False),
             ('strong_negative_flux', {'uJy': -12.}, False),
             ('snr_at_minus_five', {'uJy': -10.}, True),
             ('noise_negative_flux', {'uJy': -1., 'm': np.nan, 'dm': np.nan}, True),
             ('x_lower_boundary', {'x': 100.}, False),
             ('x_upper_boundary', {'x': 10460.}, False),
             ('y_lower_boundary', {'y': 100.}, False),
             ('y_upper_boundary', {'y': 10460.}, False),
             ('major_lower_boundary', {'maj': 1.6}, False),
             ('major_upper_boundary', {'maj': 5.}, False),
             ('minor_lower_boundary', {'min': 1.6}, False),
             ('minor_upper_boundary', {'min': 5.}, False),
             ('apfit_lower_boundary', {'apfit': -1.}, False),
             ('apfit_upper_boundary', {'apfit': -.1}, False),
             ('depth_boundary', {'mag5sig': 17.}, False),
             ('sky_boundary', {'Sky': 17.}, False),
             ('flags_ignored_by_default', {'flags': 1}, True)]
    input_frame = pd.DataFrame([dict(base, **{'case': name}) | updates for name, updates, _ in cases])
    clean_settings.RESCUE_ENABLE = False
    cleaned, _ = cuts.clean_atlas_df(input_frame)
    lookup = cleaned.set_index('case')
    rows = []
    for name, _, keep in cases:
        assert bool(lookup.loc[name, 'final_keep']) == keep, name
        rows.append({'case': name, 'expected_keep': keep,
                     'actual_keep': bool(lookup.loc[name, 'final_keep']),
                     'reason': str(lookup.loc[name, 'reject_reason'])})
    pd.DataFrame(rows).to_csv(demo.parent / 'cut_audit.csv', index=False)
    report['known_cut_cases_passed'] = len(rows)
    clean_settings.REQUIRE_FLAGS_ZERO = True
    strict, _ = cuts.clean_atlas_df(pd.DataFrame([base | {'flags': 1}]))
    assert not strict.final_keep.iloc[0]
    clean_settings.REQUIRE_FLAGS_ZERO = False

    rng = np.random.default_rng(123)
    t = np.sort(rng.uniform(0, 200, 600))
    injected = 5.3
    phase = (t / injected) % 1
    mag = 14 + .8 * (phase < .04) + rng.normal(0, .01, len(t))
    err = np.full(len(t), .01)
    period_settings.RUN_BLS = True
    period_settings.BLS_MAX_PERIOD_DAYS = 20
    bls = periodograms.run_bls(t, mag, err, 'magnitude', 200)
    assert bls is not None
    assert abs(bls['best_period'] / injected - 1) < .01
    report['bls_injected_days'] = injected
    report['bls_recovered_days'] = bls['best_period']

    if originals:
        cleaner = original(originals / 'ATLAS_batch_clean_with_plots(5).py', 'original_clean_audit')
        cleaner.RESCUE_ENABLE = False
        old, _ = cleaner.clean_atlas_df(input_frame)
        pd.testing.assert_frame_equal(cleaned, old)
        cleaner.REQUIRE_FLAGS_ZERO = False
        raw_files = list((demo / 'raw').glob('*.csv'))
        for rescue in (False, True):
            cleaner.RESCUE_ENABLE = clean_settings.RESCUE_ENABLE = rescue
            for file in raw_files:
                raw = pd.read_csv(file, dtype=str)
                new_frame, new_summary = cuts.clean_atlas_df(raw)
                old_frame, old_summary = cleaner.clean_atlas_df(raw)
                pd.testing.assert_frame_equal(new_frame, old_frame)
                assert json.dumps(new_summary, sort_keys=True) == json.dumps(old_summary, sort_keys=True)
        clean_settings.RESCUE_ENABLE = False
        report['original_cleaner'] = '26 defect/boundary cases and 12 sources at rescue off/on matched'
        search = original(originals / 'ATLAS_period_search_pipeline_final.py', 'original_period_audit')
        signal = .25 * np.sin(2 * np.pi * t / injected) + rng.normal(0, .02, len(t))
        old_ls = search.run_lomb_scargle(t, signal, err, .5, 20)
        new_ls = periodograms.run_lomb_scargle(t, signal, err, .5, 20)
        for key in ('frequency', 'period', 'power', 'raw_best_period', 'raw_best_power', 'raw_best_fap'):
            np.testing.assert_array_equal(old_ls[key], new_ls[key])
        search.BLS_MAX_PERIOD_DAYS = 20
        old_bls = search.run_bls(t, mag, err, 'magnitude', 200)
        for key in ('period_grid', 'power', 'best_period', 'best_duration', 'best_t0', 'best_depth', 'best_power', 'sde'):
            np.testing.assert_array_equal(old_bls[key], bls[key])
        report['original_periodograms'] = 'LS and BLS arrays/results exactly matched'
        morph = original(originals / 'umap_morphology_pipeline(4).py', 'original_morph_audit')
        cfg = dict(morph_settings.DEFAULTS)
        cfg['thresholds'] = dict(morph_settings.DEFAULTS['thresholds'])
        count = 0
        from groove.morphology import smoke, classify
        for index, kind in enumerate(('smooth_sine', 'clean_eclipse', 'unusual_double_dip',
                                      'grouped_raw_time_flares', 'nonvar', 'incoherent_noisy')):
            frame = smoke.synthetic_lightcurve(kind, 5.3, seed=index)
            source = dict(source_key=kind, source_id=kind, dataset='audit',
                          data=frame, input_filename=kind, file_fingerprint='0')
            period = {'recommended_period_days': 5.3}
            new = features.extract_source_features(source, period, cfg)
            old = morph.extract_source_features(source, period, cfg)
            pd.testing.assert_series_equal(pd.Series(new['summary']), pd.Series(old['summary']))
            row = dict(new['summary'], out_of_distribution_score=0.)
            pd.testing.assert_series_equal(
                pd.Series(classify.suggest_morphology(row, {'evolution_threshold': 1.5}, cfg)),
                pd.Series(morph.suggest_morphology(row, {'evolution_threshold': 1.5}, cfg)))
            count += 1
        report['original_morphology_cases_matched'] = count
    output = demo.parent / 'output_audit.json'
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('demo', type=Path)
    parser.add_argument('--originals', type=Path)
    args = parser.parse_args()
    audit(args.demo.resolve(), args.originals.resolve() if args.originals else None)
