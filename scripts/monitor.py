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
    var = {'roboflow': 'ROBOFLOW_SLACK_WEBHOOK_URL',
           'kaggle': 'KAGGLE_SLACK_WEBHOOK_URL'}[source]
    url = env(var)
    if not url:
        raise RuntimeError(f'{var} is missing')
    resp = requests.post(url, json={'text': message}, timeout=TIMEOUT)
    resp.raise_for_status()
    if resp.text.strip() != 'ok':
        raise RuntimeError(
            f'{source} Slack webhook rejected notification ({resp.status_code})')


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
    tmp.write_text(json.dumps(state, ensure_ascii=False,
                   indent=2, sort_keys=True) + '\n', encoding='utf-8')
    tmp.replace(STATE_PATH)


def get_roboflow():
    key, ws, project = (env(x) for x in (
        'ROBOFLOW_API_KEY', 'ROBOFLOW_WORKSPACE', 'ROBOFLOW_PROJECT'))
    if not any((key, ws, project)):
        return None
    if not all((key, ws, project)):
        raise RuntimeError(
            'Roboflow config incomplete: API_KEY, WORKSPACE, PROJECT required')
    resp = requests.get(
        f'https://api.roboflow.com/{quote(ws, safe="")}/{quote(project, safe="")}',
        params={'api_key': key}, timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict) or 'error' in data:
        raise RuntimeError(
            'Roboflow returned an API error or invalid JSON schema')
    metadata = data.get('project', data)
    versions = data.get('versions', metadata.get('versions', []))
    if not isinstance(metadata, dict) or not isinstance(versions, list):
        raise RuntimeError(
            'Roboflow project API response has unexpected structure')
    identifiers = []
    for item in versions:
        version = item.get('version', item.get(
            'id')) if isinstance(item, dict) else item
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
    proc = subprocess.run(
        ['kaggle', *args], capture_output=True, text=True, timeout=90)
    if proc.returncode:
        # Don't include raw CLI output, as providers may echo sensitive text.
        raise RuntimeError('Kaggle command failed: ' +
                           ' '.join(args[:2]) + f' (exit {proc.returncode})')
    return proc.stdout


def list_kaggle_notebooks(username):
    """Discover own notebooks and lastRunTime, without calling Kaggle session status API.

    Kaggle may return 404 for kernels status even when the notebook exists.
    lastRunTime indicates a saved-run timestamp, NOT a training completion result.
    """
    notebooks = {}
