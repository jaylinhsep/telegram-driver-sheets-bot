import re
import logging
from typing import List, Dict, Any, Optional, Tuple

try:
    from telegram import (
        Update,
        InlineKeyboardButton,
        InlineKeyboardMarkup,
        ReplyKeyboardMarkup,
        KeyboardButton,
    )
    from telegram.ext import (
        Application,
        CommandHandler,
        MessageHandler,
        CallbackQueryHandler,
        ContextTypes,
        filters,
    )
    TELEGRAM_AVAILABLE = True
except ImportError:
    from typing import Any
    class _Dummy:
        DEFAULT_TYPE = Any
    Update = Any
    InlineKeyboardButton = Any
    InlineKeyboardMarkup = Any
    ReplyKeyboardMarkup = Any
    KeyboardButton = Any
    Application = Any
    CommandHandler = Any
    MessageHandler = Any
    CallbackQueryHandler = Any
    ContextTypes = _Dummy
    filters = Any
    TELEGRAM_AVAILABLE = False

import config
from sheets import sheets_manager, normalize_plate, FIELD_MAP, FIELD_TITLES

logger = logging.getLogger(__name__)

# State keys for context.user_data
STATE_EDITING = "editing"       # {"plate": str, "field": str, "row_index": int}
STATE_ADDING = "adding_draft"   # {"vendor": str, "so_xe": str, "ten_lai_xe": str, "sdt": str, "cccd": str, "gplx": str, "waiting_field": str}


