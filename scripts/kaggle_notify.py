"""Copy this into a Kaggle notebook cell, or paste the relevant functions."""
import os
from datetime import datetime, timezone
import requests

from kaggle_secrets import UserSecretsClient

SLACK_URL = UserSecretsClient().get_secret('SLACK_WEBHOOK_URL')
# Always set this to the person actually running the notebook.
RUN_BY = 'THAY_BANG_TEN_THANH_VIEN'
MODEL_NAME = 'yolo11n.pt'

def notify(event, detail=''):
    payload = {
        'text': f'*Kaggle YOLO | {event}*\nNgười chạy (tự khai báo): {RUN_BY}\nModel: {MODEL_NAME}\nUTC: {datetime.now(timezone.utc).isoformat(timespec="seconds")}\n{detail}'
    }
    response = requests.post(SLACK_URL, json=payload, timeout=15)
    response.raise_for_status()
    if response.text.strip() != 'ok':
        raise RuntimeError('Slack rejected the message')

# Usage AFTER you configure the Ultralytics environment and data.yaml:
# from ultralytics import YOLO
# notify('BẮT ĐẦU TRAINING', 'Epochs: 100')
# try:
#     model = YOLO(MODEL_NAME)
#     model.train(data='/kaggle/working/data.yaml', epochs=100, imgsz=640, batch=16)
#     metrics = model.val(data='/kaggle/working/data.yaml')
#     notify('TRAINING HOÀN TẤT',
#            f'mAP50: {metrics.box.map50:.4f}; mAP50-95: {metrics.box.map:.4f}; '
#            f'Precision: {metrics.box.mp:.4f}; Recall: {metrics.box.mr:.4f}')
# except Exception as exc:
#     try:
#         notify('TRAINING THẤT BẠI', str(exc)[:500])
#     finally:
#         raise
