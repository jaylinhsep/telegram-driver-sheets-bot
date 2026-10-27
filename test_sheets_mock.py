"""
Comprehensive Unit Test Suite for Telegram Driver Sheets Bot
Tests regex patterns, plate normalization, data formatting, and mocked Google Sheet operations.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import re
import unittest
from typing import Dict, Any, List

from sheets import normalize_plate, FIELD_MAP, FIELD_TITLES
from bot import build_vehicle_card, build_add_draft_card, find_matching_vendors


class MockWorksheet:
    def __init__(self, title: str, rows: List[List[str]]):
        self.title = title
        self.rows = [list(r) for r in rows]

    def get_all_values(self):
        return [list(r) for r in self.rows]

    def update_cell(self, row: int, col: int, value: str):
        # 1-based indexing
        r_idx = row - 1
        c_idx = col - 1
        while len(self.rows) <= r_idx:
            self.rows.append([])
        while len(self.rows[r_idx]) <= c_idx:
            self.rows[r_idx].append("")
        self.rows[r_idx][c_idx] = str(value)

    def append_row(self, row_data: list, value_input_option: str = "USER_ENTERED"):
        self.rows.append([str(x) for x in row_data])

    def delete_rows(self, row: int):
        r_idx = row - 1
        if 0 <= r_idx < len(self.rows):
            self.rows.pop(r_idx)

    def col_values(self, col: int):
        c_idx = col - 1
        vals = []
        for r in self.rows:
            if len(r) > c_idx:
                vals.append(r[c_idx])
            else:
                vals.append("")
        return vals


class TestDriverBotLogic(unittest.TestCase):

    def test_normalize_plate(self):
        """Test license plate normalization across common formats."""
        self.assertEqual(normalize_plate("50E65375"), "50E65375")
        self.assertEqual(normalize_plate("50E-653.75"), "50E65375")
        self.assertEqual(normalize_plate(" 61h 13200 "), "61H13200")
        self.assertEqual(normalize_plate("51C-714.17"), "51C71417")
        self.assertEqual(normalize_plate("38H-031.41"), "38H03141")
        self.assertEqual(normalize_plate(""), "")
        self.assertEqual(normalize_plate(None), "")

    def test_add_regex_parsing(self):
        """Test parsing of /add with or without quotes."""
        pattern = r"^/add(?:\s+[\"']?(.*?)[\"']?)?$"

        # With double quotes
        m1 = re.match(pattern, '/add "AN THANH PHAT"', re.IGNORECASE)
        self.assertTrue(bool(m1))
        self.assertEqual(m1.group(1).strip().strip('"\''), "AN THANH PHAT")

        # Without quotes
        m2 = re.match(pattern, "/add BAO NAM PHAT", re.IGNORECASE)
        self.assertTrue(bool(m2))
        self.assertEqual(m2.group(1).strip().strip('"\''), "BAO NAM PHAT")

        # Single quotes
        m3 = re.match(pattern, "/add 'TÂN TIẾN PHÁT'", re.IGNORECASE)
        self.assertTrue(bool(m3))
        self.assertEqual(m3.group(1).strip().strip('"\''), "TÂN TIẾN PHÁT")

        # Empty /add
        m4 = re.match(pattern, "/add", re.IGNORECASE)
        self.assertTrue(bool(m4))
        self.assertFalse(m4.group(1))

    def test_direct_plate_command_regex(self):
        """Test matching commands like /50E65375."""
        cmd_pattern = r"^/\d{2}[a-zA-Z0-9_]+$"
        self.assertTrue(bool(re.match(cmd_pattern, "/50E65375")))
        self.assertTrue(bool(re.match(cmd_pattern, "/61H13200")))
        self.assertTrue(bool(re.match(cmd_pattern, "/50e65375")))
        self.assertFalse(bool(re.match(cmd_pattern, "/vendor")))
        self.assertFalse(bool(re.match(cmd_pattern, "/add")))

    def test_build_cards(self):
        """Test vehicle details card and add draft card rendering."""
        sample_v = {
            "vendor": "AN THANH PHAT",
            "so_xe": "50E65375",
            "ten_lai_xe": "LƯƠNG THẾ DUY",
            "sdt": "0888352428",
            "cccd": "040093028954",
            "gplx": "400131030660",
        }
        card = build_vehicle_card(sample_v)
        self.assertIn("AN THANH PHAT", card)
        self.assertIn("50E65375", card)
        self.assertIn("LƯƠNG THẾ DUY", card)
        self.assertIn("0888352428", card)
        self.assertIn("040093028954", card)
        self.assertIn("400131030660", card)

        sample_draft = {
            "vendor": "HOÀNG LONG PHÁT",
            "so_xe": "50E99999",
            "ten_lai_xe": "NGUYỄN VĂN A",
            "sdt": "0901234567",
            "cccd": "079090123456",
            "gplx": "790123456789",
        }
        draft_card = build_add_draft_card(sample_draft)
        self.assertIn("HOÀNG LONG PHÁT", draft_card)
        self.assertIn("50E99999", draft_card)
        self.assertIn("NGUYỄN VĂN A", draft_card)

    def test_mock_sheet_operations(self):
        """Simulate read, update, append, and delete operations on a mock worksheet."""
        initial_rows = [
            ["ĐỘI XE", "SỐ XE", "TÊN LÁI XE", "SĐT", "CCCD", "GPLX"],
            ["AN THANH PHAT", "50E65375", "LƯƠNG THẾ DUY", "0888352428", "040093028954", "400131030660"],
            ["DUY LINH PHAT", "61H13200", "PHẠM NGỌC SÁNG", "0865150567", "042094002527", "740149000715"],
        ]
        sheet = MockWorksheet("DanhSachXe", initial_rows)

        # 1. Verify read
        rows = sheet.get_all_values()
        self.assertEqual(len(rows), 3)

        # 2. Update cell: Row 2, Col 3 (TÊN LÁI XE)
        sheet.update_cell(2, FIELD_MAP["ten_lai_xe"], "LƯƠNG HOÀNG DUY")
        updated_rows = sheet.get_all_values()
        self.assertEqual(updated_rows[1][2], "LƯƠNG HOÀNG DUY")

        # 3. Append new row
        new_row = ["BAO NAM PHAT", "50F09323", "CAO THANH HÀ", "0918959143", "044090013803", "440128001907"]
        sheet.append_row(new_row)
        rows_after_add = sheet.get_all_values()
        self.assertEqual(len(rows_after_add), 4)
        self.assertEqual(rows_after_add[3][1], "50F09323")

        # 4. Delete row 3 (DUY LINH PHAT)
        sheet.delete_rows(3)
        rows_after_del = sheet.get_all_values()
        self.assertEqual(len(rows_after_del), 3)
        self.assertEqual(rows_after_del[2][1], "50F09323")

    def test_find_matching_vendors(self):
        vendors = [
            "AN THANH PHAT",
            "BAO NAM PHAT",
            "DUY LINH PHAT",
            "HOANG LONG PHAT",
            "NHATSON",
            "TRANCO",
            "GIA KHANG",
        ]

        # 1. Exact match uppercase
        v, idx, _ = find_matching_vendors("TRANCO", vendors)
        self.assertEqual(v, "TRANCO")
        self.assertEqual(idx, 5)

        # 2. Case-insensitive lowercase
        v, idx, _ = find_matching_vendors("tranco", vendors)
        self.assertEqual(v, "TRANCO")

        # 3. Space variations: "NHAT SON" vs "NHATSON"
        v, idx, _ = find_matching_vendors("nhat son", vendors)
        self.assertEqual(v, "NHATSON")

        # 4. "giakhang" vs "GIA KHANG"
        v, idx, _ = find_matching_vendors("giakhang", vendors)
        self.assertEqual(v, "GIA KHANG")

        # 5. Substring unique match: "hoang long" -> "HOANG LONG PHAT"
        v, idx, _ = find_matching_vendors("hoang long", vendors)
        self.assertEqual(v, "HOANG LONG PHAT")

        # 6. Multiple matches: "phat"
        v, idx, matches = find_matching_vendors("phat", vendors)
        self.assertIsNone(v)
        self.assertEqual(len(matches), 4)

        # 7. Unmatched
        v, idx, matches = find_matching_vendors("XYZ_NOT_EXIST", vendors)
        self.assertIsNone(v)
        self.assertEqual(len(matches), 0)


if __name__ == "__main__":
    unittest.main()
