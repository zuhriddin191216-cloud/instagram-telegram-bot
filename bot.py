import asyncio
import os
import re
import shutil
import tempfile
import subprocess

import requests
import instaloader
import yt_dlp

from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application


# =========================
# CONFIG
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", "10000"))
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi")

if not RENDER_URL:
    raise RuntimeError("RENDER_EXTERNAL_URL topilmadi")

WEBHOOK_PATH = "/telegram/webhook"
WEBHOOK_URL = RENDER_URL.rstrip("/") + WEBHOOK_PATH

bot = Bot(BOT_TOKEN)
dp = Dispatcher()


# =========================
# INSTAGRAM URL
# =========================

def is_instagram_url(text):
    return bool(
        re.search(
            r"https?://(?:www\.)?instagram\.com/(?:reel|p|tv)/",
            text,
            re.IGNORECASE
        )
    )


# =========================
# VIDEO DOWNLOAD
# =========================

def download_video(url, folder):

    output = os.path.join(
        folder,
        "video.%(ext)s"
    )

    ydl_opts = {
        "outtmpl": output,
        "noplaylist": True,

        # Only MP4 / H264 first
        "format": (
            "bestvideo[vcodec^=avc1][ext=mp4]+"
            "bestaudio[acodec^=mp4a][ext=m4a]/"
            "best[vcodec^=avc1][ext=mp4]/"
            "best[ext=mp4]"
        ),

        "merge_output_format": "mp4",

        # Faster
        "quiet": True,
        "no_warnings": True,

        "retries": 2,
        "fragment_retries": 2,
        "socket_timeout": 20,
    }

    try:

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:

            info = ydl.extract_info(
                url,
                download=True
            )

            filename = ydl.prepare_filename(info)

        if os.path.exists(filename):
            return filename

        mp4 = os.path.splitext(filename)[0] + ".mp4"

        if os.path.exists(mp4):
            return mp4

        for file in os.listdir(folder):

            if file.endswith(".mp4"):
                return os.path.join(
                    folder,
                    file
                )

    except Exception as e:

        print("❌ VIDEO ERROR:", e)

    return None


# =========================
# VIDEO CODEC
# =========================

def get_codec(filename):

    try:

        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                filename
            ],
            capture_output=True,
            text=True,
            timeout=8
        )

        return result.stdout.strip().lower()

    except Exception:

        return ""


# =========================
# PREPARE VIDEO
# =========================

def prepare_video(filename, folder):

    if not filename:
        return None

    codec = get_codec(filename)

    print("🎥 CODEC:", codec)

    # H264 = Telegram friendly
    if codec == "h264":

        output = os.path.join(
            folder,
            "telegram.mp4"
        )

        try:

            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    filename,
                    "-c",
                    "copy",
                    "-movflags",
                    "+faststart",
                    output
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15
            )

            if os.path.exists(output):
                return output

        except Exception as e:

            print("⚠️ REMUX:", e)

        return filename

    # Other codecs
    output = os.path.join(
        folder,
        "telegram.mp4"
    )

    try:

        print("⚙️ Converting to H264...")

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                filename,

                "-vf",
                "scale=min(480\\,iw):-2",

                "-r",
                "24",

                "-c:v",
                "libx264",

                "-preset",
                "ultrafast",

                "-crf",
                "32",

                "-pix_fmt",
                "yuv420p",

                "-c:a",
                "aac",

                "-b:a",
                "64k",

                "-movflags",
                "+faststart",

                output
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30
        )

        if os.path.exists(output):
            return output

    except Exception as e:

        print("❌ CONVERSION:", e)

    # Don't send VP9 as video
    return None


# =========================
# IMAGE EXTRACTION
# =========================

def extract_image_urls(url):

    headers = {
        "User-Agent":
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 "
            "Version/17.0 Mobile/15E148 Safari/604.1"
    }

    try:

        r = requests.get(
            url,
            headers=headers,
            timeout=15
        )

        if r.status_code != 200:
            return []

        html = r.text

        urls = re.findall(
            r'https://[^"\']+\.(?:jpg|jpeg|png)[^"\']*',
            html,
            re.IGNORECASE
        )

        result = []

        for url in urls:

            url = (
                url
                .replace("\\u0026", "&")
                .replace("\\/", "/")
            )

            if url not in result:
                result.append(url)

        print(
            "🖼 Images found:",
            len(result)
        )

        return result[:20]

    except Exception as e:

        print("❌ IMAGE PARSE:", e)

        return []