def is_authorized(update: Update) -> bool:
    """Check if the user/chat is authorized to use the bot."""
    if not config.ALLOWED_CHAT_IDS:
        return True
    chat_id = update.effective_chat.id if update.effective_chat else None
    user_id = update.effective_user.id if update.effective_user else None
    return (chat_id in config.ALLOWED_CHAT_IDS) or (user_id in config.ALLOWED_CHAT_IDS)


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Persistent reply keyboard at bottom for quick mobile access."""
    keyboard = [
        [KeyboardButton("🏢 Danh sách Vendor"), KeyboardButton("➕ Thêm xe/Vendor")],
        [KeyboardButton("🔍 Tra cứu số xe"), KeyboardButton("🔄 Đồng bộ dữ liệu")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def build_vehicle_card(v: Dict[str, Any]) -> str:
    """Format vehicle and driver details into a clean markdown card."""
    vendor = v.get("vendor", "") or "(Chưa có)"
    so_xe = v.get("so_xe", "") or "(Chưa có)"
    ten_lai = v.get("ten_lai_xe", "") or "(Chưa cập nhật)"
    sdt = v.get("sdt", "") or "(Chưa cập nhật)"
    cccd = v.get("cccd", "") or "(Chưa cập nhật)"
    gplx = v.get("gplx", "") or "(Chưa cập nhật)"

    card = (
        f"📋 *THÔNG TIN XE & LÁI XE*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏢 *VENDOR:* `{vendor}`\n"
        f"🚗 *SỐ XE:* `{so_xe}`\n"
        f"👤 *TÊN LÁI XE:* `{ten_lai}`\n"
        f"📞 *SỐ ĐIỆN THOẠI:* `{sdt}`\n"
        f"🪪 *CCCD:* `{cccd}`\n"
        f"📄 *GPLX:* `{gplx}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 *Chọn nút tương ứng bên dưới để cập nhật thông tin:*"
    )
    return card


def build_vehicle_action_markup(plate: str, vendor_idx: Optional[int] = None) -> InlineKeyboardMarkup:
    """
    Build update buttons corresponding directly to:
    VENDOR | SỐ XE | TÊN LÁI XE | SỐ ĐIỆN THOẠI | CCCD | GPLX
    """
    norm_p = normalize_plate(plate)
    buttons = [
        [
            InlineKeyboardButton("🏢 VENDOR", callback_data=f"ed:{norm_p}:vendor"),
            InlineKeyboardButton("🚗 SỐ XE", callback_data=f"ed:{norm_p}:so_xe"),
        ],
        [
            InlineKeyboardButton("👤 TÊN LÁI XE", callback_data=f"ed:{norm_p}:ten_lai_xe"),
            InlineKeyboardButton("📞 SỐ ĐIỆN THOẠI", callback_data=f"ed:{norm_p}:sdt"),
        ],
        [
            InlineKeyboardButton("🪪 CCCD", callback_data=f"ed:{norm_p}:cccd"),
            InlineKeyboardButton("📄 GPLX", callback_data=f"ed:{norm_p}:gplx"),
        ],
        [
            InlineKeyboardButton("🗑️ Xoá xe này", callback_data=f"del_cf:{norm_p}"),
            InlineKeyboardButton("🔄 Làm mới", callback_data=f"view:{norm_p}"),
        ],
    ]

    # Back navigation button
    if vendor_idx is not None:
        buttons.append([InlineKeyboardButton("⬅️ Quay lại DS xe của Vendor", callback_data=f"v_s:{vendor_idx}:0")])
    else:
        buttons.append([InlineKeyboardButton("🏢 Về danh sách Vendor", callback_data="v_l:0")])

    return InlineKeyboardMarkup(buttons)


def build_add_draft_card(draft: Dict[str, Any]) -> str:
    """Render draft card when adding a new vehicle/vendor."""
    vendor = draft.get("vendor", "") or "⚠️ *(Chưa có)*"
    so_xe = draft.get("so_xe", "") or "⚠️ *(Bắt buộc)*"
    ten_lai = draft.get("ten_lai_xe", "") or "(Chưa nhập)"
    sdt = draft.get("sdt", "") or "(Chưa nhập)"
    cccd = draft.get("cccd", "") or "(Chưa nhập)"
    gplx = draft.get("gplx", "") or "(Chưa nhập)"

    card = (
        f"➕ *THÊM XE & LÁI XE MỚI*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏢 *VENDOR:* `{vendor}`\n"
        f"🚗 *SỐ XE:* `{so_xe}`\n"
        f"👤 *TÊN LÁI XE:* `{ten_lai}`\n"
        f"📞 *SỐ ĐIỆN THOẠI:* `{sdt}`\n"
        f"🪪 *CCCD:* `{cccd}`\n"
        f"📄 *GPLX:* `{gplx}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👉 *Bấm vào từng nút bên dưới để điền/chỉnh sửa thông tin:*"
    )
    return card


def build_add_draft_markup(draft: Dict[str, Any]) -> InlineKeyboardMarkup:
    """Buttons to edit draft fields and submit to Google Sheets."""
    buttons = [
        [
            InlineKeyboardButton("🏢 Sửa Vendor", callback_data="add_f:vendor"),
            InlineKeyboardButton("🚗 Nhập Số xe (*)", callback_data="add_f:so_xe"),
        ],
        [
            InlineKeyboardButton("👤 Nhập Tên lái xe", callback_data="add_f:ten_lai_xe"),
            InlineKeyboardButton("📞 Nhập SĐT", callback_data="add_f:sdt"),
        ],
        [
            InlineKeyboardButton("🪪 Nhập CCCD", callback_data="add_f:cccd"),
            InlineKeyboardButton("📄 Nhập GPLX", callback_data="add_f:gplx"),
        ],
        [
            InlineKeyboardButton("💾 LƯU VÀO GOOGLE SHEET", callback_data="add_save"),
            InlineKeyboardButton("❌ HỦY", callback_data="add_cancel"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


# -------------------------------------------------------------
# COMMAND HANDLERS
# -------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /start and /help commands."""
    if not is_authorized(update):
        await update.message.reply_text("⛔ Bạn không có quyền sử dụng bot này.")
        return

    # Clear any pending state
    context.user_data.pop(STATE_EDITING, None)
    context.user_data.pop(STATE_ADDING, None)

    welcome_text = (
        "👋 *CHÀO MỪNG BẠN ĐẾN VỚI BOT QUẢN LÝ LÁI XE & VENDOR!*\n\n"
        "Bot được kết nối trực tiếp với Google Sheet dữ liệu lái xe.\n\n"
        "📌 *CÁC TÍNH NĂNG CHÍNH:*\n"
        "• `/vendor` : Xem danh sách vendor, bấm chọn vendor để xem biển số xe, "
        "bấm chọn số xe cụ thể để cập nhật: `VENDOR | SỐ XE | TÊN LÁI XE | SĐT | CCCD | GPLX`\n"
        "• `/add \"VENDOR MỚI\"` : Tạo xe mới cho vendor và bấm nút điền thông tin trực quan\n"
        "• `/<số xe>` (ví dụ `/50E65375`) hoặc gõ trực tiếp `50E65375` : Tra cứu ngay thông tin xe và các nút cập nhật\n"
        "• `/sync` : Đồng bộ làm mới dữ liệu từ Google Sheet\n"
        "• `/cancel` : Hủy thao tác nhập liệu đang thực hiện\n\n"
        "👇 Bấm vào nút bên dưới hoặc gõ lệnh để bắt đầu!"
    )
    await update.message.reply_text(
        welcome_text,
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(),
    )


