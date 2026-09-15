import asyncio
import html
import os
import re
import subprocess
import tempfile
import threading
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import unquote, urlparse

import requests
import yt_dlp
import instaloader

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import (
    FSInputFile,
    InputMediaPhoto,
    InputMediaVideo,
)


# =========================================================
# BOT TOKEN
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi")


dp = Dispatcher()


# =========================================================
# RENDER HEALTH SERVER
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
        ("0.0.0.0", port),
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

    return bool(
        re.search(
            r"instagram\.com/(reel|reels)/",
            url,
            re.IGNORECASE
        )
    )


# =========================================================
# SHORTCODE
# =========================================================

def get_shortcode(url):

    try:

        parsed = urlparse(url)

        parts = [
            x
            for x in parsed.path.split("/")
            if x
        ]

        if (
            len(parts) >= 2
            and parts[0].lower()
            in ("p", "reel", "reels", "tv")
        ):

            return parts[1]

    except Exception as error:

        print(
            "❌ Shortcode error:",
            repr(error),
            flush=True
        )

    return None


# =========================================================
# CLEAN URL
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

        value = html.unescape(value)

        value = unquote(value)

        return value

    except Exception:

        return raw


# =========================================================
# VIDEO DOWNLOAD
# =========================================================

def download_video(url, folder):

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

    try:

        with yt_dlp.YoutubeDL(options) as ydl:

            ydl.download([url])

    except Exception as error:

        print(
            "❌ YT-DLP ERROR:",
            repr(error),
            flush=True
        )

        traceback.print_exc()

        raise

    files = os.listdir(folder)

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

        if os.path.isfile(filepath):

            size = os.path.getsize(
                filepath
            )

            print(
                f"📦 Video size: {size}",
                flush=True
            )

            if size > 0:

                return filepath

    return None


# =========================================================
# FFMPEG CHECK
# =========================================================

