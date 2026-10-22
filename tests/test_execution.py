"""Parallel, strict-error, logging and random-state integration contracts."""
import importlib
import logging
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
import yaml
from test_pipeline import synthetic_raw

from groove import config, execution, pipeline
from groove.cli import build_parser
from groove.morphology import run as morphology
from groove.periods import loading, run, settings


def sample(tmp_path: Path, *, jobs: int = 1, cap: int | None = None) -> config.Config:
    root = tmp_path / 'raw'
    root.mkdir(exist_ok=True)
    for index in range(8):
        synthetic_raw(root, gid=str(9900000000000000001 + index), n=240, seed=index)
    path = tmp_path / f'run{jobs}.yaml'
    path.write_text(yaml.safe_dump({'name': 'test', 'input_folder': str(root),
        'output_folder': str(tmp_path / f'out{jobs}'),
        'periods': {'input_dir': str(root), 'file_glob': '*.csv', 'period_n_jobs': jobs, 'max_sources': cap,
                    'run_bls': False, 'plot_mode': 'none',
                    'auto_plot_harmonic_suspects': False, 'auto_plot_alias_suspects': False}}))
    return config.load(path)


def test_parallel_matches_serial_and_repairs_resume(tmp_path, monkeypatch):
    serial = sample(tmp_path)
    parallel = sample(tmp_path, jobs=2)
    pipeline.run_periods(serial)
    pipeline.run_periods(parallel)
    for filename in ['ls_period_search_summary.csv', 'ls_period_search_peaks.csv']:
        assert (serial.periods_dir / 'tables' / filename).read_bytes() == (
            parallel.periods_dir / 'tables' / filename).read_bytes()
    tables = parallel.periods_dir / 'tables'
    expected = (tables / 'ls_period_search_summary.csv').read_bytes()
    (tables / 'run_complete.json').unlink(missing_ok=True)
    for aggregate in ['ls_period_search_summary.csv', 'ls_period_search_peaks.csv']:
        (tables / aggregate).unlink()
    # Eight completed journals must be sufficient: never call the workers again.
    monkeypatch.setattr(run, '_analyse_file', lambda *args: pytest.fail('completed worker repeated'))
    pipeline.run_periods(parallel)
    assert (tables / 'ls_period_search_summary.csv').read_bytes() == expected


def test_parallel_source_cap_is_parent_owned(tmp_path):
    cfg = sample(tmp_path, jobs=2, cap=3)
    pipeline.run_periods(cfg)
    table = pd.read_csv(cfg.periods_dir / 'tables/ls_period_search_summary.csv', dtype=str)
    assert table.source_id.nunique() == 3
    assert len(list((cfg.periods_dir / 'tables/source_checkpoints').glob('*.json'))) == 3


def test_worker_settings_do_not_leak_and_strict_propagates(tmp_path):
    importlib.reload(settings)
    snapshot = {**vars(settings)}
    snapshot = {key: value for key, value in snapshot.items() if key.isupper()}
    snapshot.update(STRICT_ERRORS=True, MAX_PERIOD_DAYS=37.)
    original = settings.MAX_PERIOD_DAYS
    with patch.object(loading, 'normalise_columns', side_effect=ValueError('injected defect')):
        path = tmp_path / 'bad.csv'
        path.write_text('m,F\n14,o\n')
        with pytest.raises(ValueError, match='injected defect'):
            run._analyse_file(path, {}, snapshot)
    assert original == settings.MAX_PERIOD_DAYS
    assert not execution.is_strict()


def test_strict_policy_logs_and_can_be_reset(caplog):
    with (caplog.at_level(logging.WARNING), execution.error_policy(True),
          pytest.raises(ValueError, match='injected defect')):
        execution.report_exception(ValueError('injected defect'), 'groove.test')
    assert 'ValueError: injected defect' in caplog.text
    execution.report_exception(ValueError('normal fallback'), 'groove.test')
    assert not execution.is_strict()


def test_morphology_does_not_reseed_numpy(monkeypatch):
    args = morphology.build_parser().parse_args(['--config', 'unused.yaml'])
    monkeypatch.setattr(morphology, 'load_configuration', lambda _: {'mode': 'classify', 'random_seed': 42})
    monkeypatch.setattr(morphology, 'apply_cli', lambda cfg, _: cfg)
    monkeypatch.setattr(morphology._modes, 'classify_only', lambda *args: {})
    np.random.seed(123)
    before = np.random.get_state()
    morphology.execute(args)
    after = np.random.get_state()
    assert before[0] == after[0] and np.array_equal(before[1], after[1])
    assert before[2:] == after[2:]


def test_parallel_and_strict_flags():
    args = build_parser().parse_args(['run', '-c', 'test.yaml', '--n-jobs', '2', '--strict'])
    assert args.n_jobs == 2 and args.strict


def test_parallel_transient_failure_retries_only_failed_file(tmp_path, monkeypatch):
    cfg = sample(tmp_path, jobs=2)
    target = sorted((tmp_path / 'raw').glob('*.csv'))[3]
    original = run._analyse_file

    def fail_one(path, catalogue, snapshot):
        if path == target:
            return ([{'file': path.name, 'source_id': path.stem, 'object_name': path.stem,
                      'series': '', 'status': 'failed', 'error': 'transient injected failure'}], [], [])
        return original(path, catalogue, snapshot)

    monkeypatch.setattr(run, '_analyse_file', fail_one)
    with pytest.raises(RuntimeError, match='sources failed'):
        pipeline.run_periods(cfg)
    called = []

    def record(path, catalogue, snapshot):
        called.append(path)
        return original(path, catalogue, snapshot)

    monkeypatch.setattr(run, '_analyse_file', record)
    pipeline.run_periods(cfg)
    assert called == [target]
    table = pd.read_csv(cfg.periods_dir / 'tables/ls_period_search_summary.csv')
    assert len(table) == 16 and set(table.status) == {'ok'}


def test_library_logging_does_not_install_console_handler(tmp_path, capsys, caplog):
    from groove.morphology import utils
    with caplog.at_level(logging.INFO):
        logger = utils.setup_logging(tmp_path)
        logger.info('capturable stage progress')
    assert not capsys.readouterr().out
    assert 'capturable stage progress' in caplog.text
    assert 'capturable stage progress' in next(tmp_path.glob('*.log')).read_text()
    for handler in list(logger.handlers):
        if getattr(handler, '_groove_file', False):
            logger.removeHandler(handler)
            handler.close()
