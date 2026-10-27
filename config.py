import os
import json
import base64
from typing import List, Optional

# Telegram Bot Token
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

# Google Spreadsheet Configuration
GOOGLE_SHEET_ID: str = os.getenv("GOOGLE_SHEET_ID", "13ndQsSmBsKlHjIRQR0S0MO5BPqqL6J4CECBAYfQi1oo").strip()
GOOGLE_SHEET_TAB_DATA: str = os.getenv("GOOGLE_SHEET_TAB_DATA", "DanhSachXe").strip()
GOOGLE_SHEET_TAB_VENDOR: str = os.getenv("GOOGLE_SHEET_TAB_VENDOR", "VENDOR").strip()

# Option 1: Google Apps Script Web App URL (KHÔNG CẦN TẠO CREDENTIALS GOOGLE CLOUD)
# Chỉ cần vào Tiện ích mở rộng -> Apps Script trên Sheet và triển khai Web App
GOOGLE_APPS_SCRIPT_URL: str = os.getenv("GOOGLE_APPS_SCRIPT_URL", "").strip()

# Option 2: Google Service Account Credentials (Dành cho tài khoản Google Cloud)
# Can be provided via:
# 1. Environment variable GOOGLE_SERVICE_ACCOUNT_JSON (raw JSON string or base64)
# 2. File path via GOOGLE_SERVICE_ACCOUNT_FILE (e.g., 'service_account.json')
GOOGLE_SERVICE_ACCOUNT_JSON: str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
GOOGLE_SERVICE_ACCOUNT_FILE: str = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json").strip()

# Web Server & Webhook Configuration (Render.com compatibility)
PORT: int = int(os.getenv("PORT", "8000"))
WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "").strip()
RENDER_EXTERNAL_URL: str = os.getenv("RENDER_EXTERNAL_URL", "").strip()

# Cache TTL in seconds (to minimize Google Sheets API quota usage)
CACHE_TTL: int = int(os.getenv("CACHE_TTL", "60"))

# Allowed Telegram Chat/User IDs (Leave empty to allow all users)
_allowed_raw = os.getenv("ALLOWED_CHAT_IDS", "").strip()
ALLOWED_CHAT_IDS: List[int] = [
    int(x.strip()) for x in _allowed_raw.split(",") if x.strip().lstrip("-").isdigit()
]


def get_service_account_dict() -> Optional[dict]:
    """
    Parse and return service account credentials as a Python dictionary.
    Supports raw JSON string, Base64-encoded JSON, or local JSON file.
    """
    if GOOGLE_SERVICE_ACCOUNT_JSON:
        # Check if raw JSON
        try:
            return json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
        except json.JSONDecodeError:
            pass

        # Try base64 decode
        try:
            decoded = base64.b64decode(GOOGLE_SERVICE_ACCOUNT_JSON).decode("utf-8")
            return json.loads(decoded)
        except Exception:
            pass

    # Check local file
    if os.path.exists(GOOGLE_SERVICE_ACCOUNT_FILE):
        try:
            with open(GOOGLE_SERVICE_ACCOUNT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    # Common alternate filename
    if os.path.exists("credentials.json"):
        try:
            with open("credentials.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    return None