def check_ffmpeg():

    try:

        result = subprocess.run(
            [
                "ffmpeg",
                "-version"
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        if result.returncode == 0:

            first_line = (
                result.stdout
                .splitlines()[0]
                if result.stdout
                else "FFmpeg"
            )

            print(
                "✅ FFmpeg:",
                first_line,
                flush=True
            )

            return True

    except Exception as error:

        print(
            "❌ FFmpeg not found:",
            repr(error),
            flush=True
        )

    return False


# =========================================================
# CONVERT VIDEO FOR TELEGRAM
# =========================================================

def convert_video_for_telegram(
    input_file,
    folder
):

    output_file = os.path.join(
        folder,
        "telegram_video.mp4"
    )

    print(
        "",
        flush=True
    )

    print(
        "========================================",
        flush=True
    )

    print(
        "🎬 CONVERTING VIDEO FOR TELEGRAM",
        flush=True
    )

    print(
        "========================================",
        flush=True
    )

    print(
        "📥 Input:",
        input_file,
        flush=True
    )

    print(
        "📤 Output:",
        output_file,
        flush=True
    )

    command = [

        "ffmpeg",

        "-y",

        "-i",
        input_file,

        # -------------------------
        # VIDEO
        # -------------------------

        "-c:v",
        "libx264",

        "-preset",
        "veryfast",

        "-crf",
        "23",

        "-pix_fmt",
        "yuv420p",

        # -------------------------
        # AUDIO
        # -------------------------

        "-c:a",
        "aac",

        "-b:a",
        "128k",

        # -------------------------
        # TELEGRAM / WEB
        # -------------------------

        "-movflags",
        "+faststart",

        output_file
    ]

    try:

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        if result.returncode != 0:

            print(
                "❌ FFmpeg ERROR:",
                flush=True
            )

            print(
                result.stderr,
                flush=True
            )

            return input_file

        if os.path.exists(
            output_file
        ):

            size = os.path.getsize(
                output_file
            )

            print(
                "✅ Converted video size:",
                size,
                flush=True
            )

            if size > 0:

                return output_file

    except Exception as error:

        print(
            "❌ FFmpeg exception:",
            repr(error),
            flush=True
        )

        traceback.print_exc()

    print(
        "⚠️ Original video will be used.",
        flush=True
    )

    return input_file


# =========================================================
# INSTAGRAM PAGE
# =========================================================

def get_instagram_page(url):

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

    response = session.get(
        url,
        headers=headers,
        timeout=30,
        allow_redirects=True
    )

    print(
        "📡 Instagram status:",
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

    if response.status_code != 200:

        raise RuntimeError(
            f"Instagram HTTP {response.status_code}"
        )

    # MUHIM:
    # response.text qaytariladi
    return (
        response.text,
        session,
        headers
    )


# =========================================================
# EXTRACT IMAGE URLS
# =========================================================

def extract_image_urls(page):

    image_urls = []

    patterns = [

        r'"display_url"\s*:\s*"([^"]+)"',

        r'"thumbnail_src"\s*:\s*"([^"]+)"',

        r'"image_url"\s*:\s*"([^"]+)"',

        r'"url"\s*:\s*"([^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"',
    ]

    for pattern in patterns:

        matches = re.findall(
            pattern,
            page,
            flags=re.IGNORECASE | re.DOTALL
        )

        print(
            "🔎 Image pattern:",
            len(matches),
            flush=True
        )

        for raw in matches:

            image_url = clean_url(raw)

            if not image_url.startswith(
                "http"
            ):
                continue

            if (
                "scontent" not in image_url
                and
                "cdninstagram" not in image_url
                and
                not re.search(
                    r"\.(jpg|jpeg|png|webp)",
                    image_url,
                    re.IGNORECASE
                )
            ):
                continue

            if image_url not in image_urls:

                image_urls.append(
                    image_url
                )

    # OG IMAGE

    og_patterns = [

        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',

        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image',
    ]

    for pattern in og_patterns:

        matches = re.findall(
            pattern,
            page,
            flags=re.IGNORECASE
        )

        for raw in matches:

            image_url = clean_url(raw)

            if (
                image_url.startswith("http")
                and image_url not in image_urls
            ):

                image_urls.append(
                    image_url
                )

    # UNIQUE

    unique = []

    seen = set()

    for image_url in image_urls:

        base = image_url.split(
            "?",
            1
        )[0]

        if base not in seen:

            seen.add(base)

            unique.append(
                image_url
            )

    return unique


# =========================================================
# DOWNLOAD IMAGE URLS
# =========================================================

def download_image_urls(
    image_urls,
    session,
    headers,
    folder
):

    downloaded = []

    for index, image_url in enumerate(
        image_urls,
        start=1
    ):

        try:

            print(
                f"📥 Downloading image {index}",
                flush=True
            )

            response = session.get(
                image_url,
                headers=headers,
                timeout=30
            )

            response.raise_for_status()

            content_type = (
                response.headers
                .get(
                    "Content-Type",
                    ""
                )
                .lower()
            )

            if "image" not in content_type:

                print(
                    f"⚠️ Not image: {content_type}",
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
                f"❌ Image {index} error:",
                repr(error),
                flush=True
            )

    return downloaded


# =========================================================
# IMAGE METHOD 1 — REQUESTS
# =========================================================

def get_images_requests(
    url,
    folder
):

    print(
        "",
        flush=True
    )

    print(
        "🌐 IMAGE METHOD 1: REQUESTS",
        flush=True
    )

    page, session, headers = (
        get_instagram_page(url)
    )

    image_urls = extract_image_urls(
        page
    )

    print(
        "📸 Found image URLs:",
        len(image_urls),
        flush=True
    )

    if not image_urls:

        return []

    return download_image_urls(
        image_urls,
        session,
        headers,
        folder
    )


# =========================================================
# IMAGE METHOD 2 — INSTALOADER
# =========================================================

def get_images_instaloader(
    url,
    folder
):

    print(
        "",
        flush=True
    )

    print(
        "========================================",
        flush=True
    )

    print(
        "📸 IMAGE METHOD 2: INSTALOADER",
        flush=True
    )

    print(
        "========================================",
        flush=True
    )

    shortcode = get_shortcode(
        url
    )

    if not shortcode:

        print(
            "❌ Shortcode topilmadi",
            flush=True
        )

        return []

    print(
        "🔑 Shortcode:",
        shortcode,
        flush=True
    )

    loader = instaloader.Instaloader(

        download_pictures=True,

        download_videos=False,

        download_video_thumbnails=False,

        download_geotags=False,

        download_comments=False,

        save_metadata=False,

        compress_json=False,

        post_metadata_txt_pattern=""
    )

    try:

        post = (
            instaloader.Post
            .from_shortcode(
                loader.context,
                shortcode
            )
        )

        print(
            "📌 Post type:",
            post.typename,
            flush=True
        )

        downloaded = []

        # -----------------------------------------
        # CAROUSEL
        # -----------------------------------------

        if post.typename == "GraphSidecar":

            nodes = list(
                post.get_sidecar_nodes()
            )

            print(
                "🖼 Carousel items:",
                len(nodes),
                flush=True
            )

            for index, node in enumerate(
                nodes,
                start=1
            ):

                try:

                    if node.is_video:

                        print(
                            f"⏭ Item {index} is video",
                            flush=True
                        )

                        continue

                    image_url = (
                        node.display_url
                    )

                    filename = os.path.join(
                        folder,
                        f"image_{index}.jpg"
                    )

                    response = requests.get(

                        image_url,

                        headers={
                            "User-Agent": (
                                "Mozilla/5.0 "
                                "(Windows NT 10.0; Win64; x64) "
                                "AppleWebKit/537.36 "
                                "(KHTML, like Gecko) "
                                "Chrome/140.0.0.0 "
                                "Safari/537.36"
                            )
                        },

                        timeout=30
                    )

                    response.raise_for_status()

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
                            f"✅ Carousel image {index} saved",
                            flush=True
                        )

                except Exception as error:

                    print(
                        f"❌ Carousel {index}:",
                        repr(error),
                        flush=True
                    )

        # -----------------------------------------
        # SINGLE IMAGE
        # -----------------------------------------

        else:

            if post.is_video:

                print(
                    "⚠️ Post is video",
                    flush=True
                )

                return []

            image_url = post.url

            filename = os.path.join(
                folder,
                "image_1.jpg"
            )

            response = requests.get(

                image_url,

                headers={
                    "User-Agent": (
                        "Mozilla/5.0 "
                        "(Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 "
                        "(KHTML, like Gecko) "
                        "Chrome/140.0.0.0 "
                        "Safari/537.36"
                    )
                },

                timeout=30
            )

            response.raise_for_status()

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
            "📸 Instaloader downloaded:",
            len(downloaded),
            flush=True
        )

        return downloaded

    except Exception as error:

        print(
            "❌ INSTALOADER ERROR:",
            type(error).__name__,
            flush=True
        )

        print(
            "❌",
            repr(error),
            flush=True
        )

        traceback.print_exc()

        return []


# =========================================================
# GET INSTAGRAM IMAGES
# =========================================================

def get_instagram_images(
    url,
    folder
):

    try:

        images = get_images_requests(
            url,
            folder
        )

        if images:

            return images

    except Exception as error:

        print(
            "⚠️ Requests image method failed:",
            repr(error),
            flush=True
        )

    try:

        images = get_images_instaloader(
            url,
            folder
        )

        if images:

            return images

    except Exception as error:

        print(
            "⚠️ Instaloader failed:",
            repr(error),
            flush=True
        )

    return []


# =========================================================
# DOWNLOAD MEDIA
# =========================================================

def download_media(
    url,
    folder
):

    # =====================================================
    # REEL
    # =====================================================

    if is_reel_url(url):

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

                # MUHIM:
                # Telegram uchun qayta encode

                video = (
                    convert_video_for_telegram(
                        video,
                        folder
                    )
                )

                return [video]

        except Exception as error:

            print(
                "❌ Reel video error:",
                repr(error),
                flush=True
            )

            traceback.print_exc()

        return []


    # =====================================================
    # POST
    # =====================================================

    print(
        "",
        flush=True
    )

    print(
        "📌 POST DETECTED",
        flush=True
    )

    # Avval video sifatida urinadi

    try:

        video = download_video(
            url,
            folder
        )

        if video:

            video = (
                convert_video_for_telegram(
                    video,
                    folder
                )
            )

            return [video]

    except Exception as error:

        print(
            "⚠️ Post video method failed:",
            repr(error),
            flush=True
        )


    # Keyin rasmlar

    try:

        images = get_instagram_images(
            url,
            folder
        )

        if images:

            return images

    except Exception as error:

        print(
            "❌ Image methods failed:",
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

        "Instagram Reel ёки Post ссылкаси юборинг.\n\n"

        "🎥 Видео\n"
        "📸 Расм\n"
        "🖼 Carousel\n\n"

        "ҳаммасини юклаб бераман."
    )


# =========================================================
# MAIN MESSAGE HANDLER
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

    # -----------------------------------------
    # URL CHECK
    # -----------------------------------------

    if not is_instagram_url(url):

        await message.answer(
            "❌ Instagram ссылкаси юборинг."
        )

        return


    # -----------------------------------------
    # STATUS
    # -----------------------------------------

    status = await message.answer(
        "⏳ Юкланяпти..."
    )


    # -----------------------------------------
    # TEMP FOLDER
    # -----------------------------------------

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


            # -------------------------------------
            # NOTHING FOUND
            # -------------------------------------

            if not media_files:

                await status.edit_text(

                    "❌ Медиафайлни топа олмадим.\n\n"

                    "Instagram ссылка очиқ бўлиши керак."
                )

                return


            # -------------------------------------
            # UPLOAD
            # -------------------------------------

            await status.edit_text(
                "📤 Telegram'га юбориляпти..."
            )


            # =====================================
            # ONE FILE
            # =====================================

            if len(media_files) == 1:

                media = media_files[0]

                extension = (
                    os.path.splitext(
                        media
                    )[1].lower()
                )


                # ---------------------------------
                # IMAGE
                # ---------------------------------

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


                # ---------------------------------
                # VIDEO
                # ---------------------------------

                else:

                    await message.answer_video(

                        video=FSInputFile(
                            media
                        ),

                        supports_streaming=True
                    )


            # =====================================
            # MULTIPLE FILES
            # =====================================

            else:

                media_group = []


                for media in media_files:

                    extension = (
                        os.path.splitext(
                            media
                        )[1].lower()
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


                # Telegram maximum:
                # 10 media per album

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


            # -------------------------------------
            # DELETE STATUS
            # -------------------------------------

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


    # -----------------------------------------
    # FFmpeg check
    # -----------------------------------------

    check_ffmpeg()


    # -----------------------------------------
    # Render server
    # -----------------------------------------

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


    # -----------------------------------------
    # Telegram webhook clear
    # -----------------------------------------

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
            "⚠️ Could not clear updates:",
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
