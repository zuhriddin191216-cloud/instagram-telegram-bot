import asyncio
import html
import os
import re
import subprocess
import tempfile
import threading
import traceback
from pathlib import Path

import requests
import yt_dlp
import instaloader

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile
from aiogram.filters import CommandStart
from http.server import BaseHTTPRequestHandler, HTTPServer


# =========================================================
# SETTINGS
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi!")


# =========================================================
# RENDER HEALTH SERVER
# =========================================================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass


def start_health_server():
    port = int(os.environ.get("PORT", "10000"))

    server = HTTPServer(("0.0.0.0", port), HealthHandler)

    print(f"🌐 Render web server started on port {port}")

    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True
    )
    thread.start()


# =========================================================
# HELPERS
# =========================================================

def is_instagram_url(text: str) -> bool:
    if not text:
        return False

    return bool(
        re.search(
            r"https?://(?:www\.)?instagram\.com/",
            text,
            re.IGNORECASE
        )
    )


def is_reel_url(url: str) -> bool:
    return bool(
        re.search(
            r"instagram\.com/(reel|reels|tv)/",
            url,
            re.IGNORECASE
        )
    )


def clean_url(url: str) -> str:
    url = url.strip()

    # Telegram yoki boshqa matndan ortiqcha belgilar
    url = url.split()[0]

    # Query parametrlarini olib tashlaymiz
    url = url.split("?")[0]

    return url.rstrip("/")


def get_shortcode(url: str):
    match = re.search(
        r"instagram\.com/(?:p|reel|reels|tv)/([^/?#]+)",
        url,
        re.IGNORECASE
    )

    if match:
        return match.group(1)

    return None


# =========================================================
# FFMPEG CHECK
# =========================================================

def check_ffmpeg():
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            first_line = result.stdout.splitlines()[0]
            print(f"✅ FFmpeg: {first_line}")
            return True

    except Exception as e:
        print(f"❌ FFmpeg error: {e}")

    return False


# =========================================================
# VIDEO CODEC
# =========================================================

def get_video_codecs(file_path: str):
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name,width,height,r_frame_rate",
                "-of",
                "default=noprint_wrappers=1",
                file_path
            ],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            return None, None, None, None

        data = {}

        for line in result.stdout.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                data[key] = value

        codec = data.get("codec_name")
        width = data.get("width")
        height = data.get("height")
        fps = data.get("r_frame_rate")

        return codec, width, height, fps

    except Exception as e:
        print(f"⚠️ ffprobe error: {e}")
        return None, None, None, None


# =========================================================
# CONVERT VIDEO
# =========================================================

def convert_video_for_telegram(input_file: str, output_file: str):
    print("🎬 PREPARING VIDEO FOR TELEGRAM")

    codec, width, height, fps = get_video_codecs(input_file)

    print(f"🎞 Video codec: {codec}")
    print(f"📐 Resolution: {width}x{height}")
    print(f"🎞 FPS: {fps}")

    if codec == "h264":
        print("✅ Video already H.264")

        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    input_file,
                    "-c",
                    "copy",
                    "-movflags",
                    "+faststart",
                    output_file
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30
            )

            if os.path.exists(output_file):
                print("✅ Remux successful")
                return output_file

        except Exception as e:
            print(f"⚠️ Remux error: {e}")

    print("🔄 Video qayta kodlanadi...")
    print("🎥 H.264 + AAC")

    try:

        # MUHIM:
        # Render Free serverda og'ir videoni to'liq original
        # resolutionda encode qilish juda og'ir.
        #
        # Shuning uchun maksimal kenglikni 720px qilamiz.
        # Video harakatlanadi va Telegram bilan yaxshi ishlaydi.

        command = [
            "ffmpeg",
            "-y",

            "-i",
            input_file,

            # maksimal 720px
            "-vf",
            "scale=min(720\\,iw):-2",

            # FPS maksimal 30
            "-r",
            "30",

            # H.264
            "-c:v",
            "libx264",

            # Render uchun eng tez preset
            "-preset",
            "ultrafast",

            # Sifat
            "-crf",
            "30",

            # Telegram compatibility
            "-pix_fmt",
            "yuv420p",

            # Audio
            "-c:a",
            "aac",

            "-b:a",
            "96k",

            # MP4 streaming
            "-movflags",
            "+faststart",

            output_file
        ]

        print("🚀 FFmpeg started...")

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60
        )

        if result.returncode != 0:
            print("❌ FFmpeg failed")
            print(result.stderr[-3000:])
            return None

        if not os.path.exists(output_file):
            print("❌ Output file not found")
            return None

        size = os.path.getsize(output_file)

        if size < 10000:
            print("❌ Output video juda kichik")
            return None

        print(f"✅ Video converted: {size} bytes")

        return output_file

    except subprocess.TimeoutExpired:
        print("⏰ FFmpeg timeout!")
        return None

    except Exception as e:
        print(f"❌ Conversion error: {e}")
        traceback.print_exc()
        return None


