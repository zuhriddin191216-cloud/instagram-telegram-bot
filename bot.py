import asyncio
import html
import os
import re
import tempfile
import threading
import traceback
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


# =========================================================
# SETTINGS
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi")

dp = Dispatcher()


# =========================================================
# RENDER WEB SERVER
# =========================================================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):

        self.send_response(200)

        self.send_header(
            "Content-Type",
            "text/plain; charset=utf-8"
        )

        self.end_headers()

        self.wfile.write(
            b"Instagram Telegram Bot is running!"
        )

    def log_message(self, format, *args):
        pass


def start_server():

    port = int(
        os.getenv(
            "PORT",
            "10000"
        )
    )

    server = HTTPServer(
        (
            "0.0.0.0",
            port
        ),
        HealthHandler
    )

    print(
        f"🌐 Render web server started on port {port}",
        flush=True
    )

    server.serve_forever()


# =========================================================
# INSTAGRAM URL
# =========================================================

def is_instagram_url(text):

    if not text:
        return False

    pattern = (
        r"https?://"
        r"(www\.)?"
        r"instagram\.com/"
        r"(reel|reels|p|tv)/"
    )

    return re.search(
        pattern,
        text,
        re.IGNORECASE
    )


def is_reel_url(url):

    pattern = (
        r"instagram\.com/"
        r"(reel|reels)/"
    )

    return re.search(
        pattern,
        url,
        re.IGNORECASE
    )


# =========================================================
# URL CLEAN
# =========================================================

def clean_url(raw):

    try:

        value = raw

        value = value.replace(
            "\\/",
            "/"
        )

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

        value = value.replace(
            "\\u002F",
            "/"
        )

        value = html.unescape(
            value
        )

        value = unquote(
            value
        )

        return value

    except Exception:

        return raw


# =========================================================
# VIDEO DOWNLOAD
# =========================================================

def download_video(
    url,
    folder
):

    output = os.path.join(
        folder,
        "video.%(ext)s"
    )

    options = {

        "outtmpl": output,

        "format": (
            "bestvideo[ext=mp4]+"
            "bestaudio[ext=m4a]/"
            "best[ext=mp4]/"
            "best"
        ),

        "merge_output_format": "mp4",

        "noplaylist": True,

        "quiet": False,

        "no_warnings": False,

        "socket_timeout": 30,

        "retries": 3,

        "fragment_retries": 3,

        "continuedl": True,

        "overwrites": True,

        "impersonate": "chrome",

        "http_headers": {

            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/140.0.0.0 "
                "Safari/537.36"
            ),

            "Accept-Language":
                "en-US,en;q=0.9",

            "Referer":
                "https://www.instagram.com/",
        },
    }

    print(
        "",
        flush=True
    )

    print(
        "========================================",
        flush=True
    )

    print(
        "🎥 VIDEO DOWNLOAD",
        flush=True
    )

    print(
        "========================================",
        flush=True
    )

    print(
        "🔗 URL:",
        url,
        flush=True
    )

    print(
        "⚙️ yt-dlp starting...",
        flush=True
    )

    try:

        with yt_dlp.YoutubeDL(
            options
        ) as ydl:

            ydl.download(
                [url]
            )

    except Exception as error:

        print(
            "",
            flush=True
        )

        print(
            "❌ YT-DLP ERROR",
            flush=True
        )

        print(
            "❌ Error type:",
            type(error).__name__,
            flush=True
        )

        print(
            "❌ Error:",
            repr(error),
            flush=True
        )

        print(
            "❌ Full traceback:",
            flush=True
        )

        traceback.print_exc()

        print(
            "",
            flush=True
        )

        raise


    files = os.listdir(
        folder
    )

    print(
        "📁 Folder files:",
        files,
        flush=True
    )

    for filename in files:

        if not filename.startswith(
            "video."
        ):
            continue

        filepath = os.path.join(
            folder,
            filename
        )

        if os.path.isfile(
            filepath
        ):

            size = os.path.getsize(
                filepath
            )

            print(
                f"✅ VIDEO FOUND: {filepath}",
                flush=True
            )

            print(
                f"📦 File size: {size} bytes",
                flush=True
            )

            if size > 0:

                return filepath


    print(
        "❌ Video file not found",
        flush=True
    )

    return None


# =========================================================
# INSTAGRAM PAGE
# =========================================================

