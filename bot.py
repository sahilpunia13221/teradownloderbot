import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "@CineBuzz3600")
TERABOX_API = os.getenv(
    "TERABOX_API",
    "https://desibotz-terabox-api.krishnalucky193.workers.dev/api"
)

URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
MENTION_RE = re.compile(r"(?<!\w)@[A-Za-z0-9_]{4,}", re.IGNORECASE)


def find_terabox_url(text: str):
    if not text:
        return None
    for url in URL_RE.findall(text):
        clean = url.rstrip(".,)]}>\"'")
        host = urlparse(clean).netloc.lower()
        if "terabox" in host or "1024tera" in host or "terabox" in clean.lower():
            return clean
    return None


def clean_caption(original_text: str, terabox_url: str, fallback_name: str):
    caption = original_text or ""
    if terabox_url:
        caption = caption.replace(terabox_url, "")

    def repl(match):
        mention = match.group(0)
        return CHANNEL_USERNAME if mention.lower() == CHANNEL_USERNAME.lower() else ""

    caption = MENTION_RE.sub(repl, caption)
    lines = [re.sub(r"[ \t]+", " ", x).strip() for x in caption.splitlines()]
    caption = "\n".join(x for x in lines if x).strip()

    if not caption:
        caption = Path(fallback_name).stem

    caption = re.sub(
        re.escape(CHANNEL_USERNAME), "", caption, flags=re.IGNORECASE
    ).strip()

    final_caption = f"{caption}\n\n{CHANNEL_USERNAME}"
    if len(final_caption) > 1024:
        reserve = len(CHANNEL_USERNAME) + 3
        final_caption = final_caption[:1024-reserve].rstrip() + "\n\n" + CHANNEL_USERNAME
    return final_caption


async def get_terabox_info(url: str):
    timeout = httpx.Timeout(60.0, connect=20.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        r = await client.get(TERABOX_API, params={"url": url})
        r.raise_for_status()
        data = r.json()

    if data.get("status") != "success":
        raise RuntimeError(data.get("message", "TeraBox API error"))
    return data


async def download_file(url: str, output: Path):
    timeout = httpx.Timeout(connect=30.0, read=None, write=30.0, pool=30.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        async with client.stream("GET", url) as r:
            r.raise_for_status()
            with output.open("wb") as f:
                async for chunk in r.aiter_bytes(1024 * 1024):
                    f.write(chunk)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "🎬 TeraBox Downloader\n\n"
        "TeraBox link या link वाला caption/message भेजें।\n"
        f"Bot caption में दूसरे @mentions हटाकर {CHANNEL_USERNAME} जोड़ देगा।"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        return

    original_text = message.text or message.caption or ""
    terabox_url = find_terabox_url(original_text)

    if not terabox_url:
        await message.reply_text("❌ इस message में TeraBox link नहीं मिला।")
        return

    status = await message.reply_text("🔎 TeraBox link process कर रहा हूँ...")
    temp_dir = None

    try:
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
        data = await get_terabox_info(terabox_url)

        file_info = next(
            (x for x in (data.get("files") or [])
             if x.get("type") == "video" and x.get("download_url")),
            None
        )

        if file_info:
            filename = file_info.get("name") or data.get("file_name", "video.mp4")
            download_url = file_info.get("download_url")
            size_bytes = file_info.get("size")
            quality = file_info.get("quality")
        else:
            filename = data.get("file_name", "video.mp4")
            download_url = data.get("download_url")
            size_bytes = None
            quality = data.get("quality")

        if not download_url:
            raise RuntimeError("API response में download_url नहीं मिला।")

        filename = Path(filename).name
        if not filename.lower().endswith(".mp4"):
            filename += ".mp4"

        caption = clean_caption(original_text, terabox_url, filename)

        # Standard Telegram hosted Bot API limit. For large movie files,
        # use a Local Bot API server and adjust this check accordingly.
        if size_bytes and size_bytes > 50 * 1024 * 1024:
            raise RuntimeError(
                "यह file 50 MB से बड़ी है। बड़ी files के लिए Local Telegram "
                "Bot API Server configure करना होगा।"
            )

        await status.edit_text(
            "⬇️ Video download हो रहा है..." +
            (f"\nQuality: {quality}" if quality else "")
        )

        temp_dir = tempfile.TemporaryDirectory(prefix="terabox_")
        output = Path(temp_dir.name) / filename
        await download_file(download_url, output)

        if output.stat().st_size > 50 * 1024 * 1024:
            raise RuntimeError(
                "Downloaded file 50 MB से बड़ी है। Standard Telegram Bot API "
                "पर इसे upload नहीं किया जा सकता।"
            )

        await status.edit_text("⬆️ Telegram पर video upload हो रहा है...")
        await context.bot.send_chat_action(
            update.effective_chat.id, ChatAction.UPLOAD_VIDEO
        )

        with output.open("rb") as f:
            await message.reply_video(
                video=f,
                caption=caption,
                filename=filename,
                supports_streaming=True,
                read_timeout=300,
                write_timeout=300,
                connect_timeout=60,
                pool_timeout=60,
            )

        await status.delete()

    except httpx.HTTPStatusError as e:
        await status.edit_text(f"❌ HTTP error: {e.response.status_code}")
    except httpx.RequestError:
        await status.edit_text("❌ API/download server से connection नहीं हो पाया।")
    except RuntimeError as e:
        await status.edit_text(f"❌ {e}")
    except Exception as e:
        print("Unexpected error:", repr(e))
        await status.edit_text("❌ Video process करते समय unexpected error आया।")
    finally:
        if temp_dir:
            temp_dir.cleanup()


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN .env file में set नहीं है।")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        MessageHandler(
            (filters.TEXT | filters.CaptionRegex(r".+")) & ~filters.COMMAND,
            handle_message
        )
    )
    print("Bot started...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
