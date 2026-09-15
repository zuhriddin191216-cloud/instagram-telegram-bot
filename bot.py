import asyncio
import os
import re
import shutil
import tempfile
from aiohttp import web

import instaloader
import requests
import yt_dlp

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application


# =========================
# SETTINGS
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", "10000"))

# Render automatically provides this
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi!")

if not RENDER_URL:
    raise RuntimeError("RENDER_EXTERNAL_URL topilmadi!")

WEBHOOK_PATH = "/telegram/webhook"
WEBHOOK_URL = RENDER_URL.rstrip("/") + WEBHOOK_PATH


bot = Bot(BOT_TOKEN)
dp = Dispatcher()


# =========================
# INSTAGRAM URL
# =========================

def is_instagram_url(text: str):
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

    output = os.path.join(folder, "video.%(ext)s")

    options = {
        "outtmpl": output,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,

        # First try H264 because Telegram likes it
        "format": (
            "bestvideo[vcodec^=avc1][ext=mp4]+"
            "bestaudio[acodec^=mp4a][ext=m4a]/"
            "best[vcodec^=avc1][ext=mp4]/"
            "bestvideo[ext=mp4]+"
            "bestaudio[ext=m4a]/"
            "best[ext=mp4]/"
            "best"
        ),

        "merge_output_format": "mp4",
    }

    try:
        with yt_dlp.YoutubeDL(options) as ydl:

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
                return os.path.join(folder, file)

    except Exception as e:
        print("VIDEO ERROR:", e)

    return None


# =========================
# VIDEO CODEC
# =========================

def get_codec(filename):

    import subprocess

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
            timeout=10
        )

        return result.stdout.strip().lower()

    except Exception:
        return ""


# =========================
# PREPARE VIDEO
# =========================

def prepare_video(filename, folder):

    import subprocess

    if not filename:
        return None

    codec = get_codec(filename)

    print("VIDEO CODEC:", codec)

    # Already good
    if codec == "h264":

        output = os.path.join(
            folder,
            "telegram_video.mp4"
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
                timeout=20
            )

            if os.path.exists(output):
                return output

        except Exception as e:
            print("REMUX ERROR:", e)

        return filename

    # Convert other codecs
    output = os.path.join(
        folder,
        "telegram_video.mp4"
    )

    try:

        print("Converting video to H264...")

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                filename,

                "-vf",
                "scale=min(720\\,iw):-2",

                "-r",
                "30",

                "-c:v",
                "libx264",

                "-preset",
                "veryfast",

                "-crf",
                "27",

                "-pix_fmt",
                "yuv420p",

                "-c:a",
                "aac",

                "-b:a",
                "96k",

                "-movflags",
                "+faststart",

                output
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60
        )

        if os.path.exists(output):
            return output

    except Exception as e:

        print("CONVERT ERROR:", e)

    return None


# =========================
# INSTAGRAM IMAGE PARSER
# =========================

def extract_images(url):

    headers = {
        "User-Agent":
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 "
            "Version/17.0 Mobile/15E148 Safari/604.1"
    }

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=20
        )

        print(
            "Instagram status:",
            response.status_code
        )

        if response.status_code != 200:
            return []

        html = response.text

        urls = re.findall(
            r'https://[^"\']+\.(?:jpg|jpeg|png)[^"\']*',
            html,
            re.IGNORECASE
        )

        result = []

        for image in urls:

            image = (
                image
                .replace("\\u0026", "&")
                .replace("\\/", "/")
            )

            if image not in result:
                result.append(image)

        print(
            "Images found:",
            len(result)
        )

        return result[:20]

    except Exception as e:

        print(
            "IMAGE PARSE ERROR:",
            e
        )

        return []


# =========================
# DOWNLOAD IMAGES
# =========================

def download_images(urls, folder):

    files = []

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    for index, url in enumerate(urls):

        try:

            response = requests.get(
                url,
                headers=headers,
                timeout=20
            )

            if response.status_code == 200:

                filename = os.path.join(
                    folder,
                    f"image_{index + 1}.jpg"
                )

                with open(filename, "wb") as f:
                    f.write(response.content)

                files.append(filename)

        except Exception as e:

            print(
                "IMAGE DOWNLOAD ERROR:",
                e
            )

    return files


