"""Monitor Roboflow project + one Kaggle account, route events to separate Slack channels."""
import csv
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

import requests

STATE_PATH = Path('state/monitor.json')
TIMEOUT = 30
REF_PATTERN = re.compile(r'^[A-Za-z0-9_-]+/[A-Za-z0-9_-]+$')


def env(name):
    return os.environ.get(name, '').strip()


def send_slack(source, message):
    var = {'roboflow': 'ROBOFLOW_SLACK_WEBHOOK_URL', 'kaggle': 'KAGGLE_SLACK_WEBHOOK_URL'}[source]
    url = env(var)
    if not url:
        raise RuntimeError(f'{var} is missing')
    resp = requests.post(url, json={'text': message}, timeout=TIMEOUT)
    resp.raise_for_status()
    if resp.text.strip() != 'ok':
        raise RuntimeError(f'{source} Slack webhook rejected notification ({resp.status_code})')


def load_state():
    if not STATE_PATH.exists():
        return {}
    data = json.loads(STATE_PATH.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('state/monitor.json must be a JSON object')
    return data


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix('.tmp')
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    tmp.replace(STATE_PATH)


def get_roboflow():
    key, ws, project = (env(x) for x in ('ROBOFLOW_API_KEY', 'ROBOFLOW_WORKSPACE', 'ROBOFLOW_PROJECT'))
    if not any((key, ws, project)):
        return None
    if not all((key, ws, project)):
        raise RuntimeError('Roboflow config incomplete: API_KEY, WORKSPACE, PROJECT required')
    resp = requests.get(
        f'https://api.roboflow.com/{quote(ws, safe="")}/{quote(project, safe="")}',
        params={'api_key': key}, timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict) or 'error' in data:
        raise RuntimeError('Roboflow returned an API error or invalid JSON schema')
    metadata = data.get('project', data)
    versions = data.get('versions', metadata.get('versions', []))
    if not isinstance(metadata, dict) or not isinstance(versions, list):
        raise RuntimeError('Roboflow project API response has unexpected structure')
    identifiers = []
    for item in versions:
        version = item.get('version', item.get('id')) if isinstance(item, dict) else item
        if version is not None:
            identifiers.append(str(version))
    counts = {name: metadata.get(name) for name in ('images', 'unannotated')
              if isinstance(metadata.get(name), (int, float)) and not isinstance(metadata.get(name), bool)}
    return {
        'versions': sorted(set(identifiers)),
        'counts': counts,
        'url': f'https://app.roboflow.com/{quote(ws, safe="")}/{quote(project, safe="")}',
    }


def cli(args):
    proc = subprocess.run(['kaggle', *args], capture_output=True, text=True, timeout=90)
    if proc.returncode:
        # Don't include raw CLI output, as providers may echo sensitive text.
        raise RuntimeError('Kaggle command failed: ' + ' '.join(args[:2]) + f' (exit {proc.returncode})')
    return proc.stdout


def list_kaggle_notebooks(username):
    """Discover own notebooks in Kaggle; CSV provides a parseable 'ref' column."""
    refs = set()
    for page in range(1, 11):  # up to 1000 notebooks
        output = cli(['kernels', 'list', '--user', username, '--sort-by', 'dateRun',
                      '--page-size', '100', '--page', str(page), '--csv'])
        rows = list(csv.DictReader(io.StringIO(output)))
        if rows and not any(k and k.strip().lower() in ('ref', 'id') for k in rows[0]):
            raise RuntimeError('Kaggle CLI CSV response lacks a ref/id column')
        for row in rows:
            ref = next((v for k, v in row.items() if k and k.strip().lower() in ('ref', 'id')), '')
            if ref and REF_PATTERN.fullmatch(ref.strip()) and ref.split('/')[0].lower() == username.lower():
                refs.add(ref.strip())
        if len(rows) < 100:
            break
    else:
        print('Warning: Kaggle notebook list capped at 1000; consider a notebook allowlist', file=sys.stderr)
    return sorted(refs)


def kaggle_status(ref):
    output = cli(['kernels', 'status', ref])
    # The CLI prints the status of the latest saved/versioned run (not an interactive session).
    match = re.search(r'\b(complete|completed|error|failed|failure|running|queued|pending|cancelled|canceled)\b', output, re.I)
    if not match:
        raise RuntimeError(f'Unable to parse Kaggle notebook status for {ref}')
    result = match.group(1).lower()
    return {'completed': 'complete', 'failed': 'error', 'failure': 'error',
            'canceled': 'cancelled'}.get(result, result)


def get_kaggle():
    username = env('KAGGLE_ACCOUNT_USERNAME')
    explicit = [x.strip() for x in env('KAGGLE_NOTEBOOKS').split(',') if x.strip()]
    if not username and not explicit:
        return None
    if username and not re.fullmatch(r'[A-Za-z0-9_-]+', username):
        raise ValueError('Invalid KAGGLE_ACCOUNT_USERNAME')
    if username:
        discovered = list_kaggle_notebooks(username)
        refs = sorted(set(discovered + explicit))
    else:
        refs = sorted(set(explicit))
    if any(not REF_PATTERN.fullmatch(r) for r in refs):
        raise ValueError('Invalid notebook ref (expected username/notebook-slug)')
    return {ref: kaggle_status(ref) for ref in refs}


def changes_roboflow(previous, current):
    msgs = []
    old_versions = set(previous.get('versions', []))
    for version in sorted(set(current['versions']) - old_versions):
        msgs.append(f'*Roboflow | Dataset version mới*\nVersion: `{version}`\n'
                    f'Project: <{current["url"]}|Xem project>\nNgười thực hiện: Không xác định qua metadata')
    for field, new_value in current['counts'].items():
        old_value = previous.get('counts', {}).get(field)
        if old_value is not None and old_value != new_value:
            label = {'images': 'Số ảnh', 'unannotated': 'Ảnh chưa gán nhãn'}.get(field, field)
            msgs.append(f'*Roboflow | {label} thay đổi*\n{old_value} → {new_value}\n'
                        f'Project: <{current["url"]}|Xem project>\nNgười thực hiện: Không xác định')
    return msgs


def changes_kaggle(previous, current):
    msgs = []
    for ref, status in current.items():
        old_status = previous.get(ref)
        if old_status is None:
            msgs.append(f'*Kaggle | Phát hiện notebook mới*\nNotebook: '
                        f'<https://www.kaggle.com/code/{ref}|{ref}>\n'
                        f'Trạng thái hiện tại: `{status}`\nTài khoản sở hữu: `{ref.split("/")[0]}`')
        elif old_status != status:
            msgs.append(f'*Kaggle | Trạng thái notebook thay đổi*\nNotebook: '
                        f'<https://www.kaggle.com/code/{ref}|{ref}>\n'
                        f'Trạng thái: `{old_status}` → `{status}`\n'
                        f'Tài khoản sở hữu: `{ref.split("/")[0]}` (không chắc là người nhấn Run)')
    return msgs


def main():
    state = load_state()
    errors = []
    processed = 0
    source_configs = [('roboflow', get_roboflow, changes_roboflow),
                      ('kaggle', get_kaggle, changes_kaggle)]
    enabled = 0
    for source, fetch, diff in source_configs:
        try:
            new_value = fetch()
            if new_value is None:
                print(f'{source}: not configured; skipped')
                continue
            enabled += 1
            prior = state.get(source)
            # Each source has its own first-run baseline and own channel.
            if prior is None:
                send_slack(source, f'*{source.capitalize()} Monitor đã khởi tạo*\n'
                            'Đã lưu trạng thái ban đầu; lần kiểm tra tiếp theo sẽ báo thay đổi.')
                events = []
            else:
                events = diff(prior, new_value)
            # Save state after each delivered event, then continue to the next event.
            # If delivery fails, leave baseline unchanged, so the next run retries.
            for msg in events:
                send_slack(source, msg)
                processed += 1
            state[source] = new_value
            save_state(state)
            print(f'{source}: {len(events)} change notification(s)')
        except Exception as exc:
            errors.append(f'{source}: {type(exc).__name__}: {str(exc)[:250]}')
    if not enabled and not errors:
        errors.append('No source configured. Provide Roboflow config or Kaggle account username.')
    print(f'Notifications sent: {processed}; errors: {len(errors)}')
    for err in errors:
        print(err, file=sys.stderr)
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
