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

    print("")
    print("========================================")
    print("🎥 VIDEO DOWNLOAD")
    print("========================================")
    print("🔗 URL:", url, flush=True)

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

        "socket_timeout": 30,

        "retries": 3,

        "fragment_retries": 3,

        "continuedl": True,

        "overwrites": True,

        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/140.0.0.0 Safari/537.36"
            ),

            "Accept-Language": "en-US,en;q=0.9",

            "Referer": "https://www.instagram.com/",
        },
    }

    try:

        with yt_dlp.YoutubeDL(options) as ydl:

            ydl.download([url])

        files = os.listdir(folder)

        print(
            "📁 Folder files:",
            files,
            flush=True
        )

        video_files = []

        for filename in files:

            full_path = os.path.join(
                folder,
                filename
            )

            if not os.path.isfile(full_path):
                continue

            lower = filename.lower()

            if lower.endswith(
                (
                    ".mp4",
                    ".mov",
                    ".mkv",
                    ".webm"
                )
            ):

                video_files.append(
                    full_path
                )

        if not video_files:

            print(
                "❌ Video file topilmadi",
                flush=True
            )

            return None

        video = max(
            video_files,
            key=os.path.getsize
        )

        print(
            "📦 Video:",
            video,
            flush=True
        )

        print(
            "📦 Video size:",
            os.path.getsize(video),
            flush=True
        )

        return video

    except Exception as error:

        print(
            "❌ Video download error:",
            repr(error),
            flush=True
        )

        traceback.print_exc()

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
            text=True,
            timeout=10
        )

        first_line = (
            result.stdout.splitlines()[0]
            if result.stdout
            else "FFmpeg mavjud"
        )

        print(
            "✅ FFmpeg:",
            first_line,
            flush=True
        )

        return True

    except Exception as error:

        print(
            "❌ FFmpeg topilmadi:",
            repr(error),
            flush=True
        )

        return False


# =========================================================
# VIDEO CODEC
# =========================================================

def get_video_codecs(video):

    video_codec = None
    audio_codec = None

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
                video
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10
        )

        if result.stdout.strip():

            video_codec = (
                result.stdout
                .strip()
                .splitlines()[0]
                .lower()
            )

    except Exception as error:

        print(
            "⚠️ Video codec aniqlanmadi:",
            repr(error),
            flush=True
        )

    try:

        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=codec_name",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                video
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10
        )

        if result.stdout.strip():

            audio_codec = (
                result.stdout
                .strip()
                .splitlines()[0]
                .lower()
            )

    except Exception as error:

        print(
            "⚠️ Audio codec aniqlanmadi:",
            repr(error),
            flush=True
        )

    print(
        "🎞 Video codec:",
        video_codec,
        flush=True
    )

    print(
        "🔊 Audio codec:",
        audio_codec,
        flush=True
    )

    return video_codec, audio_codec


# =========================================================
# CONVERT VIDEO FOR TELEGRAM
# =========================================================

