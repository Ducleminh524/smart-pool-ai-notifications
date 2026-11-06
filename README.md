# Roboflow + Kaggle → Slack notifications

## What is monitored
- Roboflow project version identifiers, image count and unannotated count when exposed by project metadata.
- Kaggle last-run status for explicitly configured notebook references.
- Optional direct YOLO training messages from Kaggle notebook.

The actor cannot reliably be inferred from metadata. Kaggle notebook owner is not the person who last pressed Run. Roboflow individual bounding-box edits are not tracked. First scheduled run establishes a baseline. Polling may miss intermediate Kaggle runs between checks.

## Setup
1. Create a Slack app at https://api.slack.com/apps, enable Incoming Webhooks, and select your channel.
2. Create a **private** GitHub repository and upload these files (including hidden `.github/workflows/monitor.yml`). GitHub Actions must be enabled.
3. In GitHub repo **Settings → Secrets and variables → Actions → Secrets** create:
   - `SLACK_WEBHOOK_URL`: incoming webhook URL
   - `ROBOFLOW_API_KEY`: Roboflow private API key
   - `KAGGLE_API_TOKEN`: recommended Kaggle API token from https://www.kaggle.com/settings/api
   - **OR** `KAGGLE_USERNAME` and `KAGGLE_KEY`: classic Kaggle API credentials (legacy), if supported by your account
4. In **Variables** create:
   - `ROBOFLOW_WORKSPACE`: workspace slug from URL
   - `ROBOFLOW_PROJECT`: project slug from URL
   - `KAGGLE_NOTEBOOKS`: comma-separated `owner/notebook-slug` values (e.g. `user/model-training,user2/experiment`)
5. In **Settings → Actions → General → Workflow permissions**, allow read/write access so the state file can be committed. Repository rules/branch protection may require adjustment.
6. Open **Actions → Roboflow Kaggle Slack Monitor → Run workflow**.
7. Confirm a one-time baseline message on Slack and `state/monitor.json` committed. Subsequent changes trigger notifications.

**Note:** If your Kaggle account uses a newer OAuth-style token rather than a classic API key, follow current Kaggle CLI authentication instructions and adjust the GitHub workflow. Do not assume all credential types work as `KAGGLE_KEY`.

## Kaggle in-notebook notifications
1. Set Kaggle Notebook secrets `SLACK_WEBHOOK_URL`; enable Internet when allowed.
2. Paste `scripts/kaggle_notify.py` into an initial cell, then run the commented training template after configuring `data.yaml`.
3. Set `RUN_BY` explicitly for each team member. This is self-reported, not verified identity.

## Operational caveats
- GitHub scheduled workflows can be delayed or skipped and usually run on the default branch.
- A webhook sender only knows the channel bound to its webhook.
- Avoid posting sensitive image data, API keys or labels to Slack.
- Kaggle notebook crashes or forced termination can prevent the notebook's error notification. Scheduled polling serves as an independent fallback.
- Persisting state in git can cause occasional push conflicts during simultaneous manual edits; concurrency prevents overlap among this workflow's runs, not outside writers.
- If a run posts messages successfully but fails to commit, the same messages may be sent at the next run.
- Only changed state fields available to your account/API are observable; ensure account API access and plan permissions.