# =========================
# DOWNLOAD IMAGES
# =========================

def download_images(urls, folder):

    files = []

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    for i, url in enumerate(urls):

        try:

            r = requests.get(
                url,
                headers=headers,
                timeout=15
            )

            if r.status_code == 200:

                filename = os.path.join(
                    folder,
                    f"image_{i + 1}.jpg"
                )

                with open(
                    filename,
                    "wb"
                ) as f:

                    f.write(r.content)

                files.append(filename)

        except Exception as e:

            print(
                "⚠️ IMAGE:",
                e
            )

    return files


# =========================
# INSTALOADER
# =========================

def download_instaloader(url, folder):

    try:

        match = re.search(
            r"instagram\.com/(?:p|reel|tv)/([^/?]+)",
            url
        )

        if not match:
            return []

        shortcode = match.group(1)

        print(
            "🔄 Instaloader:",
            shortcode
        )

        loader = instaloader.Instaloader(
            dirname_pattern=folder,
            download_video_thumbnails=False,
            save_metadata=False,
            compress_json=False,
            post_metadata_txt_pattern=""
        )

        post = instaloader.Post.from_shortcode(
            loader.context,
            shortcode
        )

        files = []

        # =====================
        # CAROUSEL
        # =====================

        if post.typename == "GraphSidecar":

            for i, node in enumerate(
                post.get_sidecar_nodes()
            ):

                # Ignore videos
                if node.is_video:
                    continue

                filename = os.path.join(
                    folder,
                    f"image_{i + 1}.jpg"
                )

                r = requests.get(
                    node.display_url,
                    timeout=15
                )

                if r.status_code == 200:

                    with open(
                        filename,
                        "wb"
                    ) as f:

                        f.write(r.content)

                    files.append(filename)

        # =====================
        # SINGLE IMAGE
        # =====================

        elif post.typename == "GraphImage":

            filename = os.path.join(
                folder,
                "image_1.jpg"
            )

            r = requests.get(
                post.url,
                timeout=15
            )

            if r.status_code == 200:

                with open(
                    filename,
                    "wb"
                ) as f:

                    f.write(r.content)

                files.append(filename)

        print(
            "📸 Instaloader:",
            len(files)
        )

        return files

    except Exception as e:

        print(
            "❌ INSTALOADER:",
            e
        )

        return []


# =========================
# DOWNLOAD MEDIA
# =========================

def download_media(url, folder):

    path = url.split("?")[0].lower()

    # =====================
    # REEL
    # =====================

    if "/reel/" in path or "/tv/" in path:

        video = download_video(
            url,
            folder
        )

        if not video:
            return {"type": "error"}

        prepared = prepare_video(
            video,
            folder
        )

        if not prepared:
            return {"type": "error"}

        return {
            "type": "video",
            "file": prepared
        }

    # =====================
    # POST
    # =====================

    if "/p/" in path:

        # Try video
        video = download_video(
            url,
            folder
        )

        if video:

            prepared = prepare_video(
                video,
                folder
            )

            if prepared:

                return {
                    "type": "video",
                    "file": prepared
                }

        # Try HTML images
        images = extract_image_urls(url)

        if images:

            files = download_images(
                images,
                folder
            )

            if files:

                return {
                    "type": "images",
                    "files": files
                }

        # Instaloader fallback
        files = download_instaloader(
            url,
            folder
        )

        if files:

            return {
                "type": "images",
                "files": files
            }

    return {
        "type": "error"
    }


# =========================
# SEND VIDEO
# =========================

async def send_video(
    message,
    filename
):

    try:

        await message.answer_video(
            types.FSInputFile(filename),
            supports_streaming=True
        )

        return True

    except Exception as e:

        print(
            "❌ VIDEO SEND:",
            e
        )

        try:

            await message.answer_document(
                types.FSInputFile(filename)
            )

            return True

        except Exception:

            return False


# =========================
# SEND ALBUM
# =========================

