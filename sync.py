import os
import json
import datetime as dt
import requests
import gspread
from google.oauth2.service_account import Credentials


# ---------- Config ----------
SHEET_ID = os.environ["GOOGLE_SHEET_ID"]  # the long ID in the sheet URL
ADMIN_KEY = os.environ["ANTHROPIC_ADMIN_KEY"]

ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
USAGE_ENDPOINT = os.environ.get("ANTHROPIC_USAGE_ENDPOINT", "/v1/admin/usage")
AUDIT_ENDPOINT = os.environ.get("ANTHROPIC_AUDIT_ENDPOINT", "/v1/admin/audit-logs")
ANTHROPIC_VERSION = os.environ.get("ANTHROPIC_VERSION", "2023-06-01")

SERVICE_ACCOUNT_JSON = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])


def iso_now():
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def fetch_json(path: str):
    url = ANTHROPIC_BASE_URL.rstrip("/") + path
    headers = {
        "x-api-key": ADMIN_KEY,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def open_sheet():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(SERVICE_ACCOUNT_JSON, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)
    return sh


def append_rows(ws, rows):
    if rows:
        ws.append_rows(rows, value_input_option="RAW")


def normalize_usage(payload: dict):
    rows = []
    ts = iso_now()
    items = payload.get("usage") or payload.get("data") or []
    for item in items:
        rows.append([
            ts,
            item.get("workspace_id", ""),
            item.get("model", ""),
            item.get("input_tokens", item.get("inputTokens", "")),
            item.get("output_tokens", item.get("outputTokens", "")),
            item.get("cost_usd", item.get("costUsd", "")),
            json.dumps(item),
        ])
    return rows


def normalize_audit(payload: dict):
    rows = []
    ts = iso_now()
    items = payload.get("events") or payload.get("audit_logs") or payload.get("data") or []
    for ev in items:
        rows.append([
            ev.get("timestamp", ts),
            ev.get("type", ev.get("event_type", "")),
            ev.get("actor", ""),
            ev.get("target", ""),
            ev.get("details", ""),
            json.dumps(ev),
        ])
    return rows


def main():
    sh = open_sheet()
    usage_ws = sh.worksheet("usage")
    audit_ws = sh.worksheet("audit")

    usage_payload = fetch_json(USAGE_ENDPOINT)
    audit_payload = fetch_json(AUDIT_ENDPOINT)

    usage_rows = normalize_usage(usage_payload)
    audit_rows = normalize_audit(audit_payload)

    append_rows(usage_ws, usage_rows)
    append_rows(audit_ws, audit_rows)

    print(f"Appended {len(usage_rows)} usage rows and {len(audit_rows)} audit rows.")


if __name__ == "__main__":
    main()