async def cmd_vendor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /vendor command - displays paginated vendor list."""
    if not is_authorized(update):
        await update.message.reply_text("⛔ Bạn không có quyền sử dụng bot này.")
        return

    # Clear pending states
    context.user_data.pop(STATE_EDITING, None)
    context.user_data.pop(STATE_ADDING, None)

    vendors = await sheets_manager.get_all_vendors()
    if not vendors:
        await update.message.reply_text(
            "⚠️ Chưa có dữ liệu Vendor nào từ Google Sheet hoặc chưa kết nối được.\n"
            "Vui lòng kiểm tra quyền chia sẻ Google Sheet và Service Account."
        )
        return

    markup = build_vendor_list_markup(vendors, page=0)
    text = (
        f"🏢 *DANH SÁCH VENDOR / ĐỘI XE*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"Tổng cộng có *{len(vendors)}* vendor trong hệ thống.\n\n"
        f"👉 *Vui lòng chọn một Vendor để xem danh sách biển số xe:*"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=markup)


def build_vendor_list_markup(vendors: List[str], page: int = 0, page_size: int = 8) -> InlineKeyboardMarkup:
    """Build paginated inline keyboard for vendor list."""
    total_vendors = len(vendors)
    total_pages = max(1, (total_vendors + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))

    start_idx = page * page_size
    end_idx = min(start_idx + page_size, total_vendors)

    buttons = []
    # 2 columns per row
    row = []
    for i in range(start_idx, end_idx):
        v_name = vendors[i]
        # Keep button text reasonable
        label = f"🏢 {v_name}" if len(v_name) <= 22 else f"🏢 {v_name[:20]}…"
        row.append(InlineKeyboardButton(label, callback_data=f"v_s:{i}:0"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Navigation pagination row
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀️ Trước", callback_data=f"v_l:{page - 1}"))
    nav_row.append(InlineKeyboardButton(f"📄 {page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Tiếp ▶️", callback_data=f"v_l:{page + 1}"))
    buttons.append(nav_row)

    # Quick action row
    buttons.append([
        InlineKeyboardButton("➕ Thêm Vendor mới", callback_data="add_prompt_v"),
        InlineKeyboardButton("🔄 Làm mới DS", callback_data="v_l:0"),
    ])

    return InlineKeyboardMarkup(buttons)


def build_vehicle_list_markup(
    vehicles: List[Dict[str, Any]], vendor_name: str, vendor_idx: int, page: int = 0, page_size: int = 10
) -> InlineKeyboardMarkup:
    """Build paginated inline keyboard for vehicles of a vendor."""
    total_veh = len(vehicles)
    total_pages = max(1, (total_veh + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))

    start_idx = page * page_size
    end_idx = min(start_idx + page_size, total_veh)

    buttons = []
    # 2 buttons per row for plate numbers
    row = []
    for i in range(start_idx, end_idx):
        v = vehicles[i]
        plate = v.get("so_xe", "")
        norm_p = normalize_plate(plate)
        driver = v.get("ten_lai_xe", "")
        label = f"🚗 {plate}" if not driver else f"🚗 {plate} ({driver[:10]})"
        row.append(InlineKeyboardButton(label, callback_data=f"view_v:{norm_p}:{vendor_idx}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Pagination navigation
    if total_pages > 1:
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("◀️ Trước", callback_data=f"v_s:{vendor_idx}:{page - 1}"))
        nav_row.append(InlineKeyboardButton(f"📄 {page + 1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton("Tiếp ▶️", callback_data=f"v_s:{vendor_idx}:{page + 1}"))
        buttons.append(nav_row)

    # Actions: Add vehicle to this vendor, or go back to vendor list
    buttons.append([
        InlineKeyboardButton(f"➕ Thêm xe vào {vendor_name[:12]}", callback_data=f"add_v_idx:{vendor_idx}")
    ])
    buttons.append([
        InlineKeyboardButton("⬅️ Quay lại danh sách Vendor", callback_data="v_l:0")
    ])

    return InlineKeyboardMarkup(buttons)


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler for /add command.
    Syntax:
      /add "VENDOR MỚI"
      /add VENDOR MỚI
      /add (without args -> prompts to select or enter vendor)
    """
    if not is_authorized(update):
        await update.message.reply_text("⛔ Bạn không có quyền sử dụng bot này.")
        return

    # Clear pending editing
    context.user_data.pop(STATE_EDITING, None)

    msg_text = update.message.text.strip()
    # Match /add followed by text with or without quotes
    # E.g.: /add "AN THANH PHAT" or /add AN THANH PHAT
    match = re.match(r"^/add(?:\s+[\"']?(.*?)[\"']?)?$", msg_text, re.IGNORECASE)
    vendor_arg = match.group(1).strip() if (match and match.group(1)) else ""

    if not vendor_arg:
        # Prompt user to provide vendor or choose existing
        vendors = await sheets_manager.get_all_vendors()
        text = (
            "➕ *THÊM XE & VENDOR MỚI*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "👉 *Cách 1:* Gõ lệnh kèm tên vendor:\n"
            "`/add \"TÊN VENDOR\"`  (Ví dụ: `/add \"HOÀNG LONG PHÁT\"`)\n\n"
            "👉 *Cách 2:* Bấm chọn một Vendor hiện có bên dưới để thêm xe vào vendor đó:"
        )
        # Show existing vendors
        buttons = []
        row = []
        for i, v_name in enumerate(vendors[:8]):
            row.append(InlineKeyboardButton(f"🏢 {v_name}", callback_data=f"add_v_idx:{i}"))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        buttons.append([InlineKeyboardButton("➕ Nhập tên Vendor mới hoàn toàn", callback_data="add_prompt_v")])

        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        return

    # Start draft with the given vendor
    vendor_clean = vendor_arg.upper()
    draft = {
        "vendor": vendor_clean,
        "so_xe": "",
        "ten_lai_xe": "",
        "sdt": "",
        "cccd": "",
        "gplx": "",
        "waiting_field": "so_xe",  # Default next step
    }
    context.user_data[STATE_ADDING] = draft

    card_text = build_add_draft_card(draft)
    card_text += (
        "\n\n💬 *Bước tiếp theo:* Vui lòng gửi ngay *Biển số xe* vào khung chat "
        "(hoặc bấm các nút bên dưới để điền):"
    )
    markup = build_add_draft_markup(draft)
    await update.message.reply_text(card_text, parse_mode="Markdown", reply_markup=markup)


