#!/usr/bin/env bash
set -euo pipefail
zip_path=${1:?Usage: tests/release-audit.sh release.zip}; test -f "$zip_path"; unzip -t "$zip_path" >/dev/null
listing=$(unzip -Z1 "$zip_path")
if grep -E '(^|/)(data/|uploads?/|logs?/|node_modules/|\.git/|__pycache__/|\.pytest_cache/)|\.(db|sqlite|sqlite3|log|token|secret)$|(^|/)\.env$|(^|/)\.env\.(local|development|production|test)$' <<<"$listing"; then echo 'Forbidden release path found' >&2; exit 1; fi
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT; unzip -q "$zip_path" -d "$tmp"
if rg -i -l 'Server[P]C|ollama[-]edit\.fre[x]ite\.cc|(^|[^a-z])mat[t]([^a-z]|$)' "$tmp"; then echo 'Private deployment identifier found' >&2; exit 1; fi
python3 - "$tmp" <<'PY'
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
account = 'itz' + 'fre' + 'xite'
allowed = re.compile(
    rf'(?:github\.com/{account}/aperyn|ghcr\.io/{account}/aperyn|IMAGE_NAME:\s*{account}/aperyn|\b{account}\b)',
    re.I,
)
bad = []
for path in root.rglob('*'):
    if not path.is_file():
        continue
    try:
        text = path.read_text(encoding='utf-8')
    except (UnicodeDecodeError, OSError):
        continue
    if re.search('fre' + 'xite', allowed.sub('', text), re.I):
        bad.append(str(path.relative_to(root)))
if bad:
    print('Unapproved deployment identifier found:', *bad, sep='\n', file=sys.stderr)
    raise SystemExit(1)
PY
echo 'Release archive integrity and privacy path scan passed.'