def get_instagram_page(
    url
):

    headers = {

        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/140.0.0.0 "
            "Safari/537.36"
        ),

        "Accept": (
            "text/html,"
            "application/xhtml+xml,"
            "application/xml;q=0.9,"
            "image/avif,"
            "image/webp,"
            "*/*;q=0.8"
        ),

        "Accept-Language":
            "en-US,en;q=0.9",

        "Referer":
            "https://www.instagram.com/",
    }

    session = requests.Session()

    print(
        "",
        flush=True
    )

    print(
        "========================================",
        flush=True
    )

    print(
        "🌐 INSTAGRAM PAGE REQUEST",
        flush=True
    )

    print(
        "========================================",
        flush=True
    )

    print(
        "🔗 URL:",
        url,
        flush=True
    )

    response = session.get(

        url,

        headers=headers,

        timeout=30,

        allow_redirects=True
    )

    print(
        "📡 Status:",
        response.status_code,
        flush=True
    )

    print(
        "🔗 Final URL:",
        response.url,
        flush=True
    )

    print(
        "📄 HTML size:",
        len(response.text),
        flush=True
    )

    response.raise_for_status()

    return (
        response.text,
        session,
        headers
    )


# =========================================================
# IMAGE DOWNLOAD
# =========================================================

def get_instagram_images(
    url,
    folder
):

    page, session, headers = (
        get_instagram_page(
            url
        )
    )

    image_urls = []


    patterns = [

        r'"display_url"\s*:\s*"([^"]+)"',

        r'"thumbnail_src"\s*:\s*"([^"]+)"',

        (
            r'"image_versions2"\s*:\s*\{'
            r'.*?"url"\s*:\s*"([^"]+)"'
        ),
    ]


    for pattern in patterns:

        matches = re.findall(

            pattern,

            page,

            flags=re.DOTALL
        )

        print(
            "🔎 Pattern found:",
            len(matches),
            flush=True
        )


        for raw in matches:

            image_url = clean_url(
                raw
            )

            if not image_url.startswith(
                "http"
            ):
                continue

            if not (
                "scontent" in image_url
                or
                "cdninstagram" in image_url
                or
                ".jpg" in image_url
                or
                ".jpeg" in image_url
                or
                ".png" in image_url
                or
                ".webp" in image_url
            ):
                continue

            if image_url not in image_urls:

                image_urls.append(
                    image_url
                )


    # OpenGraph image
    og_matches = re.findall(

        (
            r'<meta[^>]+'
            r'property=["\']og:image["\']'
            r'[^>]+'
            r'content=["\']([^"\']+)'
        ),

        page,

        flags=re.IGNORECASE
    )


    for raw in og_matches:

        image_url = clean_url(
            raw
        )

        if (
            image_url.startswith("http")
            and
            image_url not in image_urls
        ):

            image_urls.append(
                image_url
            )


    # Remove duplicates
    unique_urls = []

    seen = set()

    for image_url in image_urls:

        base = image_url.split(
            "?",
            1
        )[0]

        if base not in seen:

            seen.add(
                base
            )

            unique_urls.append(
                image_url
            )


    print(
        "📸 Found image URLs:",
        len(unique_urls),
        flush=True
    )


    downloaded = []


    for index, image_url in enumerate(
        unique_urls,
        start=1
    ):

        try:

            print(
                f"📥 Image {index} downloading...",
                flush=True
            )

            response = session.get(

                image_url,

                headers=headers,

                timeout=30
            )

            response.raise_for_status()

            content_type = (
                response
                .headers
                .get(
                    "Content-Type",
                    ""
                )
                .lower()
            )

            print(
                f"📡 Image {index} type:",
                content_type,
                flush=True
            )


            if "image" not in content_type:

                print(
                    f"⚠️ Image {index} skipped",
                    flush=True
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
                    response.content
                )


            if os.path.getsize(
                filename
            ) > 0:

                downloaded.append(
                    filename
                )

                print(
                    f"✅ Image {index} saved",
                    flush=True
                )


        except Exception as error:

            print(
                f"❌ Image {index} ERROR:",
                repr(error),
                flush=True
            )


    print(
        "📸 Total downloaded images:",
        len(downloaded),
        flush=True
    )

    return downloaded


# =========================================================
# DOWNLOAD MEDIA
# =========================================================