async def cmd_sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Force sync data from Google Sheets."""
    if not is_authorized(update):
        return
    msg = await update.message.reply_text("🔄 Đang đồng bộ dữ liệu từ Google Sheet, vui lòng đợi giây lát...")
    success, info = await sheets_manager.sync_data(force=True)
    if success:
        await msg.edit_text(f"✅ Đồng bộ thành công!\n📊 {info}")
    else:
        await msg.edit_text(f"❌ Đồng bộ thất bại:\n{info}")


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel any active input/edit operation."""
    had_state = False
    if STATE_EDITING in context.user_data:
        context.user_data.pop(STATE_EDITING)
        had_state = True
    if STATE_ADDING in context.user_data:
        context.user_data.pop(STATE_ADDING)
        had_state = True

    if had_state:
        await update.message.reply_text(
            "❌ Đã hủy bỏ thao tác nhập liệu. Bạn có thể chọn chức năng khác từ menu.",
            reply_markup=get_main_keyboard(),
        )
    else:
        await update.message.reply_text(
            "ℹ️ Hiện không có thao tác nhập liệu nào đang chờ.",
            reply_markup=get_main_keyboard(),
        )


async def cmd_vehicle_or_plate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler for commands like /50E65375, /61H13200, /xe 50E65375, /tim 50E65375
    """
    if not is_authorized(update):
        return

    msg_text = update.message.text.strip()
    # Extract plate: if starts with /xe or /tim, extract following text. Otherwise strip leading slash.
    if msg_text.lower().startswith(("/xe", "/tim")):
        parts = msg_text.split(maxsplit=1)
        plate_candidate = parts[1].strip() if len(parts) > 1 else ""
    elif msg_text.startswith("/"):
        plate_candidate = msg_text[1:].strip()
    else:
        plate_candidate = msg_text.strip()

    await handle_search_plate(update, context, plate_candidate)


async def handle_search_plate(update: Update, context: ContextTypes.DEFAULT_TYPE, plate_query: str):
    """Search for a plate in Google Sheets and display card with update buttons."""
    norm = normalize_plate(plate_query)
    if not norm:
        await update.message.reply_text("⚠️ Vui lòng nhập biển số xe hợp lệ (Ví dụ: `50E65375` hoặc `/50E65375`).", parse_mode="Markdown")
        return

    # Clear pending states
    context.user_data.pop(STATE_EDITING, None)

    record = await sheets_manager.get_vehicle_by_plate(norm)
    if not record:
        buttons = [
            [InlineKeyboardButton(f"➕ Thêm mới xe {norm}", callback_data=f"add_prefilled:{norm}")],
            [InlineKeyboardButton("🏢 Xem danh sách Vendor", callback_data="v_l:0")],
        ]
        await update.message.reply_text(
            f"🔍 *Không tìm thấy* xe có biển số `{plate_query}` trong Google Sheet.\n"
            f"Bạn có muốn thêm mới xe này vào hệ thống không?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    card = build_vehicle_card(record)
    markup = build_vehicle_action_markup(record["so_xe"])
    await update.message.reply_text(card, parse_mode="Markdown", reply_markup=markup)


# -------------------------------------------------------------
# CALLBACK QUERY HANDLER
# -------------------------------------------------------------

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main callback router for inline keyboard interactions."""
    query = update.callback_query
    await query.answer()

    if not is_authorized(update):
        await query.edit_message_text("⛔ Bạn không có quyền sử dụng bot này.")
        return

    data = query.data
    logger.info(f"Callback received: {data}")

    if data == "noop":
        return

    # --- Vendor List Navigation: v_l:<page> ---
    if data.startswith("v_l:"):
        page = int(data.split(":")[1])
        vendors = await sheets_manager.get_all_vendors()
        markup = build_vendor_list_markup(vendors, page=page)
        text = (
            f"🏢 *DANH SÁCH VENDOR / ĐỘI XE*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"Tổng cộng có *{len(vendors)}* vendor trong hệ thống.\n\n"
            f"👉 *Vui lòng chọn một Vendor để xem danh sách biển số xe:*"
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
        return

    # --- Vendor Selection -> List Vehicles: v_s:<vendor_idx>:<page> ---
    if data.startswith("v_s:"):
        parts = data.split(":")
        v_idx = int(parts[1])
        page = int(parts[2]) if len(parts) > 2 else 0

        vendors = await sheets_manager.get_all_vendors()
        if v_idx < 0 or v_idx >= len(vendors):
            await query.edit_message_text("⚠️ Không tìm thấy Vendor tương ứng. Vui lòng thử lại từ /vendor.")
            return

        v_name = vendors[v_idx]
        vehicles = await sheets_manager.get_vehicles_by_vendor(v_name)

        if not vehicles:
            buttons = [
                [InlineKeyboardButton(f"➕ Thêm xe vào {v_name}", callback_data=f"add_v_idx:{v_idx}")],
                [InlineKeyboardButton("⬅️ Quay lại danh sách Vendor", callback_data="v_l:0")],
            ]
            await query.edit_message_text(
                f"🏢 *VENDOR: {v_name}*\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"Hiện chưa có xe nào thuộc Vendor này.\n"
                f"Bạn có thể bấm nút bên dưới để thêm xe mới:",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
            return

        markup = build_vehicle_list_markup(vehicles, v_name, v_idx, page=page)
        text = (
            f"🏢 *VENDOR: {v_name}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Tổng số: *{len(vehicles)}* xe\n\n"
            f"👉 *Bấm vào biển số xe để xem chi tiết và cập nhật:*"
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
        return

    # --- View Vehicle Details: view:<plate> or view_v:<plate>:<vendor_idx> ---
    if data.startswith(("view:", "view_v:")):
        parts = data.split(":")
        plate = parts[1]
        v_idx = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None

        record = await sheets_manager.get_vehicle_by_plate(plate)
        if not record:
            await query.edit_message_text(f"⚠️ Không tìm thấy xe `{plate}` trên hệ thống.", parse_mode="Markdown")
            return

        card = build_vehicle_card(record)
        markup = build_vehicle_action_markup(record["so_xe"], vendor_idx=v_idx)
        await query.edit_message_text(card, parse_mode="Markdown", reply_markup=markup)
        return

    # --- Edit a Specific Field: ed:<plate>:<field_code> ---
    # Triggered when user clicks VENDOR | SỐ XE | TÊN LÁI XE | SĐT | CCCD | GPLX
    if data.startswith("ed:"):
        parts = data.split(":")
        plate = parts[1]
        field_code = parts[2]

        record = await sheets_manager.get_vehicle_by_plate(plate)
        if not record:
            await query.edit_message_text(f"⚠️ Không tìm thấy thông tin xe `{plate}` để chỉnh sửa.")
            return

        # Store editing state in user_data
        context.user_data[STATE_EDITING] = {
            "plate": plate,
            "field": field_code,
            "row_index": record["row_index"],
        }

        field_title = FIELD_TITLES.get(field_code, field_code)
        current_val = record.get(field_code, "") or "(Chưa có)"

        text = (
            f"✏️ *CẬP NHẬT: {field_title.upper()}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🚗 Xe: `{record['so_xe']}`\n"
            f"📝 Giá trị hiện tại: `{current_val}`\n\n"
            f"👉 *Vui lòng gửi giá trị mới vào khung chat:*\n"
            f"_(Hoặc bấm Hủy bên dưới để quay lại)_"
        )
        cancel_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Hủy bỏ chỉnh sửa", callback_data=f"ed_cancel:{plate}")]
        ])
        await query.message.reply_text(text, parse_mode="Markdown", reply_markup=cancel_markup)
        return

    # --- Cancel Edit: ed_cancel:<plate> ---
    if data.startswith("ed_cancel:"):
        plate = data.split(":")[1]
        context.user_data.pop(STATE_EDITING, None)
        record = await sheets_manager.get_vehicle_by_plate(plate)
        if record:
            card = build_vehicle_card(record)
            markup = build_vehicle_action_markup(record["so_xe"])
            await query.message.reply_text("❌ Đã hủy chỉnh sửa.", reply_markup=markup)
        else:
            await query.message.reply_text("❌ Đã hủy chỉnh sửa.", reply_markup=get_main_keyboard())
        return

    # --- Delete Confirmation: del_cf:<plate> ---
    if data.startswith("del_cf:"):
        plate = data.split(":")[1]
        record = await sheets_manager.get_vehicle_by_plate(plate)
        if not record:
            await query.edit_message_text(f"⚠️ Không tìm thấy xe `{plate}`.")
            return

        buttons = [
            [
                InlineKeyboardButton("⚠️ Xác nhận XOÁ vĩnh viễn", callback_data=f"del_do:{plate}"),
                InlineKeyboardButton("❌ Không xoá (Quay lại)", callback_data=f"view:{plate}"),
            ]
        ]
        await query.edit_message_text(
            f"⚠️ *XÁC NHẬN XOÁ THÔNG TIN XE*\n\n"
            f"Bạn có chắc chắn muốn xoá xe `{record['so_xe']}` (Lái xe: `{record.get('ten_lai_xe', '')}`) "
            f"khỏi Google Sheet không?\n\n*Hành động này không thể hoàn tác!*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    # --- Execute Delete: del_do:<plate> ---
    if data.startswith("del_do:"):
        plate = data.split(":")[1]
        record = await sheets_manager.get_vehicle_by_plate(plate)
        if not record:
            await query.edit_message_text(f"⚠️ Không tìm thấy xe `{plate}` để xoá.")
            return

        row_idx = record["row_index"]
        success, msg = await sheets_manager.delete_vehicle(row_idx)
        if success:
            await query.edit_message_text(
                f"🗑️ *Đã xoá xe `{plate}` thành công khỏi Google Sheet!*",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏢 Xem danh sách Vendor", callback_data="v_l:0")]
                ]),
            )
        else:
            await query.edit_message_text(f"❌ Xoá thất bại: {msg}")
        return

    # --- Add Flow: add_v_idx:<vendor_idx> ---
    if data.startswith("add_v_idx:"):
        v_idx = int(data.split(":")[1])
        vendors = await sheets_manager.get_all_vendors()
        if 0 <= v_idx < len(vendors):
            vendor_name = vendors[v_idx]
        else:
            vendor_name = "VENDOR MỚI"

        draft = {
            "vendor": vendor_name,
            "so_xe": "",
            "ten_lai_xe": "",
            "sdt": "",
            "cccd": "",
            "gplx": "",
            "waiting_field": "so_xe",
        }
        context.user_data[STATE_ADDING] = draft
        card = build_add_draft_card(draft)
        card += (
            f"\n\n💬 *Bước tiếp theo:* Vui lòng gửi *Biển số xe* vào chat "
            f"(hoặc bấm các nút bên dưới để điền):"
        )
        markup = build_add_draft_markup(draft)
        await query.message.reply_text(card, parse_mode="Markdown", reply_markup=markup)
        return

    # --- Add Flow: add_prompt_v ---
    if data == "add_prompt_v":
        draft = {
            "vendor": "",
            "so_xe": "",
            "ten_lai_xe": "",
            "sdt": "",
            "cccd": "",
            "gplx": "",
            "waiting_field": "vendor",
        }
        context.user_data[STATE_ADDING] = draft
        await query.message.reply_text(
            "🏢 *Vui lòng gửi TÊN VENDOR mới vào khung chat:*\n(Ví dụ: `VẬN TẢI AN PHÁT`)",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Hủy", callback_data="add_cancel")]
            ]),
        )
        return

    # --- Add Flow: add_prefilled:<plate> ---
    if data.startswith("add_prefilled:"):
        plate = data.split(":")[1]
        draft = {
            "vendor": "",
            "so_xe": plate,
            "ten_lai_xe": "",
            "sdt": "",
            "cccd": "",
            "gplx": "",
            "waiting_field": "vendor",
        }
        context.user_data[STATE_ADDING] = draft
        card = build_add_draft_card(draft)
        card += "\n\n💬 *Vui lòng gửi TÊN VENDOR cho xe này vào khung chat:*"
        markup = build_add_draft_markup(draft)
        await query.message.reply_text(card, parse_mode="Markdown", reply_markup=markup)
        return

    # --- Add Flow: add_f:<field_code> ---
    if data.startswith("add_f:"):
        field_code = data.split(":")[1]
        draft = context.user_data.get(STATE_ADDING, {})
        draft["waiting_field"] = field_code
        context.user_data[STATE_ADDING] = draft

        field_title = FIELD_TITLES.get(field_code, field_code)
        await query.message.reply_text(
            f"👉 *Vui lòng gửi giá trị cho '{field_title}' vào khung chat:*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Hủy", callback_data="add_cancel")]
            ]),
        )
        return

    # --- Add Flow: add_cancel ---
    if data == "add_cancel":
        context.user_data.pop(STATE_ADDING, None)
        await query.edit_message_text(
            "❌ Đã hủy thao tác thêm xe mới.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏢 Xem danh sách Vendor", callback_data="v_l:0")]
            ]),
        )
        return

    # --- Add Flow: add_save ---
    if data == "add_save":
        draft = context.user_data.get(STATE_ADDING)
        if not draft:
            await query.edit_message_text("⚠️ Không tìm thấy bản nháp đang tạo. Vui lòng thử lại với /add.")
            return

        vendor = draft.get("vendor", "").strip()
        so_xe = draft.get("so_xe", "").strip()

        if not vendor:
            await query.message.reply_text("⚠️ Bạn chưa điền *Tên Vendor*! Vui lòng bấm 'Sửa Vendor' để nhập.", parse_mode="Markdown")
            return
        if not so_xe:
            await query.message.reply_text("⚠️ Bạn chưa điền *Số xe (Biển số)*! Vui lòng bấm 'Nhập Số xe' để nhập.", parse_mode="Markdown")
            return

        # Check if plate already exists in Google Sheet
        existing = await sheets_manager.get_vehicle_by_plate(so_xe)
        if existing:
            await query.message.reply_text(
                f"⚠️ *Cảnh báo:* Biển số xe `{so_xe}` đã tồn tại trong Google Sheet thuộc Vendor `{existing.get('vendor')}`!\n"
                f"Nếu muốn cập nhật thông tin, bạn có thể tra cứu bằng lệnh `/{so_xe}`.",
                parse_mode="Markdown",
            )
            return

        # Save to Google Sheets
        await query.message.reply_text("⏳ Đang lưu dữ liệu vào Google Sheet...")
        success, msg, new_record = await sheets_manager.add_vehicle(
            vendor=vendor,
            so_xe=so_xe,
            ten_lai_xe=draft.get("ten_lai_xe", ""),
            sdt=draft.get("sdt", ""),
            cccd=draft.get("cccd", ""),
            gplx=draft.get("gplx", ""),
        )

        if success and new_record:
            context.user_data.pop(STATE_ADDING, None)
            card = (
                f"🎉 *ĐÃ LƯU THÀNH CÔNG VÀO GOOGLE SHEET!*\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"🏢 *VENDOR:* `{new_record['vendor']}`\n"
                f"🚗 *SỐ XE:* `{new_record['so_xe']}`\n"
                f"👤 *TÊN LÁI XE:* `{new_record['ten_lai_xe'] or '(Trống)'}`\n"
                f"📞 *SĐT:* `{new_record['sdt'] or '(Trống)'}`\n"
                f"🪪 *CCCD:* `{new_record['cccd'] or '(Trống)'}`\n"
                f"📄 *GPLX:* `{new_record['gplx'] or '(Trống)'}`\n"
                f"━━━━━━━━━━━━━━━━━━━━━"
            )
            action_buttons = [
                [InlineKeyboardButton(f"🚗 Xem chi tiết xe {so_xe}", callback_data=f"view:{so_xe}")],
                [InlineKeyboardButton(f"➕ Thêm xe khác cho {vendor}", callback_data="add_prompt_v")],
                [InlineKeyboardButton("🏢 Về danh sách Vendor", callback_data="v_l:0")],
            ]
            await query.message.reply_text(card, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(action_buttons))
        else:
            await query.message.reply_text(f"❌ Lưu thất bại: {msg}")
        return