def convert_video_for_telegram(video):

    print("")
    print("========================================")
    print("🎬 PREPARING VIDEO FOR TELEGRAM")
    print("========================================")

    if not video or not os.path.exists(video):

        print(
            "❌ Video mavjud emas",
            flush=True
        )

        return None

    output = os.path.join(
        os.path.dirname(video),
        "telegram_video.mp4"
    )

    video_codec, audio_codec = get_video_codecs(
        video
    )

    # -----------------------------------------------------
    # H.264 + AAC bo'lsa, qayta kodlamaymiz
    # -----------------------------------------------------

    compatible_video = (
        video_codec == "h264"
    )

    compatible_audio = (
        audio_codec in (
            "aac",
            "mp4a"
        )
    )

    if compatible_video and compatible_audio:

        print(
            "⚡ Video Telegram uchun mos.",
            flush=True
        )

        print(
            "⚡ Faqat remux qilamiz...",
            flush=True
        )

        try:

            result = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    video,
                    "-c",
                    "copy",
                    "-movflags",
                    "+faststart",
                    output
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30
            )

            if (
                result.returncode == 0
                and os.path.exists(output)
                and os.path.getsize(output) > 0
            ):

                print(
                    "✅ Remux muvaffaqiyatli",
                    flush=True
                )

                print(
                    "📦 Output size:",
                    os.path.getsize(output),
                    flush=True
                )

                return output

            print(
                "⚠️ Remux ishlamadi",
                flush=True
            )

            if result.stderr:

                print(
                    result.stderr[-2000:],
                    flush=True
                )

        except subprocess.TimeoutExpired:

            print(
                "⏱️ Remux timeout",
                flush=True
            )

        except Exception as error:

            print(
                "❌ Remux error:",
                repr(error),
                flush=True
            )

        return video

    # -----------------------------------------------------
    # Mos kelmasa H.264 + AAC ga o'tkazamiz
    # -----------------------------------------------------

    print(
        "🔄 Video qayta kodlanadi...",
        flush=True
    )

    print(
        "🎥 H.264 + AAC",
        flush=True
    )

    try:

        result = subprocess.run(
            [
                "ffmpeg",
                "-y",

                "-i",
                video,

                "-c:v",
                "libx264",

                "-preset",
                "ultrafast",

                "-crf",
                "28",

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

            stdout=subprocess.PIPE,

            stderr=subprocess.PIPE,

            text=True,

            timeout=90
        )

        if (
            result.returncode == 0
            and os.path.exists(output)
            and os.path.getsize(output) > 0
        ):

            print(
                "✅ Video conversion muvaffaqiyatli",
                flush=True
            )

            print(
                "📦 Output size:",
                os.path.getsize(output),
                flush=True
            )

            return output

        print(
            "❌ Video conversion ishlamadi",
            flush=True
        )

        if result.stderr:

            print(
                result.stderr[-3000:],
                flush=True
            )

        return video

    except subprocess.TimeoutExpired:

        print(
            "⏱️ FFmpeg 90 sekunddan oshdi",
            flush=True
        )

        return video

    except Exception as error:

        print(
            "❌ Conversion error:",
            repr(error),
            flush=True
        )

        traceback.print_exc()

        return video


# =========================================================
# INSTAGRAM PAGE
# =========================================================

def get_instagram_page(url):

    session = requests.Session()

    headers = {

        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/140.0.0.0 Safari/537.36"
        ),

        "Accept-Language": "en-US,en;q=0.9",

        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,image/avif,"
            "image/webp,*/*;q=0.8"
        ),

        "Referer": "https://www.instagram.com/",
    }

    try:

        response = session.get(
            url,
            headers=headers,
            timeout=20
        )

        print(
            "📡 Instagram status:",
            response.status_code,
            flush=True
        )

        print(
            "🌐 Final URL:",
            response.url,
            flush=True
        )

        print(
            "📄 HTML size:",
            len(response.text),
            flush=True
        )

        return (
            response.text,
            session,
            headers
        )

    except Exception as error:

        print(
            "❌ Instagram page error:",
            repr(error),
            flush=True
        )

        return (
            "",
            session,
            headers
        )


# =========================================================
# IMAGE URL EXTRACTION
# =========================================================

def extract_image_urls(html_text):

    urls = []

    if not html_text:

        return urls

    patterns = [

        r'"display_url":"([^"]+)"',

        r'"thumbnail_src":"([^"]+)"',

        r'"image_url":"([^"]+)"',

        r'"src":"(https?://[^"]+\.(?:jpg|jpeg|png)[^"]*)"',
    ]

    for pattern in patterns:

        try:

            matches = re.findall(
                pattern,
                html_text,
                re.IGNORECASE
            )

            for raw_url in matches:

                url = clean_url(raw_url)

                if url not in urls:

                    urls.append(url)

        except Exception:
            pass

    # Direct image URLs
    direct_pattern = (
        r'https?://[^"\']+'
        r'\.(?:jpg|jpeg|png)'
        r'(?:\?[^"\']*)?'
    )

    try:

        matches = re.findall(
            direct_pattern,
            html_text,
            re.IGNORECASE
        )

        for raw_url in matches:

            url = clean_url(raw_url)

            if url not in urls:

                urls.append(url)

    except Exception:
        pass

    # OG image
    try:

        og_matches = re.findall(
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
            html_text,
            re.IGNORECASE
        )

        for raw_url in og_matches:

            url = clean_url(raw_url)

            if url not in urls:

                urls.append(url)

    except Exception:
        pass

    print(
        "🖼 Found image URLs:",
        len(urls),
        flush=True
    )

    return urls


