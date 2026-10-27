import os
import re
import time
import logging
import asyncio
from typing import List, Dict, Any, Optional, Tuple

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

# Column mapping in tab 'DanhSachXe'
# 1-based index for gspread:
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


def normalize_plate(plate: str) -> str:
    """Normalize license plate by removing spaces, dots, dashes and uppercasing."""
    if not plate:
        return ""
    # Strip spaces, hyphens, dots, underscores, slashes
    cleaned = re.sub(r"[\s\.\-_/]+", "", str(plate)).strip().upper()
    return cleaned


class GoogleSheetsManager:
    """Manages connection, caching, reading, and updating driver/vehicle records in Google Sheets."""

    def __init__(self):
        self._client: Optional[gspread.Client] = None
        self._spreadsheet: Optional[gspread.Spreadsheet] = None
        self._data_sheet: Optional[gspread.Worksheet] = None
        self._vendor_sheet: Optional[gspread.Worksheet] = None

        # In-memory cached data
        self._cached_vehicles: List[Dict[str, Any]] = []
        self._cached_vendors: List[str] = []
        self._last_synced: float = 0
        self._lock = asyncio.Lock()

    def is_connected(self) -> bool:
        return self._client is not None and self._spreadsheet is not None

    def connect(self) -> bool:
        """Initialize connection to Google Sheets using service account credentials."""
        if not GSPREAD_AVAILABLE:
            logger.error("Thư viện 'gspread' chưa được cài đặt. Vui lòng chạy: pip install -r requirements.txt")
            return False

        creds_dict = config.get_service_account_dict()
        if not creds_dict:
            logger.warning(
                "Chưa cấu hình Google Service Account JSON. Bot sẽ chạy ở chế độ chờ cấu hình."
            )
            return False

        try:
            creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
            self._client = gspread.authorize(creds)
            self._spreadsheet = self._client.open_by_key(config.GOOGLE_SHEET_ID)

            # Connect to DanhSachXe worksheet
            try:
                self._data_sheet = self._spreadsheet.worksheet(config.GOOGLE_SHEET_TAB_DATA)
            except Exception:
                # If name doesn't match, fallback to first worksheet
                self._data_sheet = self._spreadsheet.get_worksheet(0)
                logger.warning(
                    f"Không tìm thấy tab '{config.GOOGLE_SHEET_TAB_DATA}', đã fallback sang tab đầu tiên: '{self._data_sheet.title}'"
                )

            # Connect to VENDOR worksheet (optional)
            try:
                self._vendor_sheet = self._spreadsheet.worksheet(config.GOOGLE_SHEET_TAB_VENDOR)
            except Exception:
                self._vendor_sheet = None
                logger.info(
                    f"Tab '{config.GOOGLE_SHEET_TAB_VENDOR}' không tồn tại hoặc chưa tạo. Sẽ lấy danh sách vendor trực tiếp từ dữ liệu xe."
                )

            logger.info(
                f"✅ Kết nối Google Sheet thành công! Spreadsheet: '{self._spreadsheet.title}'"
            )
            return True
        except Exception as e:
            logger.error(f"❌ Lỗi kết nối Google Sheets: {e}", exc_info=True)
            return False

    async def sync_data(self, force: bool = False) -> Tuple[bool, str]:
        """
        Sync data from Google Sheets into local cache.
        Skips if synced within CACHE_TTL unless force=True.
        """
        async with self._lock:
            now = time.time()
            if not force and (now - self._last_synced < config.CACHE_TTL) and self._cached_vehicles:
                return True, "Dữ liệu vẫn còn trong bộ nhớ đệm (cache)."

            if not self.is_connected():
                if not self.connect():
                    return False, "Chưa thể kết nối tới Google Sheet (Vui lòng kiểm tra Service Account JSON và quyền chia sẻ của sheet)."

            try:
                # Run network-bound gspread calls in a thread pool to avoid blocking asyncio loop
                loop = asyncio.get_running_loop()
                raw_rows = await loop.run_in_executor(None, self._data_sheet.get_all_values)

                if not raw_rows:
                    self._cached_vehicles = []
                    self._cached_vendors = []
                    self._last_synced = now
                    return True, "Sheet trống."

                # First row is header: ĐỘI XE, SỐ XE, TÊN LÁI XE, SĐT, CCCD, GPLX
                vehicles = []
                unique_vendors = set()

                for row_idx, row in enumerate(raw_rows[1:], start=2):
                    # Ensure at least 6 columns
                    padded = row + [""] * (6 - len(row))
                    vendor = padded[0].strip()
                    so_xe = padded[1].strip()
                    ten_lai = padded[2].strip()
                    sdt = padded[3].strip()
                    cccd = padded[4].strip()
                    gplx = padded[5].strip()

                    # Skip empty rows where both vendor and so_xe are blank
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

                # Sync vendor master tab if available
                if self._vendor_sheet:
                    try:
                        v_rows = await loop.run_in_executor(
                            None, self._vendor_sheet.get_all_values
                        )
                        for r in v_rows[1:]:
                            if r and r[0].strip():
                                unique_vendors.add(r[0].strip())
                    except Exception as e_v:
                        logger.warning(f"Lỗi khi đọc tab VENDOR: {e_v}")

                self._cached_vehicles = vehicles
                self._cached_vendors = sorted(list(unique_vendors))
                self._last_synced = now

                msg = f"Đã đồng bộ {len(self._cached_vehicles)} xe từ {len(self._cached_vendors)} vendor."
                logger.info(msg)
                return True, msg

            except Exception as e:
                logger.error(f"Lỗi khi tải dữ liệu từ Google Sheets: {e}", exc_info=True)
                return False, f"Lỗi đọc Google Sheet: {e}"

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

        # Fallback partial match if exact normalized match not found
        for v in self._cached_vehicles:
            if norm in v.get("norm_so_xe", ""):
                return v

        return None

    async def update_vehicle_field(
        self, row_index: int, field_code: str, new_value: str
    ) -> Tuple[bool, str]:
        """Update a specific field in Google Sheet for the given row_index."""
        if field_code not in FIELD_MAP:
            return False, f"Trường cập nhật không hợp lệ: {field_code}"

        col_index = FIELD_MAP[field_code]
        cleaned_val = new_value.strip()

        if not self.is_connected():
            if not self.connect():
                return False, "Không thể kết nối đến Google Sheets để cập nhật."

        try:
            loop = asyncio.get_running_loop()
            # gspread update_cell(row, col, value)
            await loop.run_in_executor(
                None,
                lambda: self._data_sheet.update_cell(row_index, col_index, cleaned_val),
            )

            # Update local cache immediately
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

            field_title = FIELD_TITLES.get(field_code, field_code)
            return True, f"✅ Đã cập nhật thành công '{field_title}' thành: {cleaned_val}"

        except Exception as e:
            logger.error(f"Lỗi khi update cell ({row_index}, {col_index}): {e}", exc_info=True)
            return False, f"Lỗi cập nhật Google Sheet: {e}"

    async def add_vehicle(
        self,
        vendor: str,
        so_xe: str,
        ten_lai_xe: str = "",
        sdt: str = "",
        cccd: str = "",
        gplx: str = "",
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Append a new vehicle/driver row to Google Sheets.
        Also appends vendor to VENDOR tab if not present.
        """
        vendor_clean = vendor.strip().upper()
        plate_clean = so_xe.strip().upper()

        if not vendor_clean:
            return False, "Tên Vendor không được để trống.", None
        if not plate_clean:
            return False, "Biển số xe không được để trống.", None

        if not self.is_connected():
            if not self.connect():
                return False, "Không thể kết nối đến Google Sheets để thêm mới.", None

        try:
            loop = asyncio.get_running_loop()

            row_data = [
                vendor_clean,
                plate_clean,
                ten_lai_xe.strip(),
                sdt.strip(),
                cccd.strip(),
                gplx.strip(),
            ]

            # Append row to DanhSachXe
            await loop.run_in_executor(
                None,
                lambda: self._data_sheet.append_row(
                    row_data, value_input_option="USER_ENTERED"
                ),
            )

            # If VENDOR tab exists, ensure vendor is listed there
            if self._vendor_sheet:
                try:
                    all_v = await loop.run_in_executor(
                        None, self._vendor_sheet.col_values, 1
                    )
                    v_upper = [x.strip().upper() for x in all_v]
                    if vendor_clean not in v_upper:
                        await loop.run_in_executor(
                            None,
                            lambda: self._vendor_sheet.append_row(
                                [vendor_clean], value_input_option="USER_ENTERED"
                            ),
                        )
                except Exception as e_v:
                    logger.warning(f"Không thể ghi tab VENDOR: {e_v}")

            # Calculate new row index
            new_row_idx = len(self._cached_vehicles) + 2
            new_record = {
                "row_index": new_row_idx,
                "vendor": vendor_clean,
                "so_xe": plate_clean,
                "norm_so_xe": normalize_plate(plate_clean),
                "ten_lai_xe": ten_lai_xe.strip(),
                "sdt": sdt.strip(),
                "cccd": cccd.strip(),
                "gplx": gplx.strip(),
            }

            self._cached_vehicles.append(new_record)
            if vendor_clean not in self._cached_vendors:
                self._cached_vendors.append(vendor_clean)
                self._cached_vendors.sort()

            return True, "✅ Đã thêm xe mới thành công vào Google Sheet!", new_record

        except Exception as e:
            logger.error(f"Lỗi khi append_row vào Google Sheet: {e}", exc_info=True)
            return False, f"Lỗi thêm vào Google Sheet: {e}", None

    async def delete_vehicle(self, row_index: int) -> Tuple[bool, str]:
        """Delete a vehicle row from Google Sheet."""
        if not self.is_connected():
            if not self.connect():
                return False, "Không thể kết nối đến Google Sheets để xóa."

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, lambda: self._data_sheet.delete_rows(row_index)
            )

            # Invalidate cache to force reload next time
            self._cached_vehicles = [
                v for v in self._cached_vehicles if v.get("row_index") != row_index
            ]
            # Decrement row indices of rows below
            for v in self._cached_vehicles:
                if v.get("row_index", 0) > row_index:
                    v["row_index"] -= 1

            return True, "✅ Đã xóa thông tin xe khỏi Google Sheet."
        except Exception as e:
            logger.error(f"Lỗi khi xóa dòng {row_index}: {e}", exc_info=True)
            return False, f"Lỗi xóa dòng trên Google Sheet: {e}"


# Global Singleton
sheets_manager = GoogleSheetsManager()
