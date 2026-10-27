import os
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application

import config
from sheets import sheets_manager
from bot import register_handlers

# Setup logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("driver_sheets_bot")

tg_app: Optional[Application] = None


async def background_sync_worker():
    """Silently refreshes cache in background so user requests never block."""
    while True:
        try:
            await asyncio.sleep(300)  # Refresh every 5 minutes
            logger.info("🔄 [Background Worker] Đang đồng bộ ngầm dữ liệu Google Sheet...")
            await sheets_manager.sync_data(force=True)
            logger.info("✅ [Background Worker] Đồng bộ ngầm hoàn tất!")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"⚠️ [Background Worker] Lỗi đồng bộ ngầm: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager:
    1. Connects to Google Sheets & pre-loads cache
    2. Initializes Telegram Application
    3. Configures Webhook or Polling mode
    4. Starts background sync worker
    5. Handles graceful shutdown
    """
    global tg_app
    logger.info("🚀 Đang khởi động Telegram Driver Sheets Bot...")

    # 1. Connect and sync Google Sheets
    try:
        success, msg = await sheets_manager.sync_data(force=True)
        if success:
            logger.info(f"✅ Google Sheets: {msg}")
        else:
            logger.warning(f"⚠️ Google Sheets chưa sẵn sàng: {msg}")
    except Exception as e:
        logger.error(f"Lỗi khởi tạo Google Sheets: {e}", exc_info=True)

    # 2. Start background worker for silent periodic sync
    sync_task = asyncio.create_task(background_sync_worker())

    # 3. Initialize Telegram bot if token is configured
    if config.TELEGRAM_BOT_TOKEN:
        try:
            tg_app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
            register_handlers(tg_app)
            await tg_app.initialize()
            await tg_app.start()

            # Determine Webhook vs Polling
            base_url = config.WEBHOOK_URL or config.RENDER_EXTERNAL_URL
            if base_url:
                base_url = base_url.rstrip("/")
                webhook_target = f"{base_url}/webhook"
                logger.info(f"🌐 Đang thiết lập Telegram Webhook tới: {webhook_target}")
                await tg_app.bot.set_webhook(
                    url=webhook_target,
                    allowed_updates=Update.ALL_TYPES,
                    drop_pending_updates=True,
                )
                logger.info("✅ Telegram Webhook đã sẵn sàng!")
            else:
                logger.info("📡 Không có WEBHOOK_URL. Đang chạy ở chế độ Polling trong nền...")
                try:
                    await tg_app.bot.delete_webhook(drop_pending_updates=True)
                except Exception as e_del:
                    logger.warning(f"Lỗi xóa webhook cũ: {e_del}")

                if tg_app.updater:
                    await tg_app.updater.start_polling()
                    logger.info("🎉 Bot đang nhận tin nhắn qua Polling 24/7!")

        except Exception as e:
            logger.error(f"❌ Lỗi khởi động Telegram Application: {e}", exc_info=True)
    else:
        logger.warning(
            "⚠️ TELEGRAM_BOT_TOKEN chưa được thiết lập! Vui lòng thêm biến môi trường TELEGRAM_BOT_TOKEN."
        )

    yield

    # Shutdown logic
    logger.info("🛑 Đang dừng Telegram bot...")
    sync_task.cancel()
    if tg_app:
        try:
            if tg_app.updater and tg_app.updater.running:
                await tg_app.updater.stop()
            await tg_app.stop()
            await tg_app.shutdown()
            logger.info("✅ Đã dừng bot an toàn.")
        except Exception as e:
            logger.error(f"Lỗi khi dừng bot: {e}")


web_app = FastAPI(title="Telegram Driver Google Sheets Bot", lifespan=lifespan)


@web_app.get("/")
async def root():
    return {
        "status": "ok",
        "service": "Telegram Driver Google Sheets Bot",
        "sheet_id": config.GOOGLE_SHEET_ID,
        "connected_to_sheet": sheets_manager.is_connected(),
    }


@web_app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "bot_initialized": tg_app is not None,
        "sheets_connected": sheets_manager.is_connected(),
    }


@web_app.post("/webhook")
async def telegram_webhook(request: Request):
    """Receive incoming webhook updates from Telegram."""
    if not tg_app:
        return {"status": "bot_not_ready"}

    try:
        update_data = await request.json()
        update = Update.de_json(update_data, tg_app.bot)
        await tg_app.process_update(update)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Lỗi xử lý webhook update: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    uvicorn.run(
        "app:web_app",
        host="0.0.0.0",
        port=config.PORT,
        reload=False,
    )
