import os
import json
import datetime as dt
import sys
import requests
import gspread
from google.oauth2.service_account import Credentials


# ---------- Config ----------
DRY_RUN = os.environ.get("DRY_RUN", "").strip().lower() in ("1", "true", "yes")

# Validate and load environment variables
def get_required_env(key: str) -> str:
    value = os.environ.get(key, "").strip()
    if not value:
        print(f"ERROR: Required environment variable '{key}' is missing or empty.")
        sys.exit(1)
    return value

SHEET_ID = get_required_env("GOOGLE_SHEET_ID")
ADMIN_KEY = get_required_env("ANTHROPIC_ADMIN_KEY")

# Anthropic API configuration
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").strip()
if not ANTHROPIC_BASE_URL.startswith("https://"):
    print(f"ERROR: ANTHROPIC_BASE_URL must start with 'https://', got: {ANTHROPIC_BASE_URL}")
    sys.exit(1)

# Correct Anthropic Admin API endpoints
USAGE_ENDPOINT = os.environ.get("ANTHROPIC_USAGE_ENDPOINT", "/v1/organizations/usage_report/messages").strip()
COST_ENDPOINT = os.environ.get("ANTHROPIC_COST_ENDPOINT", "/v1/organizations/cost_report").strip()
ANTHROPIC_VERSION = os.environ.get("ANTHROPIC_VERSION", "2023-06-01").strip()

# Validate endpoints start with /v1/
for endpoint_name, endpoint_value in [("USAGE_ENDPOINT", USAGE_ENDPOINT), ("COST_ENDPOINT", COST_ENDPOINT)]:
    if not endpoint_value.startswith("/v1/"):
        print(f"ERROR: {endpoint_name} must start with '/v1/', got: {endpoint_value}")
        sys.exit(1)

# Load and validate Google service account JSON
service_account_json_str = get_required_env("GOOGLE_SERVICE_ACCOUNT_JSON")
try:
    SERVICE_ACCOUNT_JSON = json.loads(service_account_json_str)
    if "client_email" not in SERVICE_ACCOUNT_JSON:
        print("ERROR: GOOGLE_SERVICE_ACCOUNT_JSON missing 'client_email' field.")
        sys.exit(1)
    if "private_key" not in SERVICE_ACCOUNT_JSON:
        print("ERROR: GOOGLE_SERVICE_ACCOUNT_JSON missing 'private_key' field.")
        sys.exit(1)
    print(f"Using service account: {SERVICE_ACCOUNT_JSON['client_email']}")
except json.JSONDecodeError as e:
    print(f"ERROR: GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON: {e}")
    sys.exit(1)


def iso_now():
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def fetch_json(path: str, endpoint_name: str = "", params: dict = None):
    """Fetch JSON from Anthropic API with proper error handling."""
    url = ANTHROPIC_BASE_URL.rstrip("/") + path
    headers = {
        "x-api-key": ADMIN_KEY,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }

    print(f"Fetching {endpoint_name or path}...")
    print(f"  URL: {url}")
    if params:
        print(f"  Params: {params}")

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)

        if resp.status_code != 200:
            print(f"ERROR: API returned status {resp.status_code}")
            print(f"Response: {resp.text[:500]}")
            sys.exit(1)

        return resp.json()
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Failed to fetch {endpoint_name or path}: {e}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Failed to parse JSON response: {e}")
        print(f"Response text: {resp.text[:500]}")
        sys.exit(1)


def open_sheet():
    """Open Google Sheet with validation."""
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]

    try:
        creds = Credentials.from_service_account_info(SERVICE_ACCOUNT_JSON, scopes=scopes)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(SHEET_ID)

        print(f"Opened spreadsheet: {sh.title}")

        # Validate it's actually a Google Sheet
        try:
            sh.sheet1  # Try to access default sheet
        except Exception as e:
            if "not supported" in str(e).lower():
                print("ERROR: This document is not a Google Sheet (it may be an XLSX file).")
                print("Please ensure you're using a Google Sheets spreadsheet.")
                sys.exit(1)
            raise

        return sh

    except gspread.exceptions.SpreadsheetNotFound:
        print(f"ERROR: Spreadsheet with ID '{SHEET_ID}' not found.")
        print(f"Make sure:")
        print(f"  1. The GOOGLE_SHEET_ID is correct")
        print(f"  2. The sheet is shared with: {SERVICE_ACCOUNT_JSON['client_email']}")
        print(f"  3. The service account has 'Editor' permissions")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to open Google Sheet: {e}")
        sys.exit(1)


