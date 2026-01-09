# Anthropic Usage & Cost Logger

Automatically logs Anthropic organization usage and cost data to Google Sheets using GitHub Actions.

## What It Does

- Runs every 15 minutes via GitHub Actions (configurable)
- Fetches usage and cost data from Anthropic Admin API
- Appends new rows to a Google Sheet with two tabs:
  - `usage` - Message usage metrics (tokens, costs by workspace/model)
  - `cost` - Cost report data (spending by date/workspace/model)

## Prerequisites

1. **Anthropic Admin API Key** - You need admin access to your Anthropic organization
2. **Google Cloud Project** - With Sheets API enabled
3. **Google Service Account** - With access to your target spreadsheet
4. **Google Sheet** - Must be a real Google Sheets document (not XLSX)

## Setup Instructions

### 1. Create Google Service Account

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create or select a project
3. Enable the **Google Sheets API**:
   - Navigate to "APIs & Services" > "Library"
   - Search for "Google Sheets API"
   - Click "Enable"
4. Create a service account:
   - Navigate to "IAM & Admin" > "Service Accounts"
   - Click "Create Service Account"
   - Give it a name (e.g., "anthropic-logger")
   - Click "Create and Continue"
   - Skip granting roles (not needed)
   - Click "Done"
5. Create a key for the service account:
   - Click on the service account you just created
   - Go to "Keys" tab
   - Click "Add Key" > "Create new key"
   - Choose "JSON" format
   - Save the downloaded JSON file securely

**Important:** Note the service account email (looks like `name@project-id.iam.gserviceaccount.com`) - you'll need this to share your spreadsheet.

### 2. Create Google Sheet

1. Create a new Google Sheets spreadsheet
2. Copy the Sheet ID from the URL:
   ```
   https://docs.google.com/spreadsheets/d/[SHEET_ID]/edit
   ```
3. **Share the sheet with your service account email** (from step 1):
   - Click "Share" button
   - Paste the service account email
   - Give it "Editor" permissions
   - Click "Send"

### 3. Get Anthropic Admin API Key