# =========================
# INSTALOADER FALLBACK
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
            "Instaloader:",
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

        # CAROUSEL
        if post.typename == "GraphSidecar":

            for index, node in enumerate(
                post.get_sidecar_nodes()
            ):

                # Skip videos inside carousel
                if node.is_video:
                    continue

                filename = os.path.join(
                    folder,
                    f"image_{index + 1}.jpg"
                )

                response = requests.get(
                    node.display_url,
                    timeout=20
                )

                if response.status_code == 200:

                    with open(
                        filename,
                        "wb"
                    ) as f:

                        f.write(
                            response.content
                        )

                    files.append(filename)

        # SINGLE IMAGE
        elif post.typename == "GraphImage":

            filename = os.path.join(
                folder,
                "image_1.jpg"
            )

            response = requests.get(
                post.url,
                timeout=20
            )

            if response.status_code == 200:

                with open(
                    filename,
                    "wb"
                ) as f:

                    f.write(
                        response.content
                    )

                files.append(filename)

        print(
            "Instaloader images:",
            len(files)
        )

        return files

    except Exception as e:

        print(
            "INSTALOADER ERROR:",
            e
        )

        return []


# =========================
# MAIN DOWNLOAD
# =========================

def download_media(url, folder):

    path = url.split("?")[0].lower()

    # =====================
    # REEL / VIDEO
    # =====================

    if "/reel/" in path or "/tv/" in path:

        video = download_video(
            url,
            folder
        )

        if not video:
            return {
                "type": "error"
            }

        prepared = prepare_video(
            video,
            folder
        )

        if not prepared:
            return {
                "type": "error"
            }

        return {
            "type": "video",
            "file": prepared
        }

    # =====================
    # POST
    # =====================

    if "/p/" in path:

        # First try video
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

        # Try images
        images = extract_images(url)

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
            "VIDEO SEND ERROR:",
            e
        )

        try:

            await message.answer_document(
                types.FSInputFile(filename)
            )

            return True

        except Exception as e2:

            print(
                "DOCUMENT ERROR:",
                e2
            )

            return False


# =========================
# SEND ALBUM
# =========================

async def send_album(
    message,
    files
):

    try:

        # Telegram allows max 10 media
        # per media group.

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
            "ALBUM ERROR:",
            e
        )

        return False


# =========================
# START
# =========================

@dp.message(CommandStart())
async def start_handler(
    message: types.Message
):

    await message.answer(
        "👋 Салом!\n\n"
        "📸 Instagram Post\n"
        "🎥 Instagram Reel\n\n"
        "ҳаволасини юборинг."
    )


# =========================
# MESSAGE
# =========================

@dp.message()
async def message_handler(
    message: types.Message
):

    text = (
        message.text or ""
    ).strip()

    # Only Instagram URLs
    if not is_instagram_url(text):

        await message.answer(
            "❌ Instagram ҳаволасини юборинг."
        )

        return

    status = await message.answer(
        "⏳ Instagramдан юкланяпти..."
    )

    folder = tempfile.mkdtemp(
        prefix="instagram_"
    )

    try:

        # Status updates
        async def update_status():

            messages = [
                "⏳ Instagramдан юкланяпти...",
                "🔎 Маълумот олиняпти...",
                "⚙️ Файл тайёрланяпти...",
                "📦 Telegram учун тайёрланяпти..."
            ]

            for text_status in messages:

                await asyncio.sleep(4)

                try:

                    await status.edit_text(
                        text_status
                    )

                except Exception:
                    pass

        status_task = asyncio.create_task(
            update_status()
        )

        # Download in separate thread
        result = await asyncio.to_thread(
            download_media,
            text,
            folder
        )

        status_task.cancel()

        # Error
        if result["type"] == "error":

            await status.edit_text(
                "❌ Юклаб бўлмади.\n\n"
                "Instagram ҳаволасини текширинг."
            )

            return

        # =====================
        # VIDEO
        # =====================

        if result["type"] == "video":

            await status.edit_text(
                "📤 Telegram'га юбориляпти..."
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

        if success:

            try:
                await status.delete()
            except Exception:
                pass

        else:

            await status.edit_text(
                "❌ Telegram'га юборишда хатолик."
            )

    except Exception as e:

        print(
            "HANDLER ERROR:",
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

        try:
            shutil.rmtree(
                folder,
                ignore_errors=True
            )
        except Exception:
            pass


# =========================
# WEB SERVER
# =========================

async def health(request):

    return web.Response(
        text="OK"
    )


# =========================
# START SERVER
# =========================

async def main():

    print("🤖 BOT STARTING")
    print(
        "Webhook:",
        WEBHOOK_URL
    )

    # Web application
    app = web.Application()

    # Health check
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

    # Set webhook
    await bot.set_webhook(
        WEBHOOK_URL,
        drop_pending_updates=True
    )

    print(
        "✅ Telegram webhook set!"
    )

    runner = web.AppRunner(app)

    await runner.setup()

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        PORT
    )

    await site.start()

    print(
        f"🌐 Server started on port {PORT}"
    )

    # Keep alive
    await asyncio.Event().wait()


if __name__ == "__main__":

    asyncio.run(
        main()
    )
