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
from aiogram.types import (
    FSInputFile,
    InputMediaPhoto,
    InputMediaVideo,
)


# ==========================================
# BOT TOKEN
# ==========================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi")


dp = Dispatcher()


# ==========================================
# RENDER WEB SERVER
# ==========================================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is running!")

    def log_message(self, format, *args):
        pass


def start_server():

    port = int(os.getenv("PORT", "10000"))

    server = HTTPServer(
        ("0.0.0.0", port),
        HealthHandler
    )

    print(f"🌐 Web server started on port {port}")

    server.serve_forever()


# ==========================================
# INSTAGRAM URL
# ==========================================

def is_instagram_url(text):

    if not text:
        return False

    return re.search(
        r"https?://(www\.)?instagram\.com/(reel|reels|p|tv)/",
        text,
        re.IGNORECASE
    )


def is_reel_url(url):

    return re.search(
        r"instagram\.com/(reel|reels)/",
        url,
        re.IGNORECASE
    )


# ==========================================
# VIDEO DOWNLOAD
# ==========================================

def download_video(url, folder):

    output = os.path.join(
        folder,
        "video.%(ext)s"
    )

    options = {

        "outtmpl": output,

        "format": (
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
            "best[ext=mp4]/"
            "best"
        ),

        "merge_output_format": "mp4",

        "quiet": False,

        "no_warnings": False,

        "noplaylist": True,

        "impersonate": "chrome",

        "socket_timeout": 30,

        "retries": 3,

        "fragment_retries": 3,

        "http_headers": {

            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/140.0.0.0 Safari/537.36"
            ),

            "Accept-Language":
                "en-US,en;q=0.9",

            "Referer":
                "https://www.instagram.com/",
        },
    }

    print("")
    print("==========================================")
    print("🎥 VIDEO DOWNLOAD")
    print("==========================================")
    print("🔗 URL:", url)
    print("⚙️ yt-dlp starting...")

    try:

        with yt_dlp.YoutubeDL(options) as ydl:

            ydl.download([url])

    except Exception as error:

        print("")
        print("❌ yt-dlp ERROR")
        print("❌ Error type:", type(error).__name__)
        print("❌ Error:", repr(error))
        print("")

        raise

    # Find downloaded video
    files = os.listdir(folder)

    print("📁 Downloaded files:", files)

    for filename in files:

        if filename.startswith("video."):

            filepath = os.path.join(
                folder,
                filename
            )

            if os.path.isfile(filepath):

                print("✅ Video found:", filepath)

                return filepath

    print("❌ Video file not found")

    return None


# ==========================================
# URL CLEAN
# ==========================================

def clean_url(raw):

    try:

        value = raw.replace("\\/", "/")

        value = value.replace(
            "\\u0026",
            "&"
        )

        value = value.replace(
            "\\u003D",
            "="
        )

        value = value.replace(
            "\\u0025",
            "%"
        )

        value = html.unescape(value)

        value = unquote(value)

        return value

    except Exception:

        return raw


# ==========================================
# INSTAGRAM PAGE
# ==========================================

def get_instagram_page(url):

    headers = {

        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/140.0.0.0 Safari/537.36"
        ),

        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,image/avif,"
            "image/webp,*/*;q=0.8"
        ),

        "Accept-Language":
            "en-US,en;q=0.9",

        "Referer":
            "https://www.instagram.com/",
    }

    session = requests.Session()

    print("")
    print("==========================================")
    print("🌐 INSTAGRAM PAGE")
    print("==========================================")

    response = session.get(
        url,
        headers=headers,
        timeout=30,
        allow_redirects=True
    )

    response.raise_for_status()

    print(
        "Instagram status:",
        response.status_code
    )

    print(
        "Instagram URL:",
        response.url
    )

    print(
        "HTML size:",
        len(response.text)
    )

    return response.text, session, headers


# ==========================================
# IMAGE PARSER
# ==========================================

def get_instagram_images(url, folder):

    page, session, headers = get_instagram_page(url)

    image_urls = []

    patterns = [

        r'"display_url"\s*:\s*"([^"]+)"',

        r'"thumbnail_src"\s*:\s*"([^"]+)"',

        r'"image_versions2"\s*:\s*\{.*?"url"\s*:\s*"([^"]+)"',
    ]

    for pattern in patterns:

        matches = re.findall(
            pattern,
            page,
            flags=re.DOTALL
        )

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

                    image_urls.append(
                        image_url
                    )

    # OpenGraph image
    og_matches = re.findall(

        r'<meta[^>]+property=["\']og:image["\']'
        r'[^>]+content=["\']([^"\']+)',

        page,

        flags=re.IGNORECASE
    )

    for raw in og_matches:

        image_url = clean_url(raw)

        if (
            image_url.startswith("http")
            and image_url not in image_urls
        ):

            image_urls.append(
                image_url
            )

    # Remove duplicates
    unique_urls = []

    seen = set()

    for image_url in image_urls:

        base = image_url.split("?")[0]

        if base not in seen:

            seen.add(base)

            unique_urls.append(
                image_url
            )

    print("")
    print("📸 Found image URLs:", len(unique_urls))

    downloaded = []

    for index, image_url in enumerate(
        unique_urls,
        start=1
    ):

        try:

            print(
                f"📥 Downloading image {index}"
            )

            image_response = session.get(

                image_url,

                headers=headers,

                timeout=30
            )

            image_response.raise_for_status()

            content_type = (
                image_response
                .headers
                .get(
                    "Content-Type",
                    ""
                )
                .lower()
            )

            if "image" not in content_type:

                print(
                    f"⚠️ Image {index} skipped: "
                    f"{content_type}"
                )

                continue

            extension = ".jpg"

            if "png" in content_type:

                extension = ".png"

            elif "webp" in content_type:

                extension = ".webp"

            filename = os.path.join(

                folder,

                f"image_{index}{extension}"
            )

            with open(
                filename,
                "wb"
            ) as file:

                file.write(
                    image_response.content
                )

            downloaded.append(
                filename
            )

            print(
                f"✅ Image {index} saved"
            )

        except Exception as error:

            print(
                f"❌ Image {index} error:",
                repr(error)
            )

    print(
        "📸 Total downloaded images:",
        len(downloaded)
    )

    return downloaded


