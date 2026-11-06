"""Paste into Kaggle notebook; save KAGGLE_SLACK_WEBHOOK_URL in Kaggle Secrets first."""
from datetime import datetime, timezone
import requests
from kaggle_secrets import UserSecretsClient

KAGGLE_SLACK_WEBHOOK_URL = UserSecretsClient().get_secret('KAGGLE_SLACK_WEBHOOK_URL')
RUN_BY = 'TEN_CUA_BAN'  # self-reported, not verified by Kaggle
MODEL_NAME = 'yolo11n.pt'


def notify(event, detail=''):
    message = (f'*Kaggle YOLO | {event}*\n'
               f'Người thực hiện (tự khai báo): {RUN_BY}\n'
               f'Model: {MODEL_NAME}\n'
               f'Thời gian (UTC): {datetime.now(timezone.utc).isoformat(timespec="seconds")}\n'
               f'{detail}')
    response = requests.post(KAGGLE_SLACK_WEBHOOK_URL, json={'text': message}, timeout=15)
    response.raise_for_status()
    if response.text.strip() != 'ok':
        raise RuntimeError('Kaggle Slack webhook returned unexpected response')


# Sau khi chuẩn bị YOLO và data.yaml:
# from ultralytics import YOLO
# notify('BẮT ĐẦU TRAINING', 'Epochs: 100')
# try:
#     model = YOLO(MODEL_NAME)
#     model.train(data='/kaggle/working/data.yaml', epochs=100, imgsz=640, batch=16)
#     metrics = model.val(data='/kaggle/working/data.yaml')
#     notify('HOÀN TẤT TRAINING',
#            f'mAP50: {metrics.box.map50:.4f}\n'
#            f'mAP50-95: {metrics.box.map:.4f}\n'
#            f'Precision: {metrics.box.mp:.4f}\n'
#            f'Recall: {metrics.box.mr:.4f}')
# except Exception as error:
#     try:
#         notify('TRAINING THẤT BẠI', str(error)[:500])
#     finally:
#         raise
