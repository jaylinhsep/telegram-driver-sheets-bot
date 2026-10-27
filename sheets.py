import os
import re
import csv
import time
import logging
import asyncio
from io import StringIO
from typing import List, Dict, Any, Optional, Tuple

import requests

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    gspread = None
    Credentials = None
    GSPREAD_AVAILABLE = False

import config

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Column mapping in tab 'DanhSachXe' (1-based index)
# Col 1: ĐỘI XE
# Col 2: SỐ XE
# Col 3: TÊN LÁI XE
# Col 4: SĐT
# Col 5: CCCD
# Col 6: GPLX
FIELD_MAP = {
    "vendor": 1,
    "so_xe": 2,
    "ten_lai_xe": 3,
    "sdt": 4,
    "cccd": 5,
    "gplx": 6,
}

FIELD_TITLES = {
    "vendor": "🏢 Vendor / Đội xe",
    "so_xe": "🚗 Biển số xe",
    "ten_lai_xe": "👤 Tên lái xe",
    "sdt": "📞 Số điện thoại",
    "cccd": "🪪 Số CCCD",
    "gplx": "📄 Số GPLX",
}

# Known Google Sheet GIDs for direct public export
GID_DANH_SACH_XE = "1046738475"
GID_VENDOR = "331541216"


def normalize_plate(plate: str) -> str:
    """Normalize license plate by removing spaces, dots, dashes and uppercasing."""
    if not plate:
        return ""
    cleaned = re.sub(r"[\s\.\-_/]+", "", str(plate)).strip().upper()
    return cleaned