# ==========================================
# MEDIA DOWNLOAD
# ==========================================

def download_media(url, folder):

    # --------------------------------------
    # REEL
    # --------------------------------------

    if is_reel_url(url):

        print("")
        print("🎬 Instagram REEL detected")

        try:

            video = download_video(
                url,
                folder
            )

            if video:

                return [video]

        except Exception as error:

            print("")
            print("❌ REEL VIDEO ERROR")
            print(
                "❌ Error type:",
                type(error).__name__
            )
            print(
                "❌ Error:",
                repr(error)
            )

        # IMPORTANT:
        # Reel does NOT fall back to image
        return []


    # --------------------------------------
    # POST
    # --------------------------------------

    print("")
    print("📌 Instagram POST detected")

    # Try video first
    try:

        video = download_video(
            url,
            folder
        )

        if video:

            return [video]

    except Exception as error:

        print(
            "⚠️ Post video error:",
            repr(error)
        )


    # Try images
    try:

        images = get_instagram_images(
            url,
            folder
        )

        if images:

            return images

    except Exception as error:

        print(
            "❌ Image parser error:",
            repr(error)
        )


    return []


# ==========================================
# /START
# ==========================================

@dp.message(CommandStart())
async def start(message: types.Message):

    await message.answer(

        "👋 Салом!\n\n"

        "Instagram Reel ёки Post ссылкасини юборинг.\n\n"

        "🎥 Видео\n"
        "📸 Расм\n"
        "🖼 Carousel\n\n"

        "ҳаммасини юклаб бераман."
    )


# ==========================================
# MEDIA MESSAGE
# ==========================================

@dp.message()
async def get_media(
    message: types.Message
):

    url = (
        message.text or ""
    ).strip()

    print("")
    print("==========================================")
    print("📩 NEW MESSAGE")
    print("==========================================")
    print("URL:", url)

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
                    "Instagram ссылка очиқ бўлиши керак."
                )

                return


            await status.edit_text(
                "📤 Telegram'га юбориляпти..."
            )


            # --------------------------------
            # ONE FILE
            # --------------------------------

            if len(media_files) == 1:

                media = media_files[0]

                extension = (
                    os.path
                    .splitext(media)[1]
                    .lower()
                )

                if extension in (
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".webp"
                ):

                    await message.answer_photo(

                        photo=FSInputFile(
                            media
                        )
                    )

                else:

                    await message.answer_video(

                        video=FSInputFile(
                            media
                        )
                    )


            # --------------------------------
            # MULTIPLE FILES
            # --------------------------------

            else:

                media_group = []

                for media in media_files:

                    extension = (
                        os.path
                        .splitext(media)[1]
                        .lower()
                    )

                    if extension in (
                        ".jpg",
                        ".jpeg",
                        ".png",
                        ".webp"
                    ):

                        media_group.append(

                            InputMediaPhoto(

                                media=FSInputFile(
                                    media
                                )
                            )
                        )

                    else:

                        media_group.append(

                            InputMediaVideo(

                                media=FSInputFile(
                                    media
                                )
                            )
                        )


                # Telegram album limit = 10
                for i in range(
                    0,
                    len(media_group),
                    10
                ):

                    batch = media_group[
                        i:i + 10
                    ]

                    await message.answer_media_group(
                        media=batch
                    )


            # Delete loading message
            try:

                await status.delete()

            except Exception:

                pass


        except Exception as error:

            print("")
            print("==========================================")
            print("❌ MAIN ERROR")
            print("==========================================")
            print(
                "❌ Error type:",
                type(error).__name__
            )
            print(
                "❌ Error:",
                repr(error)
            )


            try:

                await status.edit_text(
                    "❌ Юклашда хатолик бўлди."
                )

            except Exception:

                pass


# ==========================================
# MAIN
# ==========================================

async def main():

    bot = Bot(
        token=BOT_TOKEN
    )

    # Render web server
    threading.Thread(
        target=start_server,
        daemon=True
    ).start()

    print("")
    print("==========================================")
    print("🤖 BOT STARTING")
    print("==========================================")

    # Remove old Telegram updates
    try:

        await bot.delete_webhook(
            drop_pending_updates=True
        )

        print(
            "🧹 Old Telegram updates cleared"
        )

    except Exception as error:

        print(
            "⚠️ Could not clear updates:",
            repr(error)
        )

    print("🤖 Bot ishga tushdi!")

    try:

        await dp.start_polling(
            bot,
            handle_signals=True
        )

    finally:

        await bot.session.close()


# ==========================================
# RUN
# ==========================================

if __name__ == "__main__":

    try:

        asyncio.run(main())

    except KeyboardInterrupt:

        print(
            "🛑 Bot stopped"
        )

    except Exception as error:

        print("")
        print("==========================================")
        print("💥 FATAL ERROR")
        print("==========================================")
        print(
            "Type:",
            type(error).__name__
        )
        print(
            "Error:",
            repr(error)
        )