# =========================================================
# DOWNLOAD VIDEO WITH YT-DLP
# =========================================================

def download_video(url: str, folder: str):
    print("🎥 Instagram video yuklanmoqda...")
    print(url)

    output_template = os.path.join(
        folder,
        "video.%(ext)s"
    )

    options = {
        "outtmpl": output_template,

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

        "quiet": False,

        "no_warnings": False,

        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/140.0.0.0 Safari/537.36"
            ),

            "Accept-Language": "en-US,en;q=0.9",

            "Referer": "https://www.instagram.com/",
        },
    }

    try:

        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([url])

        files = list(Path(folder).glob("video.*"))

        # mp4ni afzal ko'ramiz
        mp4_files = [
            f for f in files
            if f.suffix.lower() == ".mp4"
        ]

        if mp4_files:
            file_path = str(mp4_files[0])
        elif files:
            file_path = str(files[0])
        else:
            print("❌ Video topilmadi")
            return None

        print(f"✅ Video downloaded: {file_path}")

        return file_path

    except Exception as e:
        print(f"❌ yt-dlp error: {e}")
        return None


# =========================================================
# INSTAGRAM PAGE
# =========================================================

def get_instagram_html(url: str):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/140.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.instagram.com/",
    }

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=30
        )

        print(
            f"🌐 Instagram status: {response.status_code}"
        )

        if response.status_code != 200:
            return None

        print(
            f"📄 HTML size: {len(response.text)}"
        )

        return response.text

    except Exception as e:
        print(f"❌ Instagram request error: {e}")
        return None


# =========================================================
# IMAGE URL EXTRACTION
# =========================================================

def extract_image_urls(html_text: str):
    if not html_text:
        return []

    urls = []

    patterns = [
        r'https://[^"\']+\.jpg[^"\']*',
        r'https://[^"\']+\.jpeg[^"\']*',
        r'https://[^"\']+\.png[^"\']*',
    ]

    for pattern in patterns:

        matches = re.findall(
            pattern,
            html_text,
            re.IGNORECASE
        )

        for url in matches:

            url = html.unescape(url)

            url = url.replace("\\u0026", "&")
            url = url.replace("\\/", "/")

            if url not in urls:
                urls.append(url)

    print(f"🖼 Found {len(urls)} image URLs")

    return urls


# =========================================================
# DOWNLOAD IMAGE
# =========================================================

def download_image(url: str, path: str):
    try:

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/140.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.instagram.com/",
        }

        response = requests.get(
            url,
            headers=headers,
            timeout=30
        )

        if response.status_code != 200:
            print(
                f"❌ Image status: {response.status_code}"
            )
            return False

        with open(path, "wb") as f:
            f.write(response.content)

        print(
            f"✅ Image downloaded: {path}"
        )

        return True

    except Exception as e:
        print(f"❌ Image error: {e}")
        return False


# =========================================================
# INSTALOADER FALLBACK
# =========================================================

