import asyncio
import os
import re
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


# Render serveri uxlab qolmasligi va port ochiq bo‘lishi uchun
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
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])

    for filename in os.listdir(folder):
        if filename.startswith("video."):
            return os.path.join(folder, filename)

    return None


@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer(
        "👋 Салом!\n\n"
        "Instagram Reel ёки Post ссылкасини юборинг.\n"
        "Мен видеони юклаб, сизга юбориб бераман 🎥"
    )


@dp.message()
async def get_video(message: types.Message):
    url = (message.text or "").strip()

    if not is_instagram_url(url):
        await message.answer(
            "❌ Instagram ссылкаси юборинг.\n\n"
            "Масалан:\n"
            "https://www.instagram.com/reel/..."
        )
        return

    status = await message.answer("⏳ Видео юкланяпти...")

    with tempfile.TemporaryDirectory() as folder:
        try:
            video = await asyncio.to_thread(
                download_video,
                url,
                folder
            )

            if not video:
                await status.edit_text(
                    "❌ Видеони топа олмадим."
                )
                return

            await status.edit_text("📤 Видео Telegram'га юбориляпти...")

            await message.answer_video(
                video=FSInputFile(video),
                caption="✅ Тайёр!"
            )

            await status.delete()

        except Exception as error:
            print("ERROR:", error)

            await status.edit_text(
                "❌ Видеони юклашда хатолик бўлди.\n\n"
                "Instagram аккаунти ёпиқ бўлиши ёки видео "
                "Telegram лимитидан катта бўлиши мумкин."
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