class GoogleSheetsManager:
    """
    Manages connection, caching, reading, and updating driver/vehicle records.
    Supports 3 modes:
      1. Google Service Account (gspread)
      2. Google Apps Script Web App (NO Google Cloud credentials needed!)
      3. Public CSV Export (Instant read-only fallback)
    """

    def __init__(self):
        self._client: Optional[Any] = None
        self._spreadsheet: Optional[Any] = None
        self._data_sheet: Optional[Any] = None
        self._vendor_sheet: Optional[Any] = None

        # In-memory cached data
        self._cached_vehicles: List[Dict[str, Any]] = []
        self._cached_vendors: List[str] = []
        self._last_synced: float = 0
        self._lock = asyncio.Lock()

    def is_service_account_connected(self) -> bool:
        return self._client is not None and self._spreadsheet is not None

    def is_connected(self) -> bool:
        """True if we have write capability (via Service Account OR Apps Script Web App)."""
        return self.is_service_account_connected() or bool(config.GOOGLE_APPS_SCRIPT_URL)

    def connect(self) -> bool:
        """Initialize connection via Service Account if available."""
        if not GSPREAD_AVAILABLE:
            return False

        creds_dict = config.get_service_account_dict()
        if not creds_dict:
            return False

        try:
            creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
            self._client = gspread.authorize(creds)
            self._spreadsheet = self._client.open_by_key(config.GOOGLE_SHEET_ID)

            try:
                self._data_sheet = self._spreadsheet.worksheet(config.GOOGLE_SHEET_TAB_DATA)
            except Exception:
                self._data_sheet = self._spreadsheet.get_worksheet(0)

            try:
                self._vendor_sheet = self._spreadsheet.worksheet(config.GOOGLE_SHEET_TAB_VENDOR)
            except Exception:
                self._vendor_sheet = None

            logger.info(f"✅ Đã kết nối Google Sheets qua Service Account: '{self._spreadsheet.title}'")
            return True
        except Exception as e:
            logger.warning(f"Chưa thể kết nối Service Account: {e}")
            return False

    def _fetch_public_csv(self, gid: str) -> List[List[str]]:
        """Fetch and parse CSV rows directly from public Google Sheet export."""
        url = f"https://docs.google.com/spreadsheets/d/{config.GOOGLE_SHEET_ID}/export?format=csv&gid={gid}"
        resp = requests.get(url, timeout=12)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        f = StringIO(resp.text)
        reader = csv.reader(f)
        return [row for row in reader]

    async def sync_data(self, force: bool = False) -> Tuple[bool, str]:
        """
        Sync data into local cache.
        Tries:
          1. Service Account (gspread)
          2. Google Apps Script Web App (?action=read)
          3. Public CSV Export
        """
        async with self._lock:
            now = time.time()
            if not force and (now - self._last_synced < config.CACHE_TTL) and self._cached_vehicles:
                return True, "Dữ liệu vẫn còn trong bộ nhớ đệm (cache)."

            loop = asyncio.get_running_loop()
            raw_rows: List[List[str]] = []
            vendor_rows: List[List[str]] = []
            source_desc = ""

            # Attempt 1: Service Account
            if not self.is_service_account_connected():
                self.connect()

            if self.is_service_account_connected() and self._data_sheet:
                try:
                    raw_rows = await loop.run_in_executor(None, self._data_sheet.get_all_values)
                    if self._vendor_sheet:
                        vendor_rows = await loop.run_in_executor(None, self._vendor_sheet.get_all_values)
                    source_desc = "Google Service Account"
                except Exception as e_sa:
                    logger.warning(f"Lỗi đọc qua Service Account, thử phương thức khác: {e_sa}")

            # Attempt 2: Google Apps Script Web App
            if not raw_rows and config.GOOGLE_APPS_SCRIPT_URL:
                try:
                    def _call_apps_script_read():
                        r = requests.get(
                            f"{config.GOOGLE_APPS_SCRIPT_URL}?action=read",
                            timeout=15,
                            allow_redirects=True,
                        )
                        return r.json()

                    res_json = await loop.run_in_executor(None, _call_apps_script_read)
                    if res_json.get("status") == "success":
                        raw_rows = res_json.get("rows", [])
                        v_list = res_json.get("vendors", [])
                        vendor_rows = [[v] for v in v_list]
                        source_desc = "Google Apps Script Web App"
                except Exception as e_as:
                    logger.warning(f"Lỗi đọc qua Apps Script Web App: {e_as}")

            # Attempt 3: Public CSV Export (Zero Credentials Needed!)
            if not raw_rows:
                try:
                    raw_rows = await loop.run_in_executor(None, lambda: self._fetch_public_csv(GID_DANH_SACH_XE))
                    try:
                        vendor_rows = await loop.run_in_executor(None, lambda: self._fetch_public_csv(GID_VENDOR))
                    except Exception:
                        vendor_rows = []
                    source_desc = "Public CSV Link"
                except Exception as e_csv:
                    logger.error(f"Lỗi tải public CSV: {e_csv}")
                    return False, f"Không thể đọc Google Sheet: {e_csv}"

            if not raw_rows:
                self._cached_vehicles = []
                self._cached_vendors = []
                self._last_synced = now
                return True, "Sheet đang trống."

            # Parse records
            vehicles = []
            unique_vendors = set()

            for row_idx, row in enumerate(raw_rows[1:], start=2):
                padded = row + [""] * (6 - len(row))
                vendor = padded[0].strip()
                so_xe = padded[1].strip()
                ten_lai = padded[2].strip()
                sdt = padded[3].strip()
                cccd = padded[4].strip()
                gplx = padded[5].strip()

                if not vendor and not so_xe:
                    continue

                if vendor:
                    unique_vendors.add(vendor)

                vehicles.append(
                    {
                        "row_index": row_idx,
                        "vendor": vendor,
                        "so_xe": so_xe,
                        "norm_so_xe": normalize_plate(so_xe),
                        "ten_lai_xe": ten_lai,
                        "sdt": sdt,
                        "cccd": cccd,
                        "gplx": gplx,
                    }
                )

            # Master vendors from VENDOR tab
            for r in vendor_rows[1:]:
                if r and r[0].strip():
                    unique_vendors.add(r[0].strip())

            self._cached_vehicles = vehicles
            self._cached_vendors = sorted(list(unique_vendors))
            self._last_synced = now

            msg = f"Đã đồng bộ {len(self._cached_vehicles)} xe từ {len(self._cached_vendors)} vendor (Nguồn: {source_desc})."
            logger.info(msg)
            return True, msg

    async def get_all_vendors(self) -> List[str]:
        """Get sorted list of all unique vendors."""
        await self.sync_data(force=False)
        return self._cached_vendors

    async def get_vehicles_by_vendor(self, vendor_name: str) -> List[Dict[str, Any]]:
        """Get all vehicle records for a given vendor name (case-insensitive)."""
        await self.sync_data(force=False)
        v_target = vendor_name.strip().lower()
        return [
            v
            for v in self._cached_vehicles
            if v.get("vendor", "").strip().lower() == v_target
        ]

    async def get_vehicle_by_plate(self, plate: str) -> Optional[Dict[str, Any]]:
        """Get vehicle record matching the normalized plate."""
        await self.sync_data(force=False)
        norm = normalize_plate(plate)
        if not norm:
            return None

        for v in self._cached_vehicles:
            if v.get("norm_so_xe") == norm:
                return v

        for v in self._cached_vehicles:
            if norm in v.get("norm_so_xe", ""):
                return v

        return None

    async def update_vehicle_field(
        self, row_index: int, field_code: str, new_value: str
    ) -> Tuple[bool, str]:
        """Update a specific field in Google Sheet."""
        if field_code not in FIELD_MAP:
            return False, f"Trường cập nhật không hợp lệ: {field_code}"

        col_index = FIELD_MAP[field_code]
        cleaned_val = new_value.strip()
        loop = asyncio.get_running_loop()

        # Method 1: Google Service Account
        if self.is_service_account_connected() and self._data_sheet:
            try:
                await loop.run_in_executor(
                    None,
                    lambda: self._data_sheet.update_cell(row_index, col_index, cleaned_val),
                )
                self._update_local_cache(row_index, field_code, cleaned_val)
                field_title = FIELD_TITLES.get(field_code, field_code)
                return True, f"✅ Đã cập nhật thành công '{field_title}' thành: {cleaned_val}"
            except Exception as e:
                logger.error(f"Lỗi khi update cell Service Account: {e}")

        # Method 2: Google Apps Script Web App (NO CREDENTIALS REQUIRED!)
        if config.GOOGLE_APPS_SCRIPT_URL:
            try:
                payload = {
                    "action": "update_cell",
                    "row": row_index,
                    "col": col_index,
                    "value": cleaned_val,
                }
                def _post_apps_script():
                    r = requests.post(
                        config.GOOGLE_APPS_SCRIPT_URL,
                        json=payload,
                        timeout=15,
                        allow_redirects=True,
                    )
                    return r.json()

                res = await loop.run_in_executor(None, _post_apps_script)
                if res.get("status") == "success":
                    self._update_local_cache(row_index, field_code, cleaned_val)
                    field_title = FIELD_TITLES.get(field_code, field_code)
                    return True, f"✅ Đã cập nhật thành công '{field_title}' thành: {cleaned_val}"
                else:
                    return False, f"Google Apps Script báo lỗi: {res.get('message', 'Không rõ')}"
            except Exception as e:
                logger.error(f"Lỗi khi gọi Apps Script update_cell: {e}")
                return False, f"Lỗi gọi Apps Script: {e}"

        return False, (
            "⚠️ Bot hiện chưa được cấp quyền GHI vào Google Sheet.\n"
            "Vì Google API không cho phép bot tự động ghi trực tiếp ẩn danh qua link công khai, bạn chỉ cần:\n"
            "👉 Cách 1 (Khuyên dùng - 1 phút): Tạo Google Apps Script Web App gắn vào Sheet và thêm biến GOOGLE_APPS_SCRIPT_URL (Xem hướng dẫn).\n"
            "👉 Cách 2: Tạo Service Account JSON trên Google Cloud."
        )

    def _update_local_cache(self, row_index: int, field_code: str, cleaned_val: str):
        """Update in-memory cache directly."""
        for v in self._cached_vehicles:
            if v.get("row_index") == row_index:
                v[field_code] = cleaned_val
                if field_code == "so_xe":
                    v["norm_so_xe"] = normalize_plate(cleaned_val)
                if field_code == "vendor":
                    if cleaned_val and cleaned_val not in self._cached_vendors:
                        self._cached_vendors.append(cleaned_val)
                        self._cached_vendors.sort()
                break

    async def add_vehicle(
        self,
        vendor: str,
        so_xe: str,
        ten_lai_xe: str = "",
        sdt: str = "",
        cccd: str = "",
        gplx: str = "",
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Append a new vehicle/driver row to Google Sheets."""
        vendor_clean = vendor.strip().upper()
        plate_clean = so_xe.strip().upper()

        if not vendor_clean:
            return False, "Tên Vendor không được để trống.", None
        if not plate_clean:
            return False, "Biển số xe không được để trống.", None

        row_data = [
            vendor_clean,
            plate_clean,
            ten_lai_xe.strip(),
            sdt.strip(),
            cccd.strip(),
            gplx.strip(),
        ]
        loop = asyncio.get_running_loop()

        # Method 1: Google Service Account
        if self.is_service_account_connected() and self._data_sheet:
            try:
                await loop.run_in_executor(
                    None,
                    lambda: self._data_sheet.append_row(row_data, value_input_option="USER_ENTERED"),
                )
                if self._vendor_sheet:
                    try:
                        all_v = await loop.run_in_executor(None, self._vendor_sheet.col_values, 1)
                        if vendor_clean not in [x.strip().upper() for x in all_v]:
                            await loop.run_in_executor(
                                None,
                                lambda: self._vendor_sheet.append_row([vendor_clean], value_input_option="USER_ENTERED"),
                            )
                    except Exception as e_v:
                        logger.warning(f"Không thể ghi tab VENDOR: {e_v}")

                return True, "✅ Đã thêm xe mới thành công vào Google Sheet!", self._add_to_local_cache(row_data)
            except Exception as e:
                logger.error(f"Lỗi append_row Service Account: {e}")

        # Method 2: Google Apps Script Web App
        if config.GOOGLE_APPS_SCRIPT_URL:
            try:
                payload = {"action": "append_row", "row_data": row_data}
                def _post_apps_script_add():
                    r = requests.post(
                        config.GOOGLE_APPS_SCRIPT_URL,
                        json=payload,
                        timeout=15,
                        allow_redirects=True,
                    )
                    return r.json()

                res = await loop.run_in_executor(None, _post_apps_script_add)
                if res.get("status") == "success":
                    return True, "✅ Đã thêm xe mới thành công vào Google Sheet!", self._add_to_local_cache(row_data)
                else:
                    return False, f"Google Apps Script báo lỗi: {res.get('message', 'Không rõ')}", None
            except Exception as e:
                logger.error(f"Lỗi gọi Apps Script append_row: {e}")
                return False, f"Lỗi gọi Apps Script: {e}", None

        return False, (
            "⚠️ Bot hiện chưa được cấp quyền GHI vào Google Sheet.\n"
            "Vui lòng cấu hình GOOGLE_APPS_SCRIPT_URL hoặc GOOGLE_SERVICE_ACCOUNT_JSON."
        ), None

    def _add_to_local_cache(self, row_data: List[str]) -> Dict[str, Any]:
        """Add newly appended vehicle to local memory cache."""
        new_row_idx = len(self._cached_vehicles) + 2
        new_record = {
            "row_index": new_row_idx,
            "vendor": row_data[0],
            "so_xe": row_data[1],
            "norm_so_xe": normalize_plate(row_data[1]),
            "ten_lai_xe": row_data[2],
            "sdt": row_data[3],
            "cccd": row_data[4],
            "gplx": row_data[5],
        }
        self._cached_vehicles.append(new_record)
        if row_data[0] not in self._cached_vendors:
            self._cached_vendors.append(row_data[0])
            self._cached_vendors.sort()
        return new_record

    async def delete_vehicle(self, row_index: int) -> Tuple[bool, str]:
        """Delete a vehicle row from Google Sheet."""
        loop = asyncio.get_running_loop()

        # Method 1: Service Account
        if self.is_service_account_connected() and self._data_sheet:
            try:
                await loop.run_in_executor(None, lambda: self._data_sheet.delete_rows(row_index))
                self._remove_from_local_cache(row_index)
                return True, "✅ Đã xóa thông tin xe khỏi Google Sheet."
            except Exception as e:
                logger.error(f"Lỗi delete_rows Service Account: {e}")

        # Method 2: Google Apps Script Web App
        if config.GOOGLE_APPS_SCRIPT_URL:
            try:
                payload = {"action": "delete_row", "row": row_index}
                def _post_apps_script_del():
                    r = requests.post(
                        config.GOOGLE_APPS_SCRIPT_URL,
                        json=payload,
                        timeout=15,
                        allow_redirects=True,
                    )
                    return r.json()

                res = await loop.run_in_executor(None, _post_apps_script_del)
                if res.get("status") == "success":
                    self._remove_from_local_cache(row_index)
                    return True, "✅ Đã xóa thông tin xe khỏi Google Sheet."
                else:
                    return False, f"Google Apps Script báo lỗi: {res.get('message', 'Không rõ')}"
            except Exception as e:
                return False, f"Lỗi gọi Apps Script: {e}"

        return False, "Chưa cấu hình quyền ghi (GOOGLE_APPS_SCRIPT_URL hoặc GOOGLE_SERVICE_ACCOUNT_JSON)."

    def _remove_from_local_cache(self, row_index: int):
        """Remove row from local cache and adjust row indices."""
        self._cached_vehicles = [v for v in self._cached_vehicles if v.get("row_index") != row_index]
        for v in self._cached_vehicles:
            if v.get("row_index", 0) > row_index:
                v["row_index"] -= 1


# Global Singleton
sheets_manager = GoogleSheetsManager()
