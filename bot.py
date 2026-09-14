import asyncio
import os
import re
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import yt_dlp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import FSInputFile


BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi")


dp = Dispatcher()


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running!")

    def log_message(self, format, *args):
        pass


def start_server():
    port = int(os.getenv("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()


def is_instagram_url(text):
    return re.search(
        r"https?://(www\.)?instagram\.com/(reel|reels|p|tv)/",
        text
    )


def download_video(url, folder):
    output = os.path.join(folder, "video.%(ext)s")

    options = {
        "outtmpl": output,
        "format": "best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 "
                "like Mac OS X) AppleWebKit/605.1.15 "
                "Version/17.0 Mobile/15E148 Safari/604.1"
            ),
            "Referer": "https://www.instagram.com/",
        },
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])

    for filename in os.listdir(folder):
        if filename.startswith("video."):
            return os.path.join(folder, filename)

    return None


def download_images(url, folder):
    """
    Instagram photo/carousel учун gallery-dl ишлатади.
    """
    command = [
        "gallery-dl",
        "--directory",
        folder,
        "--no-mtime",
        url,
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=120,
    )

    print("gallery-dl stdout:", result.stdout)
    print("gallery-dl stderr:", result.stderr)

    files = []

    for root, dirs, filenames in os.walk(folder):
        for filename in filenames:
            path = os.path.join(root, filename)

            if filename.lower().endswith(
                (".jpg", ".jpeg", ".png", ".webp")
            ):
                files.append(path)

    return sorted(files)


def download_media(url, folder):
    """
    Аввал video/Reel сифатида олишга ҳаракат қилади.
    Агар video формат топилмаса, gallery-dl орқали
    photo/carousel сифатида олади.
    """

    try:
        video = download_video(url, folder)

        if video:
            return [video]

    except Exception as error:
        print("yt-dlp:", error)

    # Видео эмас — photo/carousel бўлиши мумкин
    try:
        images = download_images(url, folder)

        if images:
            return images

    except Exception as error:
        print("gallery-dl:", error)

    return []


@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer(
        "👋 Салом!\n\n"
        "Instagram Reel ёки Post ссылкасини юборинг.\n\n"
        "🎥 Видео\n"
        "📸 Расм\n"
        "🖼 Бир нечта расмли Post\n\n"
        "ҳаммасини юклаб бераман."
    )


@dp.message()
async def get_media(message: types.Message):
    url = (message.text or "").strip()

    if not is_instagram_url(url):
        await message.answer(
            "❌ Instagram ссылкаси юборинг.\n\n"
            "Масалан:\n"
            "https://www.instagram.com/reel/..."
        )
        return

    status = await message.answer("⏳ Юкланяпти...")

    with tempfile.TemporaryDirectory() as folder:
        try:
            media_files = await asyncio.to_thread(
                download_media,
                url,
                folder
            )

            if not media_files:
                await status.edit_text(
                    "❌ Медиафайлни топа олмадим.\n\n"
                    "Instagram Post очиқ бўлиши керак."
                )
                return

            await status.edit_text(
                "📤 Telegram'га юбориляпти..."
            )

            for media in media_files:
                extension = os.path.splitext(media)[1].lower()

                if extension in (
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".webp"
                ):
                    await message.answer_photo(
                        photo=FSInputFile(media)
                    )
                else:
                    await message.answer_video(
                        video=FSInputFile(media)
                    )

            await status.delete()

        except Exception as error:
            print("ERROR:", error)

            await status.edit_text(
                "❌ Юклашда хатолик бўлди."
            )


async def main():
    bot = Bot(token=BOT_TOKEN)

    threading.Thread(
        target=start_server,
        daemon=True
    ).start()

    print("🤖 Bot ishga tushdi!")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