def get_or_create_worksheet(sh, title: str, headers: list):
    """Get existing worksheet or create it with headers."""
    try:
        ws = sh.worksheet(title)
        print(f"Found existing worksheet: {title}")
    except gspread.exceptions.WorksheetNotFound:
        print(f"Creating new worksheet: {title}")
        ws = sh.add_worksheet(title=title, rows=1000, cols=20)
        ws.append_row(headers, value_input_option="RAW")
        print(f"Added headers to {title}: {headers}")

    return ws


def append_rows(ws, rows, sheet_name: str = ""):
    """Append rows to worksheet, with dry-run support."""
    if not rows:
        print(f"No rows to append to {sheet_name or ws.title}")
        return

    if DRY_RUN:
        print(f"\n[DRY RUN] Would append {len(rows)} rows to '{sheet_name or ws.title}':")
        for i, row in enumerate(rows[:3]):  # Show first 3 rows
            print(f"  Row {i+1}: {row}")
        if len(rows) > 3:
            print(f"  ... and {len(rows) - 3} more rows")
    else:
        ws.append_rows(rows, value_input_option="RAW")
        print(f"Appended {len(rows)} rows to '{sheet_name or ws.title}'")


def normalize_usage(payload: dict):
    """Normalize usage report data into rows."""
    rows = []
    ts = iso_now()
    data_items = payload.get("data", [])

    for data_item in data_items:
        # Each data item contains results array with actual usage data
        results = data_item.get("results", [])
        for item in results:
            # Handle both cached and uncached tokens
            uncached_input = item.get("uncached_input_tokens", 0)
            cached_input = item.get("cache_read_input_tokens", 0)
            total_input_tokens = uncached_input + cached_input

            rows.append([
                ts,
                item.get("workspace_id") or "",
                item.get("model") or "",
                total_input_tokens,
                item.get("output_tokens", ""),
                "",  # cost_usd not in usage report
                json.dumps(item),
            ])
    return rows


def normalize_cost(payload: dict):
    """Normalize cost report data into rows."""
    rows = []
    ts = iso_now()
    data_items = payload.get("data", [])

    for data_item in data_items:
        # Extract date range from data item
        period = f"{data_item.get('starting_at', '')} to {data_item.get('ending_at', '')}"

        # Each data item contains results array with actual cost data
        results = data_item.get("results", [])
        for item in results:
            rows.append([
                ts,
                item.get("workspace_id") or "",
                item.get("model") or "",
                period,  # Use the period from data_item
                item.get("amount", ""),
                item.get("description") or item.get("cost_type") or "",
                json.dumps(item),
            ])
    return rows


def get_date_range():
    """Get date range for API queries (last 24 hours by default)."""
    # Allow custom lookback via env var (in hours)
    lookback_hours = int(os.environ.get("LOOKBACK_HOURS", "24"))

    ending_at = dt.datetime.utcnow()
    starting_at = ending_at - dt.timedelta(hours=lookback_hours)

    # Format as ISO 8601 (YYYY-MM-DD)
    return {
        "starting_at": starting_at.strftime("%Y-%m-%d"),
        "ending_at": ending_at.strftime("%Y-%m-%d")
    }


def main():
    print("=" * 60)
    print("Anthropic Usage & Cost Logger")
    print("=" * 60)

    if DRY_RUN:
        print("\n*** DRY RUN MODE - No data will be written to sheets ***\n")

    # Open Google Sheet
    sh = open_sheet()

    # Get or create worksheets with headers
    usage_headers = ["timestamp", "workspace_id", "model", "input_tokens", "output_tokens", "cost_usd", "raw_json"]
    cost_headers = ["timestamp", "workspace_id", "model", "date", "cost_usd", "usage_type", "raw_json"]

    usage_ws = get_or_create_worksheet(sh, "usage", usage_headers)
    cost_ws = get_or_create_worksheet(sh, "cost", cost_headers)

    # Get date range for API queries
    date_params = get_date_range()
    print(f"\nFetching data from {date_params['starting_at']} to {date_params['ending_at']}")

    # Fetch data from Anthropic
    print("\nFetching data from Anthropic API...")
    usage_payload = fetch_json(USAGE_ENDPOINT, "usage report", params=date_params)
    cost_payload = fetch_json(COST_ENDPOINT, "cost report", params=date_params)

    # Normalize data
    print("\nNormalizing data...")
    usage_rows = normalize_usage(usage_payload)
    cost_rows = normalize_cost(cost_payload)

    print(f"Prepared {len(usage_rows)} usage rows")
    print(f"Prepared {len(cost_rows)} cost rows")

    # Append to sheets
    print("\nWriting to Google Sheets...")
    append_rows(usage_ws, usage_rows, "usage")
    append_rows(cost_ws, cost_rows, "cost")

    print("\n" + "=" * 60)
    print("✓ Sync completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