# =========================================================
# DOWNLOAD IMAGE URLS
# =========================================================

def download_image_urls(
    urls,
    session,
    headers,
    folder
):

    files = []

    for index, url in enumerate(
        urls,
        start=1
    ):

        try:

            response = session.get(
                url,
                headers=headers,
                timeout=20
            )

            if response.status_code != 200:

                print(
                    f"⚠️ Image {index}: HTTP {response.status_code}",
                    flush=True
                )

                continue

            content_type = (
                response.headers
                .get(
                    "Content-Type",
                    ""
                )
                .lower()
            )

            if (
                "image" not in content_type
                and not url.lower().endswith(
                    (
                        ".jpg",
                        ".jpeg",
                        ".png",
                        ".webp"
                    )
                )
            ):

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

            if os.path.getsize(filename) > 0:

                files.append(filename)

                print(
                    f"✅ Image {index} saved",
                    flush=True
                )

        except Exception as error:

            print(
                f"⚠️ Image {index} error:",
                repr(error),
                flush=True
            )

    return files


# =========================================================
# REQUESTS IMAGE METHOD
# =========================================================

def get_images_requests(url, folder):

    print("")
    print("========================================")
    print("🖼 INSTAGRAM IMAGE SEARCH")
    print("========================================")

    html_text, session, headers = get_instagram_page(
        url
    )

    if not html_text:

        return []

    urls = extract_image_urls(
        html_text
    )

    if not urls:

        return []

    return download_image_urls(
        urls,
        session,
        headers,
        folder
    )


# =========================================================
# INSTALOADER IMAGE METHOD
# =========================================================

def get_images_instaloader(
    url,
    folder
):

    print("")
    print("========================================")
    print("📸 INSTALOADER FALLBACK")
    print("========================================")

    shortcode = get_shortcode(
        url
    )

    if not shortcode:

        print(
            "❌ Shortcode topilmadi",
            flush=True
        )

        return []

    try:

        loader = instaloader.Instaloader(
            download_videos=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            post_metadata_txt_pattern=""
        )

        post = instaloader.Post.from_shortcode(
            loader.context,
            shortcode
        )

        files = []

        # -------------------------------------------------
        # Carousel
        # -------------------------------------------------

        if post.typename == "GraphSidecar":

            print(
                "🖼 Carousel detected",
                flush=True
            )

            index = 1

            for node in post.get_sidecar_nodes():

                if node.is_video:

                    print(
                        f"⏭ Video item {index} skipped",
                        flush=True
                    )

                    index += 1

                    continue

                image_url = node.display_url

                try:

                    response = requests.get(
                        image_url,
                        headers={
                            "User-Agent":
                                "Mozilla/5.0"
                        },
                        timeout=30
                    )

                    if response.status_code != 200:

                        index += 1
                        continue

                    filename = os.path.join(
                        folder,
                        f"image_{index}.jpg"
                    )

                    with open(
                        filename,
                        "wb"
                    ) as file:

                        file.write(
                            response.content
                        )

                    if os.path.getsize(filename) > 0:

                        files.append(
                            filename
                        )

                        print(
                            f"✅ Carousel image {index} saved",
                            flush=True
                        )

                except Exception as error:

                    print(
                        f"⚠️ Carousel image {index} error:",
                        repr(error),
                        flush=True
                    )

                index += 1

            print(
                "📸 Instaloader downloaded:",
                len(files),
                flush=True
            )

            return files

        # -------------------------------------------------
        # Single image
        # -------------------------------------------------

        if post.is_video:

            print(
                "🎥 Post is video",
                flush=True
            )

            return []

        image_url = post.url

        response = requests.get(
            image_url,
            headers={
                "User-Agent":
                    "Mozilla/5.0"
            },
            timeout=30
        )

        if response.status_code != 200:

            return []

        filename = os.path.join(
            folder,
            "image_1.jpg"
        )

        with open(
            filename,
            "wb"
        ) as file:

            file.write(
                response.content
            )

        if os.path.getsize(filename) > 0:

            print(
                "✅ Single image saved",
                flush=True
            )

            return [filename]

    except Exception as error:

        print(
            "❌ Instaloader error:",
            repr(error),
            flush=True
        )

        traceback.print_exc()

    return []


