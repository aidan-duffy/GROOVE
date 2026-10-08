"""Exercise download state transitions without contacting ATLAS."""
from argparse import Namespace
from pathlib import Path
import json
from unittest.mock import Mock
import pandas as pd
import pytest
from groove import config, pipeline
from groove.download import client, run, settings


@pytest.fixture
def download_config(tmp_path, monkeypatch):
    targets = tmp_path / 'targets.csv'
    pd.DataFrame({'GaiaDR3': ['3216489845356186496', '3216489845356186497'],
                  'RAdeg': [84., 85.], 'DEdeg': [-2.5, -2.6],
                  'group': ['A', 'B'], 'Quality': ['good', 'good']}).to_csv(targets, index=False)
    path = tmp_path / 'run.yaml'
    path.write_text('name: test\noutput_folder: out\ntargets: targets.csv\nyears: full\n')
    monkeypatch.setenv('ATLAS_TOKEN', 'fake-test-token')
    return config.load(path)


def fake_client(monkeypatch):
    obj = Mock()
    obj.submit_job.return_value = ('https://fallingstar-data.com/forcedphot/queue/123/', '123')
    obj.poll_job.return_value = {'status': 'done', 'result_url': '/result/123.txt'}
    obj.download_result.return_value = pd.DataFrame({'MJD': [58000., 58001.], 'm': [14., 14.], 'dm': [.02,.02], 'F': ['o','c']})
    monkeypatch.setattr(client, 'AtlasClient', lambda token, args: obj)
    return obj


def test_download_resume_completed_and_metadata(download_config, monkeypatch):
    obj = fake_client(monkeypatch)
    assert pipeline.run_download(download_config) == 0
    assert obj.submit_job.call_count == 2
    files = sorted(download_config.raw_lightcurves.glob('*.csv'))
    assert len(files) == 2
    assert pd.read_csv(files[0], dtype=str)['target_GaiaDR3'][0] == '3216489845356186496'
    obj.reset_mock()
    assert pipeline.run_download(download_config) == 0
    obj.submit_job.assert_not_called()
    progress = pd.read_csv(download_config.raw_lightcurves.parent/'download_progress.csv')
    assert set(progress.status) == {'completed'}
    assert 'fake-test-token' not in (download_config.raw_lightcurves.parent/'run_config.json').read_text()


def test_download_dry_run_needs_no_token_and_writes_nothing(download_config, monkeypatch):
    monkeypatch.delenv('ATLAS_TOKEN')
    assert pipeline.run_download(download_config, dry_run=True) == 0
    assert not download_config.raw_lightcurves.parent.exists()


def test_active_job_stops_next_submission_and_resumes(download_config, monkeypatch):
    obj = fake_client(monkeypatch)
    obj.poll_job.side_effect = client.RetryableError('poll timed out')
    assert pipeline.run_download(download_config) == 1
    assert obj.submit_job.call_count == 1
    obj.reset_mock()
    obj.poll_job.side_effect = None
    assert pipeline.run_download(download_config) == 0
    # First target uses its saved task URL; only the second is newly submitted.
    assert obj.submit_job.call_count == 1
    assert obj.poll_job.call_count == 2


def test_result_download_resumes_without_resubmission(download_config, monkeypatch):
    obj = fake_client(monkeypatch)
    obj.download_result.side_effect = client.RetryableError('connection lost')
    assert pipeline.run_download(download_config, limit=1) == 1
    obj.reset_mock()
    obj.download_result.side_effect = None
    assert pipeline.run_download(download_config, limit=1) == 0
    obj.submit_job.assert_not_called()
    obj.poll_job.assert_not_called()


def test_ambiguous_post_does_not_resubmit(download_config, monkeypatch):
    obj = fake_client(monkeypatch)
    obj.submit_job.side_effect = client.RetryableError('unknown outcome')
    assert pipeline.run_download(download_config) == 1
    obj.reset_mock()
    with pytest.raises(RuntimeError, match='unknown outcome'):
        pipeline.run_download(download_config)
    obj.submit_job.assert_not_called()


