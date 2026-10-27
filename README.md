# 🚛 TELEGRAM BOT QUẢN LÝ LÁI XE & VENDOR (GOOGLE SHEETS)

Bot Telegram kết nối trực tiếp với file Google Sheet quản lý thông tin lái xe và các vendor vận tải:
- **Link Google Sheet:** [Google Sheets Driver Data](https://docs.google.com/spreadsheets/d/13ndQsSmBsKlHjIRQR0S0MO5BPqqL6J4CECBAYfQi1oo/edit?gid=1046738475#gid=1046738475)
- **Tab dữ liệu chính:** `DanhSachXe` (gid: `1046738475`)
- **Tab danh sách Vendor:** `VENDOR` (gid: `331541216`)

---

## 🌟 CÁC TÍNH NĂNG CHÍNH

### 1. `/vendor` — Xem danh sách Vendor & Biển số xe
- Hiển thị danh sách tất cả các Vendor dưới dạng nút bấm phân trang trực quan.
- **Bấm chọn một Vendor cụ thể:** Bot hiển thị danh sách tất cả các biển số xe thuộc Vendor đó.
- **Bấm chọn biển số xe cụ thể:** Bot hiển thị thẻ thông tin chi tiết xe & lái xe kèm 6 nút cập nhật:
  - `[ 🏢 VENDOR ]`
  - `[ 🚗 SỐ XE ]`
  - `[ 👤 TÊN LÁI XE ]`
  - `[ 📞 SỐ ĐIỆN THOẠI ]`
  - `[ 🪪 CCCD ]`
  - `[ 📄 GPLX ]`
- Khi bấm vào nút bất kỳ, bot sẽ yêu cầu nhập giá trị mới trong chat và tự động cập nhật ngay lập tức vào ô tương ứng trên Google Sheet!

### 2. `/add "VENDOR MỚI"` — Thêm Vendor & Xe mới
- Cú pháp: `/add "TÊN VENDOR"` hoặc `/add TÊN VENDOR` (Ví dụ: `/add "TÂN TIẾN PHÁT"`).
- Nếu chỉ gõ `/add`: Bot sẽ gợi ý chọn Vendor có sẵn hoặc bấm nút nhập Vendor mới.
- Bot hiển thị form trực quan kèm các nút:
  - `[ 🚗 Nhập Số xe (*) ]`
  - `[ 👤 Nhập Tên lái xe ]`
  - `[ 📞 Nhập SĐT ]`
  - `[ 🪪 Nhập CCCD ]`
  - `[ 📄 Nhập GPLX ]`
  - `[ 💾 LƯU VÀO GOOGLE SHEET ]`
  - `[ ❌ HỦY ]`
- Khi bấm **LƯU VÀO GOOGLE SHEET**, bot sẽ kiểm tra tính hợp lệ, tự động thêm dòng mới vào tab `DanhSachXe` và cập nhật tab `VENDOR`.

### 3. `/<số xe cụ thể>` hoặc nhập trực tiếp Biển số xe — Tra cứu & Cập nhật nhanh
- Gõ lệnh với biển số: `/50E65375`, `/61H13200`
- Hoặc gõ trực tiếp biển số: `50E65375`, `50E-653.75`, `61H 13200`
- Hoặc gõ lệnh: `/xe 50E65375` hoặc `/tim 50E65375`
- Bot tự động chuẩn hóa biển số, tìm trong Google Sheet và hiển thị thẻ thông tin xe cùng đầy đủ các nút cập nhật.
- Nếu xe chưa có, bot cung cấp ngay nút `[ ➕ Thêm mới xe này ]` để tạo nhanh.

### 4. `/sync` — Đồng bộ dữ liệu
- Làm mới bộ nhớ đệm (cache) và đồng bộ dữ liệu mới nhất từ Google Sheet.

---

## 🏗️ CẤU TRÚC DỰ ÁN

```
telegram-driver-sheets-bot/
├── app.py                  # Web server FastAPI + Lifespan quản lý Bot Telegram
├── bot.py                  # Toàn bộ logic xử lý lệnh, menu nút bấm & nhập liệu
├── config.py               # Quản lý biến môi trường và nạp Service Account
├── sheets.py               # Quản lý đọc/ghi Google Sheet qua gspread & caching
├── test_sheets_mock.py     # Bộ kiểm thử tự động (Unit Tests)
├── requirements.txt        # Thư viện Python cần thiết
├── render.yaml             # Blueprint triển khai 1-click lên Render.com
├── Procfile                # Start command cho nền tảng PaaS
├── .env.example            # File mẫu cấu hình biến môi trường
├── .gitignore              # Loại bỏ file nhạy cảm và rác khỏi Git
└── README.md               # Hướng dẫn chi tiết
```

---

## 🔑 HƯỚNG DẪN CẤU HÌNH CHI TIẾT (TỪNG BƯỚC)

### BƯỚC 1: TẠO BOT TELEGRAM & LẤY TOKEN
1. Mở ứng dụng Telegram, tìm bot **`@BotFather`**.
2. Gửi lệnh `/newbot`.
3. Đặt tên hiển thị cho bot (Ví dụ: `Driver Vendor Bot`).
4. Đặt username kết thúc bằng `bot` (Ví dụ: `vsho_driver_sheet_bot`).
5. `@BotFather` sẽ gửi cho bạn **HTTP API Token** có dạng:
   `7123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`
   *(Lưu lại token này để dùng ở Bước 4)*.

---

### BƯỚC 2: TẠO GOOGLE SERVICE ACCOUNT & CẤP QUYỀN CHO SHEET
Để bot có thể đọc và ghi dữ liệu vào Google Sheet tự động, bạn cần 1 tài khoản Service Account miễn phí từ Google:

1. Truy cập [Google Cloud Console](https://console.cloud.google.com/).
2. Tạo một Project mới (hoặc chọn Project sẵn có).
3. Vào **APIs & Services** > **Library**:
   - Tìm kiếm `Google Sheets API` -> Bấm **Enable**.
   - Tìm kiếm `Google Drive API` -> Bấm **Enable**.
4. Vào **APIs & Services** > **Credentials**:
   - Bấm **Create Credentials** -> Chọn **Service Account**.
   - Đặt tên (ví dụ: `driver-sheets-bot`) -> Bấm **Create and Continue** -> Bấm **Done**.
5. Nhấp vào Service Account vừa tạo:
   - Chuyển sang tab **Keys** -> Bấm **Add Key** -> **Create new key**.
   - Chọn định dạng **JSON** -> Bấm **Create**.
   - Một file `.json` sẽ tự động tải về máy tính của bạn.
6. **QUAN TRỌNG NHẤT - CẤP QUYỀN CHO GOOGLE SHEET:**
   - Mở file `.json` vừa tải về, copy địa chỉ email trong trường `"client_email"` (có dạng: `driver-sheets-bot@xxxxxx.iam.gserviceaccount.com`).
   - Mở file Google Sheet của bạn: [Google Sheets Link](https://docs.google.com/spreadsheets/d/13ndQsSmBsKlHjIRQR0S0MO5BPqqL6J4CECBAYfQi1oo/edit?gid=1046738475#gid=1046738475)
   - Bấm nút **Chia sẻ (Share)** ở góc trên bên phải.
   - Dán email của Service Account vào, chọn quyền **Người chỉnh sửa (Editor)**, bỏ tick thông báo rồi bấm **Chia sẻ (Share)**.

---

### BƯỚC 3: ĐƯA DỰ ÁN LÊN GITHUB
1. Cài đặt [Git](https://git-scm.com/) nếu máy chưa có.
2. Mở Terminal / PowerShell tại thư mục này:
   ```bash
   cd "C:\Users\VSHO Trucking14\.gemini\antigravity\scratch\telegram-driver-sheets-bot"
   ```
3. Khởi tạo Git và commit code:
   ```bash
   git init
   git add .
   git commit -m "Khoi tao Telegram Bot quan ly lai xe va vendor Google Sheets"
   ```
4. Lên [GitHub](https://github.com/), tạo một Repository mới (ví dụ đặt tên: `telegram-driver-sheets-bot`, để chế độ **Private** hoặc **Public** tùy bạn).
5. Liên kết và đẩy code lên:
   ```bash
   git remote add origin https://github.com/<tai-khoan-cua-ban>/telegram-driver-sheets-bot.git
   git branch -M main
   git push -u origin main
   ```

---

### BƯỚC 4: LIÊN KẾT & TRIỂN KHAI LÊN RENDER.COM

Dự án đã có sẵn file `render.yaml`, bạn có thể triển khai tự động hoặc thủ công chỉ trong 2 phút:

#### Cách 1: Triển khai nhanh qua Web Service trên Render
1. Đăng nhập vào [Render.com](https://render.com/).
2. Bấm **New +** ở góc trên -> Chọn **Web Service**.
3. Chọn Repository GitHub vừa tạo (`telegram-driver-sheets-bot`).
4. Điền các thông số cơ bản:
   - **Name:** `telegram-driver-sheets-bot`
   - **Region:** `Singapore` (để tốc độ về Việt Nam nhanh nhất)
   - **Environment:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app:web_app --host 0.0.0.0 --port $PORT`
   - **Instance Type:** `Free`
5. Kéo xuống mục **Environment Variables** (Biến môi trường) và thêm các biến sau:
   - `TELEGRAM_BOT_TOKEN`: Dán mã token bot từ BotFather.
   - `GOOGLE_SHEET_ID`: `13ndQsSmBsKlHjIRQR0S0MO5BPqqL6J4CECBAYfQi1oo`
   - `GOOGLE_SHEET_TAB_DATA`: `DanhSachXe`
   - `GOOGLE_SHEET_TAB_VENDOR`: `VENDOR`
   - `GOOGLE_SERVICE_ACCOUNT_JSON`: Mở file `.json` tải ở Bước 2, copy **TOÀN BỘ NỘI DUNG FILE JSON** và dán vào giá trị biến này.
   - `ALLOWED_CHAT_IDS`: *(Tùy chọn)* ID tài khoản Telegram của bạn nếu muốn chặn người lạ dùng bot.
6. Bấm **Deploy Web Service**.

> **💡 Lưu ý về Render Free Tier:**
> Dự án được tích hợp sẵn máy chủ web FastAPI đáp ứng cổng `$PORT` và endpoint `/` cũng như `/health` của Render. Khi chạy trên Render Web Service, bot tự động nhận diện URL Render và đăng ký Webhook với Telegram, giúp bot chạy mượt mà, phản hồi ngay lập tức mà không tốn tài nguyên polling!

---

## 💻 CHẠY THỬ NGHIỆM TẠI MÁY LOCAL (NẾU CẦN)

1. Tạo môi trường ảo và cài đặt thư viện:
   ```bash
   python -m venv venv
   # Trên Windows:
   venv\Scripts\activate
   # Trên Linux/Mac:
   source venv/bin/activate

   pip install -r requirements.txt
   ```
2. Đổi tên file `.env.example` thành `.env`, điền Token và Service Account JSON. Hoặc sao chép file `.json` của Service Account vào thư mục dự án và đặt tên là `service_account.json`.
3. Chạy bot:
   ```bash
   python app.py
   ```
4. Mở Telegram và nhắn `/start` với bot của bạn để bắt đầu sử dụng!