# =========================================================
# GET IMAGES
# =========================================================

def get_instagram_images(
    url,
    folder
):

    # 1. Requests
    try:

        files = get_images_requests(
            url,
            folder
        )

        if files:

            print(
                "✅ Images found using requests:",
                len(files),
                flush=True
            )

            return files

    except Exception as error:

        print(
            "⚠️ Requests image method error:",
            repr(error),
            flush=True
        )

    # 2. Instaloader fallback
    try:

        files = get_images_instaloader(
            url,
            folder
        )

        if files:

            return files

    except Exception as error:

        print(
            "⚠️ Instaloader fallback error:",
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

        print("")
        print("🎬 REEL DETECTED")

        video = download_video(
            url,
            folder
        )

        if not video:

            return []

        # Telegram uchun tayyorlash
        video = convert_video_for_telegram(
            video
        )

        if not video:

            return []

        return [video]

    # =====================================================
    # POST
    # =====================================================

    print("")
    print("📦 POST DETECTED")

    # Avval video tekshiramiz
    video = download_video(
        url,
        folder
    )

    if video:

        video = convert_video_for_telegram(
            video
        )

        if video:

            return [video]

    # Keyin rasmlar
    images = get_instagram_images(
        url,
        folder
    )

    return images


# =========================================================
# TELEGRAM UPLOAD
# =========================================================

async def send_media_to_telegram(
    message,
    media_files
):

    if not media_files:

        await message.answer(
            "❌ Media topilmadi."
        )

        return

    print("")
    print("========================================")
    print("📤 TELEGRAM UPLOAD")
    print("========================================")

    print(
        "📦 MEDIA FILES:",
        media_files,
        flush=True
    )

    # =====================================================
    # Bitta fayl
    # =====================================================

    if len(media_files) == 1:

        media = media_files[0]

        if not os.path.exists(media):

            await message.answer(
                "❌ Fayl topilmadi."
            )

            return

        size = os.path.getsize(
            media
        )

        print(
            "📦 Upload file size:",
            size,
            flush=True
        )

        lower = media.lower()

        # -------------------------------------------------
        # Video
        # -------------------------------------------------

        if lower.endswith(
            (
                ".mp4",
                ".mov",
                ".mkv",
                ".webm"
            )
        ):

            print(
                "📤 Uploading video to Telegram...",
                flush=True
            )

            try:

                await message.answer_video(
                    video=FSInputFile(
                        media
                    ),

                    supports_streaming=True,

                    caption="🎬 Instagram"
                )

                print(
                    "✅ Video uploaded to Telegram",
                    flush=True
                )

            except Exception as error:

                print(
                    "❌ Telegram video upload error:",
                    repr(error),
                    flush=True
                )

                traceback.print_exc()

                # Document sifatida yuborishga urinib ko'ramiz
                try:

                    print(
                        "📄 Trying document upload...",
                        flush=True
                    )

                    await message.answer_document(
                        document=FSInputFile(
                            media
                        ),

                        caption="🎬 Instagram video"
                    )

                    print(
                        "✅ Video sent as document",
                        flush=True
                    )

                except Exception as document_error:

                    print(
                        "❌ Document upload error:",
                        repr(document_error),
                        flush=True
                    )

                    await message.answer(
                        "❌ Videoni Telegram'га юборишда хатолик."
                    )

            return

        # -------------------------------------------------
        # Bitta rasm
        # -------------------------------------------------

        print(
            "📤 Uploading photo...",
            flush=True
        )

        try:

            await message.answer_photo(
                photo=FSInputFile(
                    media
                ),

                caption="📸 Instagram"
            )

            print(
                "✅ Photo uploaded",
                flush=True
            )

        except Exception as error:

            print(
                "❌ Photo upload error:",
                repr(error),
                flush=True
            )

        return

    # =====================================================
    # Bir nechta rasmlar
    # =====================================================

    print(
        f"📸 Sending {len(media_files)} images...",
        flush=True
    )

    # Telegram MediaGroup maksimum 10 ta
    batch_size = 10

    for start in range(
        0,
        len(media_files),
        batch_size
    ):

        batch = media_files[
            start:start + batch_size
        ]

        media_group = []

        for index, filename in enumerate(
            batch
        ):

            if not os.path.exists(filename):

                continue

            media_group.append(
                InputMediaPhoto(
                    media=FSInputFile(
                        filename
                    )
                )
            )

        if not media_group:

            continue

        try:

            print(
                f"📤 Uploading album "
                f"{start + 1}-{start + len(batch)}...",
                flush=True
            )

            await message.answer_media_group(
                media=media_group
            )

            print(
                f"✅ Album uploaded: "
                f"{start + 1}-{start + len(batch)}",
                flush=True
            )

        except Exception as error:

            print(
                "❌ Media group error:",
                repr(error),
                flush=True
            )

            traceback.print_exc()

            await message.answer(
                "❌ Расмларни юборишда хатолик."
            )


# =========================================================
# /START
# =========================================================

@dp.message(
    CommandStart()
)
async def start_handler(
    message: types.Message
):

    await message.answer(
        "👋 Салом!\n\n"
        "Instagram Reel ёки Post ҳаволасини юборинг.\n"
        "Мен видеони ёки расмларни Telegram'га юбориб бераман. 📥"
    )


# =========================================================
# MESSAGE HANDLER
# =========================================================

@dp.message()
async def message_handler(
    message: types.Message
):

    try:

        text = (
            message.text
            or message.caption
            or ""
        ).strip()

        print("")
        print("========================================")
        print("📩 NEW TELEGRAM MESSAGE")
        print("========================================")
        print(
            "🔗 URL:",
            text,
            flush=True
        )

        if not is_instagram_url(text):

            await message.answer(
                "❌ Instagram ҳаволасини юборинг.\n\n"
                "Масалан:\n"
                "https://www.instagram.com/reel/ABC123/"
            )

            return

        status_message = await message.answer(
            "⏳ Юкланяпти..."
        )

        clean = clean_url(
            text
        )

        with tempfile.TemporaryDirectory() as folder:

            media_files = download_media(
                clean,
                folder
            )

            if not media_files:

                await status_message.edit_text(
                    "❌ Media топилмади ёки Instagram "
                    "унга киришни чеклаган."
                )

                return

            await status_message.edit_text(
                "📤 Telegram'га юбориляпти..."
            )

            await send_media_to_telegram(
                message,
                media_files
            )

            try:

                await status_message.delete()

            except Exception:
                pass

    except Exception as error:

        print("")
        print("========================================")
        print("❌ MAIN ERROR")
        print("========================================")

        print(
            repr(error),
            flush=True
        )

        traceback.print_exc()

        try:

            await message.answer(
                "❌ Хатолик юз берди. Кейинроқ қайта уриниб кўринг."
            )

        except Exception:
            pass


# =========================================================
# MAIN
# =========================================================

async def main():

    print("")
    print("========================================")
    print("🤖 BOT STARTING")
    print("========================================")

    check_ffmpeg()

    # Render health server
    threading.Thread(
        target=start_server,
        daemon=True
    ).start()

    bot = Bot(
        token=BOT_TOKEN
    )

    try:

        # Eski webhook/update'larni tozalash
        await bot.delete_webhook(
            drop_pending_updates=True
        )

        print(
            "🧹 Old Telegram updates cleared",
            flush=True
        )

        print(
            "🤖 Bot ishga tushdi!",
            flush=True
        )

        await dp.start_polling(
            bot
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
            "❌ Fatal error:",
            repr(error),
            flush=True
        )

        traceback.print_exc()
