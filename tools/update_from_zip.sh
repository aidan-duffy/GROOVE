#!/usr/bin/env bash
# Run inside your existing GROOVE Git checkout using its active Python environment.
set -euo pipefail
if [ "$#" -ne 1 ]; then
    echo 'Usage: bash update_from_zip.sh /absolute/path/to/GROOVE_v1.0.6.zip' >&2
    exit 2
fi
groove_zip=$(realpath "$1")
groove_repo=$(git rev-parse --show-toplevel)
cd "$groove_repo"
groove_branch=$(git branch --show-current)
if [ -z "$groove_branch" ]; then
    echo 'Switch to your normal branch before updating; this checkout has a detached HEAD.' >&2
    exit 1
fi
groove_remote=$(git remote get-url origin)
case "$groove_remote" in
    git@github.com:aidan-duffy/GROOVE.git|https://github.com/aidan-duffy/GROOVE.git) ;;
    *) echo 'This updater expects origin to be aidan-duffy/GROOVE. Check git remote -v.' >&2; exit 1 ;;
esac
if ! git diff --cached --quiet; then
    echo 'There are already staged changes. Commit or unstage those before running this updater.' >&2
    exit 1
fi
# Check the identity before changing files; SSH authenticates the later push.
git var GIT_AUTHOR_IDENT >/dev/null
groove_backup=$(mktemp -d -t groove-source-backup-XXXXXX)
groove_paths=$(mktemp -t groove-release-paths-XXXXXX)
trap 'rm -f "$groove_paths"' EXIT
python - "$groove_zip" "$groove_repo" "$groove_backup" "$groove_paths" <<'PY'
from pathlib import Path, PurePosixPath
import shutil
import sys
import zipfile
archive, repo, backup, path_list = map(Path, sys.argv[1:])
written = []
with zipfile.ZipFile(archive) as source:
    members = []
    for entry in source.infolist():
        if entry.is_dir():
            continue
        parts = PurePosixPath(entry.filename).parts
        if not parts or parts[0] != 'GROOVE' or '..' in parts or '.git' in parts:
            raise SystemExit('Unexpected archive path; no update applied.')
        relative = Path(*parts[1:])
        if not relative.parts or relative.name == '.env':
            raise SystemExit('Unexpected archive file; no update applied.')
        destination = repo / relative
        if destination.is_symlink():
            raise SystemExit('A release destination is a symbolic link; review it before updating.')
        members.append((entry, relative, destination))
    if not any(relative.as_posix() == 'pyproject.toml' for _, relative, _ in members):
        raise SystemExit('The archive does not contain GROOVE source.')
    for entry, relative, destination in members:
        # Preserve existing user configuration/target lists and never stage them.
        if destination.exists() and (relative.parts[0] == 'configs'
                or relative.as_posix().startswith('data/targets/')):
            continue
        if destination.is_file():
            previous = backup / relative
            previous.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(destination, previous)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read(entry))
        written.append(relative.as_posix())
path_list.write_bytes(b''.join(item.encode('utf-8') + b'\0' for item in written))
print(f'Updated {len(written)} package files. Previous copies: {backup}')
PY
python -m pip install -e '.[dev]'
python -m pip check
groove_version=$(python -m groove --version)
echo "$groove_version"
if [ "$groove_version" != "groove 1.0.6" ]; then
    echo "Expected GROOVE 1.0.6; stopping before commit/push." >&2
    exit 1
fi
python -m pytest -ra
# Stage only delivered source files, not arbitrary data, credentials or results.
git add --pathspec-from-file="$groove_paths" --pathspec-file-nul
if ! git diff --cached --quiet; then
    git diff --cached --stat
    git commit -m 'Add dataset marker shapes, safe map redraws and user workflow documentation'
fi
git push origin "$groove_branch"
echo 'GROOVE source updated, tested, committed and pushed.'
echo 'Run a fresh demo/output folder to use O/C-only defaults. Existing YAML series overrides are preserved.'