async def send_album(
    message,
    files
):

    try:

        # Telegram max 10 files per album
        for start in range(
            0,
            len(files),
            10
        ):

            batch = files[
                start:start + 10
            ]

            media = []

            for filename in batch:

                media.append(
                    types.InputMediaPhoto(
                        media=types.FSInputFile(
                            filename
                        )
                    )
                )

            await message.answer_media_group(
                media=media
            )

        return True

    except Exception as e:

        print(
            "❌ ALBUM ERROR:",
            e
        )

        return False


# =========================
# START COMMAND
# =========================

@dp.message(CommandStart())
async def start_handler(
    message: types.Message
):

    await message.answer(
        "👋 Салом!\n\n"
        "🎥 Instagram Reel\n"
        "📸 Instagram Post\n\n"
        "Ҳаволани юборинг."
    )


# =========================
# MESSAGE HANDLER
# =========================

@dp.message()
async def message_handler(
    message: types.Message
):

    text = (
        message.text or ""
    ).strip()

    if not is_instagram_url(text):

        await message.answer(
            "❌ Instagram ҳаволасини юборинг."
        )

        return

    status = await message.answer(
        "⏳ Юкланяпти..."
    )

    folder = tempfile.mkdtemp(
        prefix="instagram_"
    )

    status_task = None

    try:

        # =====================
        # STATUS
        # =====================

        async def status_loop():

            messages = [
                "⏳ Instagramдан юкланяпти...",
                "🔎 Instagram маълумотлари олиняпти...",
                "⚙️ Файл тайёрланяпти...",
                "📦 Telegram учун тайёрланяпти..."
            ]

            for msg in messages:

                await asyncio.sleep(4)

                try:

                    await status.edit_text(
                        msg
                    )

                except Exception:
                    pass

        status_task = asyncio.create_task(
            status_loop()
        )

        # =====================
        # DOWNLOAD
        # =====================

        result = await asyncio.to_thread(
            download_media,
            text,
            folder
        )

        if status_task:

            status_task.cancel()

        # =====================
        # ERROR
        # =====================

        if result["type"] == "error":

            await status.edit_text(
                "❌ Юклаб бўлмади.\n"
                "Ҳаволани текширинг."
            )

            return

        # =====================
        # VIDEO
        # =====================

        if result["type"] == "video":

            await status.edit_text(
                "📤 Видео Telegram'га юбориляпти..."
            )

            success = await send_video(
                message,
                result["file"]
            )

        # =====================
        # ALBUM
        # =====================

        else:

            await status.edit_text(
                "📸 Расмлар альбом қилиняпти..."
            )

            success = await send_album(
                message,
                result["files"]
            )

        # =====================
        # FINISH
        # =====================

        if success:

            try:
                await status.delete()
            except Exception:
                pass

        else:

            await status.edit_text(
                "❌ Юборишда хатолик."
            )

    except Exception as e:

        print(
            "❌ HANDLER ERROR:",
            e
        )

        try:

            await status.edit_text(
                "❌ Хатолик юз берди. "
                "Қайта уриниб кўринг."
            )

        except Exception:
            pass

    finally:

        if status_task:

            status_task.cancel()

        shutil.rmtree(
            folder,
            ignore_errors=True
        )


# =========================
# HEALTH
# =========================

async def health(request):

    return web.Response(
        text="OK"
    )


# =========================
# MAIN
# =========================

async def main():

    print("🤖 BOT STARTING")
    print(
        "🌐 WEBHOOK:",
        WEBHOOK_URL
    )

    app = web.Application()

    # Render health
    app.router.add_get(
        "/",
        health
    )

    # Telegram webhook
    webhook_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot
    )

    webhook_handler.register(
        app,
        path=WEBHOOK_PATH
    )

    setup_application(
        app,
        dp,
        bot=bot
    )

    # IMPORTANT:
    # No polling!
    # No getUpdates!
    # No delete_webhook!

    await bot.set_webhook(
        WEBHOOK_URL,
        drop_pending_updates=True
    )

    print(
        "✅ WEBHOOK SET"
    )

    runner = web.AppRunner(
        app
    )

    await runner.setup()

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        PORT
    )

    await site.start()

    print(
        f"🚀 SERVER RUNNING: {PORT}"
    )

    await asyncio.Event().wait()


if __name__ == "__main__":

    asyncio.run(
        main()
    )