def test_token_lock_rejects_second_process():
    with run.token_lock('fake-lock-token'):
        with pytest.raises(RuntimeError, match='already using'):
            with run.token_lock('fake-lock-token'):
                pass


def test_only_single_token_supported(download_config, monkeypatch):
    monkeypatch.delenv('ATLAS_TOKEN')
    monkeypatch.setenv('UNUSED_TOKEN', 'ignored')
    with pytest.raises(EnvironmentError, match='ATLAS_TOKEN'):
        client.load_token()
    path = download_config.source_path
    path.write_text(path.read_text() + 'tokens: 1\n')
    with pytest.raises(ValueError, match='unknown config'):
        config.load(path)


def test_gaia_and_arbitrary_filters_combine(download_config):
    download_config.gaia_id = '3216489845356186496'
    download_config.filters = {'Quality': 'good', 'group': 'A'}
    assert pipeline.run_download(download_config, dry_run=True) == 0


def test_client_full_history_payload_and_csv_parsing(monkeypatch):
    args = Namespace(max_retries=0, retry_delay=0)
    obj = client.AtlasClient('fake', args)
    response = Mock(status_code=201)
    response.json.return_value = {'url': '/forcedphot/queue/123/', 'id': 123}
    obj.session = Mock()
    obj.session.post.return_value = response
    settings.STOP_EVENT.clear()
    url, job = obj.submit_job(84, -2.5, None, None, 'reduced')
    payload = obj.session.post.call_args.kwargs['data']
    assert payload['mjd_min'] == payload['mjd_max'] == ''
    assert payload['use_reduced'] == 'true'
    response = Mock(status_code=200, text='MJD,m,dm,F\n58000,14,.02,o\n')
    obj.session.get.return_value = response
    assert len(obj.download_result('/result.txt')) == 1
    response.text = '###MJD m dm F\n58000 14 .02 o\n'
    assert len(obj.download_result('/result.txt')) == 1
    response.text = '<html>server error</html>'
    with pytest.raises(client.PermanentJobError, match='MJD'):
        obj.download_result('/result.txt')


def test_simulated_download_reaches_final_scientific_outputs(download_config, monkeypatch, tmp_path):
    from test_pipeline import synthetic_raw
    raw = tmp_path / 'api_fixture'
    raw.mkdir()
    synthetic_raw(raw, n=500)
    response = pd.read_csv(next(raw.glob('*.csv')), dtype=str)
    obj = fake_client(monkeypatch)
    obj.download_result.return_value = response
    download_config.clean = {'make_summary_plots': False, 'make_reason_plot': False,
                             'make_example_plots': False}
    download_config.periods = {'max_period_days': 30, 'run_bls': False,
                               'plot_mode': 'none', 'auto_plot_harmonic_suspects': False}
    download_config.morphology = {'mode': 'classify', 'n_jobs': 1}
    pipeline.run_all(download_config)
    periods = pd.read_csv(download_config.periods_dir / 'tables/source_period_recommendations.csv',
                          dtype={'source_id': str})
    morphology = pd.read_csv(download_config.morphology_dir / 'classification/tables/all_sources.csv',
                             dtype={'source_id': str})
    expected = {'3216489845356186496', '3216489845356186497'}
    assert set(periods.source_id) == set(morphology.source_id) == expected
    assert ((periods.recommended_period_days / 12.7 - 1).abs() < .01).all()
    assert morphology.final_primary_tag.eq('wavelike').all()
    assert obj.submit_job.call_count == 2


def test_download_receipt_skips_auth_when_complete_and_rerun_refetches(download_config, monkeypatch):
    obj = fake_client(monkeypatch)
    assert pipeline.run_download(download_config) == 0
    submitted = obj.submit_job.call_count
    obj.validate_authentication.reset_mock()
    assert pipeline.run_download(download_config) == 0
    obj.validate_authentication.assert_not_called()
    assert pipeline.run_download(download_config, rerun=True) == 0
    assert obj.submit_job.call_count > submitted