1. Log in to [Anthropic Console](https://console.anthropic.com)
2. Go to your organization settings
3. Generate an Admin API key (requires org admin permissions)
4. Copy the key - you won't be able to see it again

### 4. Configure GitHub Secrets

Add these secrets to your GitHub repository:

1. Go to your repo > Settings > Secrets and variables > Actions
2. Click "New repository secret" for each:

| Secret Name | Description | How to Get It |
|-------------|-------------|---------------|
| `GOOGLE_SHEET_ID` | The ID from your Google Sheet URL | Copy from URL (see step 2) |
| `ANTHROPIC_ADMIN_KEY` | Your Anthropic admin API key | From Anthropic Console (step 3) |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Full contents of the service account JSON file | Paste entire JSON file contents |

**Note:** When you view GitHub secrets later, they'll appear blank - this is normal security behavior.

### 5. Run the Workflow

1. Go to Actions tab in your GitHub repo
2. Click "Sync Anthropic logs to Google Sheets"
3. Click "Run workflow"
4. The workflow will:
   - Fetch usage and cost data
   - Create `usage` and `cost` tabs if they don't exist
   - Append new rows to each tab

## Configuration

### Environment Variables

You can customize behavior with these optional environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DRY_RUN` | `false` | Set to `1` or `true` to test without writing to sheets |
| `LOOKBACK_HOURS` | `24` | How many hours back to fetch data (e.g., `24` for last day, `168` for last week) |
| `ANTHROPIC_BASE_URL` | `https://api.anthropic.com` | Anthropic API base URL |
| `ANTHROPIC_USAGE_ENDPOINT` | `/v1/organizations/usage_report/messages` | Usage report endpoint |
| `ANTHROPIC_COST_ENDPOINT` | `/v1/organizations/cost_report` | Cost report endpoint |
| `ANTHROPIC_VERSION` | `2023-06-01` | API version header |

### Schedule

The workflow runs every 15 minutes by default. To change this, edit `.github/workflows/sync.yml`:

```yaml
schedule:
  - cron: "*/15 * * * *"  # Every 15 minutes
```

Common schedules:
- Every hour: `"0 * * * *"`
- Every 6 hours: `"0 */6 * * *"`
- Daily at midnight: `"0 0 * * *"`

## Testing Locally

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set environment variables:
   ```bash
   export GOOGLE_SHEET_ID="your-sheet-id"
   export ANTHROPIC_ADMIN_KEY="your-admin-key"
   export GOOGLE_SERVICE_ACCOUNT_JSON='{"type":"service_account",...}'
   ```

3. Run in dry-run mode first (safe, won't write to sheets):
   ```bash
   export DRY_RUN=1
   python sync.py
   ```

4. Run for real:
   ```bash
   unset DRY_RUN
   python sync.py
   ```

## Troubleshooting

### Error: "Spreadsheet not found"

**Cause:** The service account doesn't have access to the sheet.

**Fix:**
1. Verify `GOOGLE_SHEET_ID` is correct
2. Share the sheet with your service account email (found in the JSON as `client_email`)
3. Give it "Editor" permissions

### Error: "This operation is not supported for this document"

**Cause:** The document is an XLSX file, not a Google Sheet.

**Fix:**
1. Create a new Google Sheets spreadsheet (not XLSX)
2. Update `GOOGLE_SHEET_ID` to the new sheet ID

### Error: "GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON"

**Cause:** The JSON is malformed, truncated, or has extra characters.

**Fix:**
1. Re-download the service account JSON from Google Cloud Console
2. Copy the entire file contents exactly
3. Paste into GitHub secret without modifications
4. Ensure no extra spaces or newlines were added

### Error: "API returned status 404"

**Cause:** Using wrong Anthropic API endpoints.

**Fix:** The script now uses correct endpoints by default:
- Usage: `/v1/organizations/usage_report/messages`
- Cost: `/v1/organizations/cost_report`

If you've overridden these with env vars, remove the overrides.

### Error: "Required environment variable 'X' is missing"

**Cause:** A required secret isn't set in GitHub.

**Fix:**
1. Go to repo Settings > Secrets and variables > Actions
2. Verify all three required secrets are present:
   - `GOOGLE_SHEET_ID`
   - `ANTHROPIC_ADMIN_KEY`
   - `GOOGLE_SERVICE_ACCOUNT_JSON`

### No rows appearing in sheet

**Possible causes:**

1. **No data in time range:** The API may return empty results if there's no recent activity
   - Check the script output to see how many rows were prepared
   - Try running after some API usage

2. **Wrong API endpoints:** Verify you're using the correct endpoints (see above)

3. **Permissions:** Ensure service account has "Editor" (not "Viewer") access

### Checking logs

1. Go to Actions tab in GitHub
2. Click on a workflow run
3. Click "Run sync" step
4. View detailed logs including API responses and row counts

## Sheet Structure

### Usage Tab

| Column | Description |
|--------|-------------|
| timestamp | When this row was logged (ISO 8601) |
| workspace_id | Anthropic workspace identifier |
| model | Model name (e.g., claude-3-opus-20240229) |
| input_tokens | Number of input tokens |
| output_tokens | Number of output tokens |
| cost_usd | Cost in USD for this usage |
| raw_json | Full JSON response for debugging |

### Cost Tab

| Column | Description |
|--------|-------------|
| timestamp | When this row was logged (ISO 8601) |
| workspace_id | Anthropic workspace identifier |
| model | Model name |
| date | Date of the cost entry |
| cost_usd | Cost in USD |
| usage_type | Type of usage |
| raw_json | Full JSON response for debugging |

## Data Handling

- **Append-only:** Rows are never deleted or modified
- **Deduplication:** Not implemented - you may see duplicate entries if the script runs multiple times for the same time period
- **Pagination:** Not currently implemented - if you have a large organization, you may need to add pagination support

## Security Notes

- Never commit your service account JSON or API keys to git
- Use GitHub secrets for all sensitive values
- The script validates that secrets are present before running
- No secrets are printed to logs

## License

MIT