def download_with_instaloader(
    url: str,
    folder: str
):

    shortcode = get_shortcode(url)

    if not shortcode:
        print("❌ Shortcode topilmadi")
        return []

    print(
        f"🔄 Instaloader fallback: {shortcode}"
    )

    try:

        loader = instaloader.Instaloader(
            dirname_pattern=folder,
            filename_pattern="{shortcode}_{mediacount}",
            download_videos=False,
            save_metadata=False,
            post_metadata_txt_pattern=""
        )

        post = instaloader.Post.from_shortcode(
            loader.context,
            shortcode
        )

        downloaded = []

        # Carousel
        if post.typename == "GraphSidecar":

            index = 1

            for node in post.get_sidecar_nodes():

                if node.is_video:
                    continue

                image_url = node.display_url

                path = os.path.join(
                    folder,
                    f"image_{index}.jpg"
                )

                if download_image(
                    image_url,
                    path
                ):
                    downloaded.append(path)

                index += 1

        else:

            if not post.is_video:

                image_url = post.url

                path = os.path.join(
                    folder,
                    "image_1.jpg"
                )

                if download_image(
                    image_url,
                    path
                ):
                    downloaded.append(path)

        print(
            f"✅ Instaloader images: {len(downloaded)}"
        )

        return downloaded

    except Exception as e:

        print(
            f"❌ Instaloader error: {e}"
        )

        return []


# =========================================================
# DOWNLOAD MEDIA
# =========================================================

def download_media(url: str, folder: str):

    reel = is_reel_url(url)

    print(f"📌 Reel: {reel}")

    # -----------------------------------------------------
    # REEL
    # -----------------------------------------------------

    if reel:

        original = download_video(
            url,
            folder
        )

        if not original:
            return {
                "type": "none",
                "files": []
            }

        converted = os.path.join(
            folder,
            "telegram_video.mp4"
        )

        result = convert_video_for_telegram(
            original,
            converted
        )

        if result:
            return {
                "type": "video",
                "files": [result]
            }

        # Conversion ishlamasa originalni yubormaymiz,
        # chunki VP9 Telegramda rasmdagidek ko'rinishi mumkin.
        return {
            "type": "none",
            "files": []
        }

    # -----------------------------------------------------
    # POST VIDEO
    # -----------------------------------------------------

    print("📦 Post media tekshirilmoqda...")

    original = download_video(
        url,
        folder
    )

    if original:

        converted = os.path.join(
            folder,
            "telegram_video.mp4"
        )

        result = convert_video_for_telegram(
            original,
            converted
        )

        if result:

            return {
                "type": "video",
                "files": [result]
            }

    # -----------------------------------------------------
    # IMAGES
    # -----------------------------------------------------

    print("🖼 Video topilmadi. Rasmlar qidirilmoqda...")

    html_text = get_instagram_html(url)

    image_urls = extract_image_urls(
        html_text
    )

    downloaded = []

    index = 1

    for image_url in image_urls:

        if len(downloaded) >= 20:
            break

        path = os.path.join(
            folder,
            f"image_{index}.jpg"
        )

        if download_image(
            image_url,
            path
        ):
            downloaded.append(path)

        index += 1

    # -----------------------------------------------------
    # INSTALOADER FALLBACK
    # -----------------------------------------------------

    if not downloaded:

        downloaded = download_with_instaloader(
            url,
            folder
        )

    if downloaded:

        return {
            "type": "images",
            "files": downloaded
        }

    return {
        "type": "none",
        "files": []
    }


# =========================================================
# SEND MEDIA
# =========================================================

