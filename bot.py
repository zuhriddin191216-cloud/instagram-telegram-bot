import asyncio
import os
import re
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

import requests
import instaloader
import yt_dlp

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart


BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", "10000"))

bot = Bot(BOT_TOKEN)
dp = Dispatcher()


# =========================
# RENDER HEALTH SERVER
# =========================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass


def run_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    print(f"🌐 Render web server started on port {PORT}")
    server.serve_forever()


# =========================
# URL
# =========================

def is_instagram_url(url):
    return bool(
        re.search(
            r"https?://(www\.)?instagram\.com/(reel|p|tv)/",
            url,
            re.IGNORECASE,
        )
    )


# =========================
# YT-DLP VIDEO
# =========================

def download_video(url, folder):
    output = os.path.join(folder, "video.%(ext)s")

    ydl_opts = {
        "outtmpl": output,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,

        # Avval Telegram uchun qulay H264 video qidiradi
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
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        filename = ydl.prepare_filename(info)

        if not os.path.exists(filename):
            mp4 = os.path.splitext(filename)[0] + ".mp4"
            if os.path.exists(mp4):
                filename = mp4

        if os.path.exists(filename):
            return filename

        for f in os.listdir(folder):
            if f.endswith(".mp4"):
                return os.path.join(folder, f)

    except Exception as e:
        print("❌ yt-dlp error:", e)

    return None


# =========================
# VIDEO CODEC
# =========================

def get_video_codec(filename):
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
                filename,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        return result.stdout.strip().lower()

    except Exception as e:
        print("⚠️ ffprobe error:", e)
        return ""


# =========================
# PREPARE VIDEO
# =========================

def prepare_video(filename, folder):
    if not filename:
        return None

    codec = get_video_codec(filename)
    print("🎥 Video codec:", codec)

    # H264 bo'lsa, faqat remux
    if codec in ("h264", "avc1"):
        output = os.path.join(folder, "telegram_video.mp4")

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
                    output,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
            )

            if os.path.exists(output):
                return output

        except Exception as e:
            print("⚠️ Remux error:", e)

        return filename

    # H264 emas bo'lsa — Telegramga mos qilib convert
    output = os.path.join(folder, "telegram_video.mp4")

    try:
        print("⚙️ Video H264 emas, conversion boshlanmoqda...")

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

                output,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=45,
        )

        if os.path.exists(output):
            return output

    except Exception as e:
        print("❌ Conversion error:", e)

    return None


# =========================
# INSTAGRAM IMAGES
# =========================

def extract_image_urls(url):
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1"
            )
        }

        r = requests.get(
            url,
            headers=headers,
            timeout=20,
        )

        if r.status_code != 200:
            print("⚠️ Instagram status:", r.status_code)
            return []

        html = r.text

        urls = re.findall(
            r'https://[^"\']+\.(?:jpg|jpeg|png)[^"\']*',
            html,
            re.IGNORECASE,
        )

        result = []

        for item in urls:
            item = item.replace("\\u0026", "&")
            item = item.replace("\\/", "/")

            if item not in result:
                result.append(item)

        print("🖼 Found images:", len(result))

        return result[:20]

    except Exception as e:
        print("❌ Image extraction error:", e)

    return []


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
                timeout=20,
            )

            if r.status_code == 200 and r.content:
                filename = os.path.join(
                    folder,
                    f"image_{i + 1}.jpg"
                )

                with open(filename, "wb") as f:
                    f.write(r.content)

                files.append(filename)

        except Exception as e:
            print("⚠️ Image error:", e)

    return files


# =========================
# INSTALOADER FALLBACK
# =========================

def download_instaloader(url, folder):
    try:
        shortcode_match = re.search(
            r"instagram\.com/(?:p|reel|tv)/([^/?]+)",
            url,
        )

        if not shortcode_match:
            return []

        shortcode = shortcode_match.group(1)

        print("🔄 Instaloader fallback:", shortcode)

        loader = instaloader.Instaloader(
            dirname_pattern=folder,
            filename_pattern="{shortcode}_{date_utc:%Y%m%d_%H%M%S}",
            download_video_thumbnails=False,
            save_metadata=False,
            compress_json=False,
            post_metadata_txt_pattern="",
        )

        post = instaloader.Post.from_shortcode(
            loader.context,
            shortcode,
        )

        files = []

        if post.typename == "GraphSidecar":
            for index, node in enumerate(post.get_sidecar_nodes()):
                if node.is_video:
                    continue

                target = os.path.join(
                    folder,
                    f"image_{index + 1}.jpg"
                )

                r = requests.get(
                    node.display_url,
                    timeout=20,
                )

                if r.status_code == 200:
                    with open(target, "wb") as f:
                        f.write(r.content)

                    files.append(target)

        elif post.typename == "GraphImage":
            target = os.path.join(
                folder,
                "image_1.jpg"
            )

            r = requests.get(
                post.url,
                timeout=20,
            )

            if r.status_code == 200:
                with open(target, "wb") as f:
                    f.write(r.content)

                files.append(target)

        return files

    except Exception as e:
        print("❌ Instaloader error:", e)

    return []


