"""Check saved download files; optionally compare with their ATLAS result tables.

python audit_downloads.py real_run.yaml
python audit_downloads.py real_run.yaml --compare-api
The optional comparison reads existing results; it never submits a new job.
"""
from pathlib import Path
from argparse import ArgumentParser, Namespace
import json
import numpy as np
import pandas as pd
from groove.config import load
from groove.download.client import AtlasClient, load_token


def audit(config_path, compare_api=False):
    cfg = load(config_path)
    directory = cfg.raw_root / cfg.download_run_name
    state = json.loads((directory / 'run_config.json').read_text())
    progress = pd.read_csv(directory / 'download_progress.csv', dtype=str, keep_default_na=False)
    unresolved = progress.loc[~progress.status.isin(['completed', 'no_data'])]
    if len(unresolved):
        raise ValueError('Unresolved downloads: ' + ', '.join(unresolved.status.unique()))
    finished = progress.loc[progress.status.eq('completed')]
    if finished.empty:
        raise ValueError('No completed photometry files to verify.')
    remote = AtlasClient(load_token(), Namespace(max_retries=2, retry_delay=1)) if compare_api else None
    rows = []
    try:
        for _, target in finished.iterrows():
            path = Path(target.all_lightcurves_path)
            saved = pd.read_csv(path, dtype=str)
            saved.columns = [str(c).strip().lstrip('#') for c in saved]
            assert len(saved) == int(float(target.number_of_points)), path.name
            if target.get('gaia_dr3_id'):
                assert saved.target_GaiaDR3.eq(target.gaia_dr3_id).all(), path.name
            time = pd.to_numeric(saved.MJD, errors='coerce')
            assert np.isfinite(time).all(), path.name
            if state.get('mjd_min') is not None:
                assert time.min() >= float(state['mjd_min']) - 1e-6
                assert time.max() <= float(state['mjd_max']) + 1e-6
            assert {'F'} <= set(saved) and ({'m', 'dm'} <= set(saved) or {'uJy', 'duJy'} <= set(saved))
            if remote:
                api = remote.download_result(target.result_url)
                api.columns = [str(c).strip().lstrip('#') for c in api]
                assert len(api) == len(saved), path.name
                assert set(api) <= set(saved), path.name
                for column in api:
                    a = pd.to_numeric(api[column], errors='coerce')
                    b = pd.to_numeric(saved[column], errors='coerce')
                    numeric = a.notna().any() and a.notna().sum() == api[column].notna().sum()
                    if numeric:
                        np.testing.assert_allclose(a, b, rtol=1e-10, atol=1e-10, equal_nan=True)
                    else:
                        pd.testing.assert_series_equal(api[column].fillna('').astype(str).reset_index(drop=True), saved[column].fillna('').astype(str).reset_index(drop=True), check_names=False)
            rows.append({'file': path.name, 'rows': len(saved), 'mjd_min': float(time.min()),
                         'mjd_max': float(time.max()), 'filters': sorted(saved.F.unique().tolist()),
                         'compared_with_api_result': compare_api})
    finally:
        if remote:
            remote.close()
    report = {'completed_sources': len(rows), 'no_data_sources': int(progress.status.eq('no_data').sum()), 'files': rows}
    output = cfg.output_folder / 'download_audit.json'
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('config', type=Path)
    parser.add_argument('--compare-api', action='store_true')
    args = parser.parse_args()
    audit(args.config, args.compare_api)