async def send_media(
    message: Message,
    media_type: str,
    files: list
):

    # -----------------------------------------------------
    # VIDEO
    # -----------------------------------------------------

    if media_type == "video":

        video_path = files[0]

        print(
            "📤 Uploading video to Telegram..."
        )

        try:

            await message.answer_video(
                video=FSInputFile(video_path),
                supports_streaming=True
            )

            print(
                "✅ Video sent successfully"
            )

            return True

        except Exception as e:

            print(
                f"❌ Video upload error: {e}"
            )

            # fallback document
            try:

                print(
                    "📄 Sending video as document..."
                )

                await message.answer_document(
                    document=FSInputFile(
                        video_path
                    )
                )

                return True

            except Exception as e2:

                print(
                    f"❌ Document error: {e2}"
                )

                return False

    # -----------------------------------------------------
    # ONE IMAGE
    # -----------------------------------------------------

    if media_type == "images":

        if len(files) == 1:

            try:

                await message.answer_photo(
                    photo=FSInputFile(
                        files[0]
                    )
                )

                return True

            except Exception as e:

                print(
                    f"❌ Photo error: {e}"
                )

                return False

        # -------------------------------------------------
        # MULTIPLE IMAGES
        # -------------------------------------------------

        print(
            f"📸 Sending {len(files)} images..."
        )

        # Telegram album max 10
        for i in range(
            0,
            len(files),
            10
        ):

            batch = files[
                i:i + 10
            ]

            media = []

            from aiogram.types import InputMediaPhoto

            for path in batch:

                media.append(
                    InputMediaPhoto(
                        media=FSInputFile(
                            path
                        )
                    )
                )

            try:

                await message.answer_media_group(
                    media=media
                )

            except Exception as e:

                print(
                    f"❌ Album error: {e}"
                )

                return False

        print(
            "✅ Images sent successfully"
        )

        return True

    return False


# =========================================================
# BOT
# =========================================================

bot = Bot(
    token=BOT_TOKEN
)

dp = Dispatcher()


# =========================================================
# START
# =========================================================

@dp.message(CommandStart())
async def start_handler(
    message: Message
):

    await message.answer(
        "👋 Салом!\n\n"
        "Instagram Reel ёки Post ҳаволасини юборинг.\n\n"
        "🎥 Видео → видео қилиб\n"
        "🖼 Расм → расм қилиб\n"
        "📸 Карусель → ҳамма расмларни юбориб бераман."
    )


# =========================================================
# MESSAGE HANDLER
# =========================================================

@dp.message(F.text)
async def message_handler(
    message: Message
):

    text = message.text.strip()

    if not is_instagram_url(text):

        await message.answer(
            "❌ Instagram ҳаволасини юборинг."
        )

        return

    url = clean_url(text)

    status = await message.answer(
        "⏳ Юкланяпти..."
    )

    try:

        with tempfile.TemporaryDirectory() as folder:

            result = await asyncio.to_thread(
                download_media,
                url,
                folder
            )

            media_type = result["type"]
            files = result["files"]

            if not files:

                await status.edit_text(
                    "❌ Медиа юклаб бўлмади.\n\n"
                    "Instagram ҳаволаси очиқ эканини "
                    "текшириб кўринг."
                )

                return

            await status.edit_text(
                "📤 Telegram'га юбориляпти..."
            )

            success = await send_media(
                message,
                media_type,
                files
            )

            if success:

                try:
                    await status.delete()
                except:
                    pass

            else:

                await status.edit_text(
                    "❌ Telegram'га юборишда хатолик."
                )

    except Exception as e:

        print(
            f"❌ MAIN ERROR: {e}"
        )

        traceback.print_exc()

        try:

            await status.edit_text(
                "❌ Хатолик юз берди.\n"
                "Бироздан кейин яна уриниб кўринг."
            )

        except:
            pass


# =========================================================
# MAIN
# =========================================================

async def main():

    print("🤖 BOT STARTING")

    check_ffmpeg()

    start_health_server()

    try:

        await bot.delete_webhook(
            drop_pending_updates=True
        )

        print(
            "🧹 Old Telegram updates cleared"
        )

    except Exception as e:

        print(
            f"⚠️ Webhook clear error: {e}"
        )

    print(
        "🤖 Bot ishga tushdi!"
    )

    await dp.start_polling(
        bot
    )


if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        print(
            "🛑 Bot stopped"
        )

    except Exception as e:

        print(
            f"💥 FATAL ERROR: {e}"
        )

        traceback.print_exc()