# =========================
# DOWNLOAD MEDIA
# =========================

def download_media(url, folder):
    parsed = urlparse(url)
    path = parsed.path.lower()

    # Reel / video
    if "/reel/" in path or "/tv/" in path:
        video = download_video(url, folder)

        if not video:
            return {
                "type": "error"
            }

        prepared = prepare_video(video, folder)

        if not prepared:
            return {
                "type": "error"
            }

        return {
            "type": "video",
            "file": prepared
        }

    # Post
    if "/p/" in path:
        # Avval yt-dlp
        video = download_video(url, folder)

        if video:
            prepared = prepare_video(video, folder)

            if prepared:
                return {
                    "type": "video",
                    "file": prepared
                }

        # Rasm
        images = extract_image_urls(url)

        if images:
            files = download_images(images, folder)

            if files:
                return {
                    "type": "images",
                    "files": files
                }

        # Instaloader fallback
        files = download_instaloader(url, folder)

        if files:
            return {
                "type": "images",
                "files": files
            }

    return {
        "type": "error"
    }


# =========================
# SEND MEDIA
# =========================

async def send_media(message, result):
    try:
        if result["type"] == "video":
            file_path = result["file"]

            try:
                await message.answer_video(
                    types.FSInputFile(file_path),
                    supports_streaming=True,
                )
                return True

            except Exception as e:
                print("⚠️ Video upload failed:", e)

                try:
                    await message.answer_document(
                        types.FSInputFile(file_path)
                    )
                    return True
                except Exception as e2:
                    print("❌ Document upload failed:", e2)

        elif result["type"] == "images":
            files = result["files"]

            # Telegram media group max 10
            for i in range(0, len(files), 10):
                batch = files[i:i + 10]

                media = []

                for file_path in batch:
                    media.append(
                        types.InputMediaPhoto(
                            media=types.FSInputFile(file_path)
                        )
                    )

                await message.answer_media_group(
                    media=media
                )

            return True

    except Exception as e:
        print("❌ Send media error:", e)

    return False


# =========================
# START
# =========================

@dp.message(CommandStart())
async def start_handler(message: types.Message):
    await message.answer(
        "👋 Салом!\n\n"
        "Instagram Reel ёки Post ҳаволасини юборинг."
    )


# =========================
# MAIN HANDLER
# =========================

@dp.message()
async def message_handler(message: types.Message):

    text = (message.text or "").strip()

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

    # Status updater
    stop_status = asyncio.Event()

    async def status_updater():
        seconds = 0

        messages = [
            "⏳ Instagramдан юкланяпти...",
            "⏳ Instagramдан маълумот олиняпти...",
            "⚙️ Видео тайёрланяпти...",
            "⚙️ Файл Telegram учун тайёрланяпти...",
        ]

        index = 0

        while not stop_status.is_set():
            await asyncio.sleep(5)

            if stop_status.is_set():
                break

            seconds += 5

            index = min(
                index + 1,
                len(messages) - 1
            )

            try:
                await status.edit_text(
                    f"{messages[index]}\n"
                    f"⏱ {seconds} секунд"
                )
            except Exception:
                pass

    updater_task = asyncio.create_task(
        status_updater()
    )

    try:
        result = await asyncio.to_thread(
            download_media,
            text,
            folder,
        )

        stop_status.set()

        try:
            await updater_task
        except Exception:
            pass

        if result["type"] == "error":
            await status.edit_text(
                "❌ Видео ёки расмни юклаб бўлмади.\n"
                "Instagram ҳаволасини текширинг."
            )
            return

        await status.edit_text(
            "📤 Telegram'га юбориляпти..."
        )

        success = await send_media(
            message,
            result,
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
        print("❌ Handler error:", e)

        stop_status.set()

        try:
            await updater_task
        except Exception:
            pass

        try:
            await status.edit_text(
                "❌ Хатолик юз берди. Қайта уриниб кўринг."
            )
        except Exception:
            pass

    finally:
        # Temp fayllarni o'chirish
        try:
            for filename in os.listdir(folder):
                path = os.path.join(folder, filename)

                if os.path.isfile(path):
                    os.remove(path)

            os.rmdir(folder)

        except Exception:
            pass


# =========================
# RUN
# =========================

async def main():
    print("🤖 BOT STARTING")

    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        print(
            "✅ FFmpeg:",
            result.stdout.splitlines()[0]
            if result.stdout
            else "installed"
        )

    except Exception:
        print("⚠️ FFmpeg not found")

    threading.Thread(
        target=run_server,
        daemon=True,
    ).start()

    # Eski Telegram update'larni tozalash
    try:
        await bot.delete_webhook(
            drop_pending_updates=True
        )
        print("🧹 Old Telegram updates cleared")
    except Exception as e:
        print("⚠️ Webhook cleanup:", e)

    print("🤖 Bot ishga tushdi!")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
