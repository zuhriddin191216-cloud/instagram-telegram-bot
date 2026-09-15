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
            "b
