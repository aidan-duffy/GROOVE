"""Content-checked stage receipts and atomic per-source/product checkpoints."""
from __future__ import annotations
from contextlib import contextmanager
from functools import wraps
import inspect
import hashlib
import json
from pathlib import Path
import os
import tempfile


def digest(path):
    path = Path(path)
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def hash_value(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, default=str, allow_nan=True), encoding='utf8')
    tmp.replace(path)


def read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}


def snapshot(paths):
    result = {}
    for root in paths:
        root = Path(root)
        files = root.rglob('*') if root.is_dir() else [root]
        for path in files:
            if not path.is_file() or path.name.endswith(('.tmp', '.log')):
                continue
            if any(p in {'__pycache__', '.groove_state'} for p in path.parts):
                continue
            result[str(path.resolve())] = digest(path)
    return result


def settings_dict(module):
    return {key: value for key, value in vars(module).items() if key.isupper()}


def code_hash(stage):
    package = Path(__file__).parent
    files = [*package.glob('*.py'), *(package / stage).glob('*.py')]
    return hash_value({str(p.relative_to(package)): digest(p) for p in sorted(files)})


def locations(cfg, stage):
    values = {k.lower(): v for k, v in getattr(cfg, stage).items()}
    def loc(key, default):
        return Path(values.get(key) or default)
    if stage == 'download':
        return [cfg.targets] if cfg.targets else [], [cfg.raw_root]
    if stage == 'clean':
        return [loc('input_dir', cfg.raw_lightcurves)], [loc('cleaned_dir', cfg.clean_dir), loc('plot_dir', cfg.clean_plots)]
    if stage == 'select':
        return [loc('cleaned_dir', cfg.clean_dir)], [loc('selected_dir', cfg.selected_dir), cfg.clean_dir / 'source_selection.csv', cfg.clean_dir / 'source_selection_reason_counts.csv']
    if stage == 'periods':
        inputs = [loc('input_dir', cfg.selected_dir)]
        inputs += [Path(p) for p in values.get('reference_summary_csvs', [])]
        if values.get('catalog_csv'):
            inputs.append(Path(values['catalog_csv']))
        # The explicit memory is an input. Default memory is this run's output.
        if values.get('alias_memory_csv'):
            inputs.append(Path(values['alias_memory_csv']))
        return inputs, [loc('output_dir', cfg.periods_dir), loc('plot_dir', cfg.period_plots)]
    root = loc('output_root', cfg.morphology_dir)
    inputs = [cfg.selected_dir, cfg.periods_dir / 'tables']
    manual = loc('manual_labels_file', root / 'manual_labels.csv')
    inputs.append(manual)
    return inputs, [root, cfg.plots_root / 'ML', root.parent / 'plots/ML']


@contextmanager
def products(folder, signature, force=False):
    """Reuse compatible figure/HTML bytes and publish new products atomically.

    Rendering may repeat; already completed products keep their timestamps.
    Existing products without a receipt are regenerated once, never trusted.
    """
    from matplotlib.figure import Figure
    from plotly.basedatatypes import BaseFigure
    store = ProductStore(folder, signature, force)
    old_save = Figure.savefig
    old_html = BaseFigure.write_html
    def save(fig, target, *args, **kwargs):
        if not isinstance(target, (str, Path)) or str(target).endswith('.tmp'):
            return old_save(fig, target, *args, **kwargs)
        path = Path(target)
        if store.current(path):
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + '.tmp')
        options = dict(kwargs)
        options.setdefault('format', path.suffix.lstrip('.'))
        try:
            result = old_save(fig, temporary, *args, **options)
            temporary.replace(path)
            store.record(path)
            return result
        finally:
            temporary.unlink(missing_ok=True)
    def html(fig, target, *args, **kwargs):
        if not isinstance(target, (str, Path)) or str(target).endswith('.tmp'):
            return old_html(fig, target, *args, **kwargs)
        path = Path(target)
        if store.current(path):
            return
        temporary = path.with_name(path.name + '.tmp')
        try:
            result = old_html(fig, str(temporary), *args, **kwargs)
            temporary.replace(path)
            store.record(path)
            return result
        finally:
            temporary.unlink(missing_ok=True)
    Figure.savefig, BaseFigure.write_html = save, html
    global ACTIVE_PRODUCTS
    previous = ACTIVE_PRODUCTS
    ACTIVE_PRODUCTS = store
    try:
        yield store
    finally:
        Figure.savefig, BaseFigure.write_html = old_save, old_html
        ACTIVE_PRODUCTS = previous


class ProductStore:
    def __init__(self, folder, signature, force=False):
        self.folder = Path(folder)
        self.signature = signature
        self.force = force
    def receipt(self, path):
        return self.folder / (hash_value(str(Path(path).resolve())) + '.json')
    def current(self, path):
        if self.force:
            return False
        state = read_json(self.receipt(path))
        return state.get('signature') == self.signature and state.get('sha256') is not None and state['sha256'] == digest(path)
    def record(self, path):
        atomic_json(self.receipt(path), {'signature': self.signature, 'sha256': digest(path)})


ACTIVE_PRODUCTS = None


def resumable(stage):
    def decorate(function):
        @wraps(function)
        def run(cfg, *args, **kwargs):
            force = bool(kwargs.get('rerun', False))
            if kwargs.get('dry_run', False):
                return function(cfg, *args, **kwargs)
            inputs, outputs = locations(cfg, stage)
            bound = inspect.signature(function).bind(cfg, *args, **kwargs)
            bound.apply_defaults()
            options = {k: v for k, v in bound.arguments.items() if k not in {'cfg', 'rerun'}}
            if 'extra_args' in options:
                options['extra_args'] = [a for a in options['extra_args'] or [] if a != '--']
            fingerprint = hash_value({'code': code_hash(stage), 'name': cfg.name,
                'settings': getattr(cfg, stage), 'options': options,
                'top': {k: getattr(cfg, k) for k in ('years', 'photometry', 'group', 'group_column', 'filters', 'gaia_id')} if stage == 'download' else {},
                'inputs': snapshot(inputs), 'output_locations': [str(p.resolve()) for p in outputs]})
            marker = cfg.output_folder / '.groove_state' / (stage + '.json')
            saved = read_json(marker)
            if not force and saved.get('signature') == fingerprint and saved.get('status') == 'complete':
                old = saved.get('outputs', {})
                if old and all(digest(p) == sha for p, sha in old.items()):
                    print(f'[resume] {stage}: complete; unchanged inputs/settings and checked outputs.')
                    return 0 if stage == 'download' else None
            atomic_json(marker, {'signature': fingerprint, 'status': 'running'})
            with products(marker.parent / (stage + '_products'), fingerprint, force):
                result = function(cfg, *args, **kwargs)
            if isinstance(result, int) and result != 0:
                return result
            # Selection writes its reports into the cleaning input directory.
            # Capture final input state so those writes do not invalidate itself.
            fingerprint_after = hash_value({'code': code_hash(stage), 'name': cfg.name,
                'settings': getattr(cfg, stage), 'options': options,
                'top': {k: getattr(cfg, k) for k in ('years', 'photometry', 'group', 'group_column', 'filters', 'gaia_id')} if stage == 'download' else {},
                'inputs': snapshot(inputs), 'output_locations': [str(p.resolve()) for p in outputs]})
            atomic_json(marker, {'signature': fingerprint_after, 'status': 'complete', 'outputs': snapshot(outputs)})
            return result
        return run
    return decorate
