import asyncio
import html
import os
import re
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import unquote

import requests
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
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) "
                "AppleWebKit/605.1.15 "
                "(KHTML, like Gecko) Version/17.0 "
                "Mobile/15E148 Safari/604.1"
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


def clean_url(raw):
    try:
        value = raw.replace("\\/", "/")
        value = value.replace("\\u0026", "&")
        value = value.replace("\\u003D", "=")
        value = value.replace("\\u0025", "%")
        value = html.unescape(value)
        value = unquote(value)
        return value
    except Exception:
        return raw


def get_instagram_images(url, folder):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) "
            "AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/17.0 "
            "Mobile/15E148 Safari/604.1"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.instagram.com/",
    }

    session = requests.Session()
    response = session.get(
        url,
        headers=headers,
        timeout=30,
        allow_redirects=True,
    )

    response.raise_for_status()

    page = response.text

    print("Instagram status:", response.status_code)
    print("Instagram URL:", response.url)
    print("HTML size:", len(page))

    image_urls = []

    # Асосий carousel расмлар
    patterns = [
        r'"display_url"\s*:\s*"([^"]+)"',
        r'"thumbnail_src"\s*:\s*"([^"]+)"',
        r'"image_versions2"\s*:\s*\{.*?"url"\s*:\s*"([^"]+)"',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, page, flags=re.DOTALL)

        for raw in matches:
            image_url = clean_url(raw)

            if (
                image_url.startswith("http")
                and (
                    "scontent" in image_url
                    or "cdninstagram" in image_url
                    or ".jpg" in image_url
                    or ".jpeg" in image_url
                    or ".png" in image_url
                    or ".webp" in image_url
                )
            ):
                if image_url not in image_urls:
                    image_urls.append(image_url)

    # OpenGraph биринчи расм учун fallback
    og_matches = re.findall(
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
        page,
        flags=re.IGNORECASE,
    )

    for raw in og_matches:
        image_url = clean_url(raw)

        if image_url.startswith("http") and image_url not in image_urls:
            image_urls.append(image_url)

    # Дубликатларни олиб ташлаш
    unique_urls = []

    for item in image_urls:
        base = item.split("?")[0]

        if base not in [
            x.split("?")[0]
            for x in unique_urls
        ]:
            unique_urls.append(item)

    print("Found image URLs:", len(unique_urls))

    downloaded = []

    for index, image_url in enumerate(unique_urls, start=1):
        try:
            image_response = session.get(
                image_url,
                headers=headers,
                timeout=30,
            )

            image_response.raise_for_status()

            content_type = image_response.headers.get(
                "Content-Type",
                ""
            ).lower()

            if "image" not in content_type:
                continue

            extension = ".jpg"

            if "png" in content_type:
                extension = ".png"
            elif "webp" in content_type:
                extension = ".webp"
            elif "jpeg" in content_type:
                extension = ".jpg"

            filename = os.path.join(
                folder,
                f"image_{index}{extension}"
            )

            with open(filename, "wb") as file:
                file.write(image_response.content)

            downloaded.append(filename)

        except Exception as error:
            print(
                f"Image {index} error:",
                error
            )

    return downloaded


def download_media(url, folder):
    # 1. Аввало видео
    try:
        video = download_video(url, folder)

        if video:
            return [video]

    except Exception as error:
        print("yt-dlp:", error)

    # 2. Агар видео бўлмаса — расм
    try:
        images = get_instagram_images(
            url,
            folder
        )

        if images:
            return images

    except Exception as error:
        print("Instagram image parser:", error)

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
            "❌ Instagram ссылкаси юборинг."
        )
        return

    status = await message.answer(
        "⏳ Юкланяпти..."
    )

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

                extension = os.path.splitext(
                    media
                )[1].lower()

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

    bot = Bot(
        token=BOT_TOKEN
    )

    threading.Thread(
        target=start_server,
        daemon=True
    ).start()

    print("🤖 Bot ishga tushdi!")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
