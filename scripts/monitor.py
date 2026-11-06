"""Scheduled metadata-only monitoring of Roboflow and Kaggle notebooks."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

import requests

STATE_PATH = Path('state/monitor.json')
TIMEOUT = 25


def env(name, default=''):
    return os.getenv(name, default).strip()


def send_slack(message):
    url = env('SLACK_WEBHOOK_URL')
    if not url:
        raise RuntimeError('SLACK_WEBHOOK_URL is missing')
    r = requests.post(url, json={'text': message}, timeout=TIMEOUT)
    r.raise_for_status()
    if r.text.strip() != 'ok':
        raise RuntimeError(f'Slack rejected message: {r.status_code}')


def get_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding='utf-8'))
    return {}


def get_roboflow():
    key, workspace, project = (env(k) for k in ['ROBOFLOW_API_KEY', 'ROBOFLOW_WORKSPACE', 'ROBOFLOW_PROJECT'])
    if not all((key, workspace, project)):
        print('Roboflow: missing configuration; skipped')
        return None
    url = f'https://api.roboflow.com/{workspace}/{project}'
    resp = requests.get(url, params={'api_key': key}, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if 'error' in data:
        raise RuntimeError(f'Roboflow API error: {str(data["error"])[:160]}')
    p = data.get('project', data)
    # Keep only stable, documented project metadata; do not retain secrets or large payloads.
    versions = p.get('versions', data.get('versions', []))
    version_ids = []
    for v in versions if isinstance(versions, list) else []:
        if isinstance(v, dict):
            val = v.get('version', v.get('id'))
        else:
            val = v
        if val is not None:
            version_ids.append(str(val))
    version_ids = sorted(set(version_ids))
    fields = ['images', 'unannotated']
    stats = {name: p[name] for name in fields if isinstance(p.get(name), (int, float))}
    return {'versions': version_ids, 'counts': stats, 'url': f'https://app.roboflow.com/{workspace}/{project}'}


def kaggle_status(notebook):
    # CLI returns human-readable status in the currently documented interface.
    proc = subprocess.run(['kaggle', 'kernels', 'status', notebook], capture_output=True, text=True, timeout=45)
    if proc.returncode:
        raise RuntimeError('Kaggle status failed for ' + notebook + ': ' + (proc.stderr or proc.stdout)[-400:])
    output = (proc.stdout + '\n' + proc.stderr).strip()
    # Normalize only known state words, avoid changing state from varying timestamps.
    match = re.search(r'\b(complete|completed|error|failed|failure|running|queued|pending|cancelled|canceled)\b', output, re.I)
    normalized = match.group(1).lower() if match else output[:180]
    if normalized == 'completed':
        normalized = 'complete'
    if normalized in ('failed', 'failure'):
        normalized = 'error'
    return normalized


def get_kaggle():
    refs = [s.strip() for s in env('KAGGLE_NOTEBOOKS').split(',') if s.strip()]
    if not refs:
        print('Kaggle: no notebooks configured; skipped')
        return None
    result = {}
    for ref in refs:
        if not re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_-]+', ref):
            raise ValueError('Invalid KAGGLE_NOTEBOOKS entry: ' + ref)
        result[ref] = kaggle_status(ref)
    return result


def compare(old, new):
    messages = []
    if 'roboflow' in old and 'roboflow' in new:
        a, b = old['roboflow'], new['roboflow']
        added = sorted(set(b['versions']) - set(a.get('versions', [])))
        for v in added:
            messages.append(f'*Roboflow | Version mới*\nProject: <{b["url"]}|Mở Roboflow>\nVersion: `{v}`\nNgười thực hiện: Không có trong dữ liệu API được kiểm tra')
        for key, new_count in b.get('counts', {}).items():
            previous = a.get('counts', {}).get(key)
            if previous is not None and new_count != previous:
                messages.append(f'*Roboflow | Số lượng thay đổi*\nTrường: `{key}`\nTrước: {previous} → Sau: {new_count}\nProject: <{b["url"]}|Mở Roboflow>\nNgười thực hiện: Không xác định')
    if 'kaggle' in old and 'kaggle' in new:
        for ref, status in new['kaggle'].items():
            before = old['kaggle'].get(ref)
            if before is not None and before != status:
                owner = ref.split('/')[0]
                messages.append(f'*Kaggle | Trạng thái notebook thay đổi*\nNotebook: <https://www.kaggle.com/code/{ref}|{ref}>\nTrạng thái: `{before}` → `{status}`\nTài khoản sở hữu: `{owner}` (không đồng nghĩa người nhấn Run)')
    return messages


def main():
    old = get_state()
    new = dict(old)
    errors = []
    for name, fn in [('roboflow', get_roboflow), ('kaggle', get_kaggle)]:
        try:
            result = fn()
            if result is not None:
                new[name] = result
        except Exception as exc:
            errors.append(f'{name}: {exc}')
    if not any(x in new for x in ('roboflow', 'kaggle')):
        raise RuntimeError('Neither data source is configured')
    messages = compare(old, new)
    if not STATE_PATH.exists():
        messages.insert(0, '*AI Monitor đã khởi tạo*\nĐã lưu trạng thái đầu tiên. Những thay đổi tiếp theo sẽ tạo thông báo.')
    for msg in messages:
        send_slack(msg)
    # Never mark undelivered notifications as processed.
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(new, indent=2, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')
    print(f'Notified: {len(messages)}; errors: {len(errors)}')
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