# -------------------------------------------------------------
# TEXT MESSAGE HANDLER
# -------------------------------------------------------------

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles text messages:
    1. Reply keyboard clicks ('🏢 Danh sách Vendor', etc.)
    2. Active editing state: saves updated field to Google Sheets
    3. Active adding draft state: updates field in draft
    4. License plate lookups: e.g. '50E65375', '61H13200'
    """
    if not is_authorized(update):
        return

    text = update.message.text.strip()

    # --- 1. Reply Keyboard quick actions ---
    if text == "🏢 Danh sách Vendor":
        await cmd_vendor(update, context)
        return
    if text == "➕ Thêm xe/Vendor":
        await cmd_add(update, context)
        return
    if text == "🔍 Tra cứu số xe":
        await update.message.reply_text(
            "🔍 *TRA CỨU XE:*\n"
            "Vui lòng gửi Biển số xe cần tìm (Ví dụ: `50E65375` hoặc `/50E65375`):",
            parse_mode="Markdown",
        )
        return
    if text == "🔄 Đồng bộ dữ liệu":
        await cmd_sync(update, context)
        return

    # --- 2. Active Editing State ---
    if STATE_EDITING in context.user_data:
        edit_info = context.user_data[STATE_EDITING]
        plate = edit_info["plate"]
        field_code = edit_info["field"]
        row_idx = edit_info["row_index"]

        await update.message.reply_text("⏳ Đang cập nhật vào Google Sheet...")
        success, msg = await sheets_manager.update_vehicle_field(row_idx, field_code, text)

        # Clear editing state
        context.user_data.pop(STATE_EDITING, None)

        if success:
            record = await sheets_manager.get_vehicle_by_plate(plate if field_code != "so_xe" else text)
            card = build_vehicle_card(record) if record else ""
            markup = build_vehicle_action_markup(record["so_xe"]) if record else get_main_keyboard()
            await update.message.reply_text(f"{msg}\n\n{card}", parse_mode="Markdown", reply_markup=markup)
        else:
            await update.message.reply_text(f"❌ {msg}\nVui lòng thử lại hoặc gửi /cancel.")
        return

    # --- 3. Active Adding Draft State ---
    if STATE_ADDING in context.user_data:
        draft = context.user_data[STATE_ADDING]
        waiting_field = draft.get("waiting_field", "so_xe")

        if waiting_field == "vendor":
            draft["vendor"] = text.upper()
            # If so_xe is not yet entered, prompt for so_xe next
            if not draft.get("so_xe"):
                draft["waiting_field"] = "so_xe"
            else:
                draft["waiting_field"] = ""
        elif waiting_field == "so_xe":
            draft["so_xe"] = text.upper()
            draft["waiting_field"] = "ten_lai_xe"
        elif waiting_field == "ten_lai_xe":
            draft["ten_lai_xe"] = text.upper()
            draft["waiting_field"] = "sdt"
        elif waiting_field == "sdt":
            draft["sdt"] = text
            draft["waiting_field"] = "cccd"
        elif waiting_field == "cccd":
            draft["cccd"] = text
            draft["waiting_field"] = "gplx"
        elif waiting_field == "gplx":
            draft["gplx"] = text
            draft["waiting_field"] = ""
        else:
            # Default assign to so_xe if empty
            if not draft.get("so_xe"):
                draft["so_xe"] = text.upper()
            else:
                draft["ten_lai_xe"] = text.upper()

        context.user_data[STATE_ADDING] = draft
        card = build_add_draft_card(draft)
        next_hint = ""
        if draft.get("waiting_field"):
            title = FIELD_TITLES.get(draft["waiting_field"], draft["waiting_field"])
            next_hint = f"\n\n💬 *Gợi ý tiếp theo:* Gửi ngay `{title}` hoặc bấm nút bên dưới:"
        card += next_hint

        markup = build_add_draft_markup(draft)
        await update.message.reply_text(card, parse_mode="Markdown", reply_markup=markup)
        return

    # --- 4. Search Plate Lookup ---
    # Check if text looks like a vehicle plate (e.g. 50E65375, 50E-653.75, 61H13200, 51C 71417)
    norm = normalize_plate(text)
    if re.match(r"^\d{2}[A-Z0-9]{4,8}$", norm, re.IGNORECASE):
        await handle_search_plate(update, context, text)
        return

    # If unmatched text
    await update.message.reply_text(
        f"❓ Bot chưa nhận diện được yêu cầu: `{text}`\n\n"
        "• Gõ `/vendor` để xem danh sách Vendor\n"
        "• Gõ `/add \"TÊN VENDOR\"` để thêm xe mới\n"
        "• Gõ biển số xe (Ví dụ: `50E65375` hoặc `/50E65375`) để tra cứu & cập nhật",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(),
    )


def register_handlers(app: Application):
    """Register all command and message handlers with python-telegram-bot Application."""
    app.add_handler(CommandHandler(["start", "help"], cmd_start))
    app.add_handler(CommandHandler("vendor", cmd_vendor))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler(["sync", "refresh"], cmd_sync))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CommandHandler(["xe", "tim"], cmd_vehicle_or_plate))

    # Pattern for direct plate commands like /50E65375 or /61H13200
    # Telegram commands match letters, digits and underscores
    app.add_handler(
        MessageHandler(
            filters.COMMAND & filters.Regex(r"^/\d{2}[a-zA-Z0-9_]+$"),
            cmd_vehicle_or_plate,
        )
    )

    # Callback Query Handler
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    # Text message handler (exclude commands)
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message)
    )