def download_media(
    url,
    folder
):

    # =====================================
    # REEL
    # =====================================

    if is_reel_url(
        url
    ):

        print(
            "",
            flush=True
        )

        print(
            "🎬 REEL DETECTED",
            flush=True
        )

        try:

            video = download_video(
                url,
                folder
            )

            if video:

                return [video]

        except Exception as error:

            print(
                "",
                flush=True
            )

            print(
                "❌ REEL VIDEO ERROR",
                flush=True
            )

            print(
                "❌ Error type:",
                type(error).__name__,
                flush=True
            )

            print(
                "❌ Error:",
                repr(error),
                flush=True
            )

            traceback.print_exc()


        # Reel uchun rasm fallback YO'Q
        return []


    # =====================================
    # POST
    # =====================================

    print(
        "",
        flush=True
    )

    print(
        "📌 POST DETECTED",
        flush=True
    )


    # First try video
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
            repr(error),
            flush=True
        )


    # Then images
    try:

        images = get_instagram_images(
            url,
            folder
        )

        if images:

            return images

    except Exception as error:

        print(
            "❌ Image parser ERROR:",
            repr(error),
            flush=True
        )

        traceback.print_exc()


    return []


# =========================================================
# /START
# =========================================================

@dp.message(
    CommandStart()
)
async def start(
    message: types.Message
):

    await message.answer(

        "👋 Салом!\n\n"

        "Instagram Reel ёки Post "
        "ссылкаси юборинг.\n\n"

        "🎥 Видео\n"
        "📸 Расм\n"
        "🖼 Carousel\n\n"

        "ҳаммасини юклаб бераман."
    )


# =========================================================
# MESSAGE HANDLER
# =========================================================

@dp.message()
async def get_media(
    message: types.Message
):

    url = (
        message.text or ""
    ).strip()


    print(
        "",
        flush=True
    )

    print(
        "========================================",
        flush=True
    )

    print(
        "📩 NEW TELEGRAM MESSAGE",
        flush=True
    )

    print(
        "========================================",
        flush=True
    )

    print(
        "🔗 URL:",
        url,
        flush=True
    )


    if not is_instagram_url(
        url
    ):

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


            print(
                "📦 MEDIA FILES:",
                media_files,
                flush=True
            )


            # =================================
            # NOTHING FOUND
            # =================================

            if not media_files:

                await status.edit_text(

                    "❌ Медиафайлни топа олмадим.\n\n"
                    "Instagram ссылка очиқ бўлиши керак."
                )

                return


            # =================================
            # UPLOAD
            # =================================

            await status.edit_text(
                "📤 Telegram'га юбориляпти..."
            )


            # =================================
            # ONE FILE
            # =================================

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


            # =================================
            # MULTIPLE FILES
            # =================================

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


                # Telegram maximum = 10
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

            print(
                "",
                flush=True
            )

            print(
                "========================================",
                flush=True
            )

            print(
                "💥 MAIN ERROR",
                flush=True
            )

            print(
                "========================================",
                flush=True
            )

            print(
                "❌ Error type:",
                type(error).__name__,
                flush=True
            )

            print(
                "❌ Error:",
                repr(error),
                flush=True
            )

            traceback.print_exc()


            try:

                await status.edit_text(

                    "❌ Юклашда хатолик бўлди."
                )

            except Exception:

                pass


# =========================================================
# MAIN
# =========================================================

async def main():

    bot = Bot(
        token=BOT_TOKEN
    )


    # Render web server
    threading.Thread(

        target=start_server,

        daemon=True

    ).start()


    print(
        "",
        flush=True
    )

    print(
        "========================================",
        flush=True
    )

    print(
        "🤖 BOT STARTING",
        flush=True
    )

    print(
        "========================================",
        flush=True
    )


    # Clear old Telegram updates
    try:

        await bot.delete_webhook(

            drop_pending_updates=True
        )

        print(
            "🧹 Old Telegram updates cleared",
            flush=True
        )

    except Exception as error:

        print(
            "⚠️ Could not clear Telegram updates:",
            repr(error),
            flush=True
        )


    print(
        "🤖 Bot ishga tushdi!",
        flush=True
    )


    try:

        await dp.start_polling(

            bot,

            handle_signals=True
        )

    finally:

        await bot.session.close()


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        print(
            "🛑 Bot stopped",
            flush=True
        )

    except Exception as error:

        print(
            "",
            flush=True
        )

        print(
            "========================================",
            flush=True
        )

        print(
            "💥 FATAL ERROR",
            flush=True
        )

        print(
            "========================================",
            flush=True
        )

        print(
            "❌ Error type:",
            type(error).__name__,
            flush=True
        )

        print(
            "❌ Error:",
            repr(error),
            flush=True
        )

        traceback.print_exc()
