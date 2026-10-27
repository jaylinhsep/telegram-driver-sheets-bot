/**
 * GOOGLE APPS SCRIPT CHO TELEGRAM DRIVER BOT
 * -------------------------------------------------------------
 * Hướng dẫn cài đặt (Chỉ mất 1 phút, KHÔNG CẦN TẠO CREDENTIALS GOOGLE CLOUD):
 * 1. Mở file Google Sheet của bạn.
 * 2. Vào menu: Tiện ích mở rộng (Extensions) > Apps Script.
 * 3. Xóa hết mã cũ trong file Mã.gs (Code.gs), dán toàn bộ đoạn mã này vào.
 * 4. Bấm nút Lưu (Save - icon đĩa mềm).
 * 5. Bấm nút "Triển khai" (Deploy) ở góc trên bên phải > "Quản lý bản triển khai mới" (New deployment).
 * 6. Bấm vào biểu tượng bánh răng (Cài đặt) > Chọn loại "Ứng dụng web" (Web app).
 * 7. Cấu hình:
 *    - Mô tả: Telegram Driver Sheets Webhook
 *    - Thực thi dưới dạng (Execute as): "Tôi" (Me)
 *    - Ai có quyền truy cập (Who has access): "Bất kỳ ai" (Anyone)   <-- Cực kỳ quan trọng!
 * 8. Bấm "Triển khai" (Deploy) > Cấp quyền (Authorize access) bằng tài khoản Google của bạn.
 * 9. Copy đường link "URL của ứng dụng web" (có đuôi /exec).
 * 10. Dán link này vào biến môi trường `GOOGLE_APPS_SCRIPT_URL` trên Render.com!
 */

function doGet(e) {
  var action = (e && e.parameter && e.parameter.action) ? e.parameter.action : "read";
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheetData = ss.getSheetByName("DanhSachXe") || ss.getSheets()[0];
  var sheetVendor = ss.getSheetByName("VENDOR");

  if (action === "read") {
    var rows = sheetData.getDataRange().getValues();
    var vendors = [];
    if (sheetVendor) {
      var vRows = sheetVendor.getDataRange().getValues();
      for (var i = 1; i < vRows.length; i++) {
        if (vRows[i][0]) {
          vendors.push(vRows[i][0].toString().trim());
        }
      }
    }
    return ContentService.createTextOutput(JSON.stringify({
      status: "success",
      rows: rows,
      vendors: vendors
    })).setMimeType(ContentService.MimeType.JSON);
  }

  return ContentService.createTextOutput(JSON.stringify({
    status: "success",
    message: "Google Apps Script Driver Bot is ready!"
  })).setMimeType(ContentService.MimeType.JSON);
}

function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);
    var action = data.action;
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sheetData = ss.getSheetByName("DanhSachXe") || ss.getSheets()[0];
    var sheetVendor = ss.getSheetByName("VENDOR");

    // 1. Cập nhật một ô cụ thể: {action: "update_cell", row: 2, col: 3, value: "NGUYỄN VĂN A"}
    if (action === "update_cell") {
      var row = parseInt(data.row, 10);
      var col = parseInt(data.col, 10);
      sheetData.getRange(row, col).setValue(data.value);
      return ContentService.createTextOutput(JSON.stringify({
        status: "success",
        updated_row: row,
        updated_col: col
      })).setMimeType(ContentService.MimeType.JSON);
    }

    // 2. Thêm dòng mới: {action: "append_row", row_data: ["AN THANH PHAT", "50E12345", "TÊN", "SĐT", "CCCD", "GPLX"]}
    if (action === "append_row") {
      sheetData.appendRow(data.row_data);

      // Đồng bộ vào tab VENDOR nếu chưa có
      if (sheetVendor && data.row_data && data.row_data[0]) {
        var vName = data.row_data[0].toString().trim().toUpperCase();
        var vList = sheetVendor.getDataRange().getValues().map(function(r) {
          return r[0] ? r[0].toString().trim().toUpperCase() : "";
        });
        if (vList.indexOf(vName) === -1) {
          sheetVendor.appendRow([vName]);
        }
      }

      return ContentService.createTextOutput(JSON.stringify({
        status: "success"
      })).setMimeType(ContentService.MimeType.JSON);
    }

    // 3. Xóa một dòng: {action: "delete_row", row: 5}
    if (action === "delete_row") {
      var delRow = parseInt(data.row, 10);
      sheetData.deleteRow(delRow);
      return ContentService.createTextOutput(JSON.stringify({
        status: "success"
      })).setMimeType(ContentService.MimeType.JSON);
    }

    return ContentService.createTextOutput(JSON.stringify({
      status: "error",
      message: "Unknown action: " + action
    })).setMimeType(ContentService.MimeType.JSON);

  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({
      status: "error",
      message: err.toString()
    })).setMimeType(ContentService.MimeType.JSON);
  }
}
