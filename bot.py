import os
import yt_dlp
import logging
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MusicFetcherBot")

os.makedirs("downloads", exist_ok=True)

YDL_OPTS_VIDEO = {
    "format": "bestvideo+bestaudio/best",
    "outtmpl": "downloads/%(title)s.%(ext)s",
    "merge_output_format": "mp4",
    "quiet": True,
    "noplaylist": True,
}

YDL_OPTS_AUDIO = {
    "format": "bestaudio/best",
    "outtmpl": "downloads/%(title)s.%(ext)s",
    "quiet": True,
    "noplaylist": True,
    "postprocessors": [{
        "key": "FFmpegExtractAudio",
        "preferredcodec": "mp3",
        "preferredquality": "192",
    }],
}

app = Client("music_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

user_choices = {}

def progress_hook(msg):
    async def hook(d):
        if d['status'] == 'downloading':
            await msg.edit(f"🔄 Загружаю... {d.get('_percent_str', '...')}")
        elif d['status'] == 'finished':
            await msg.edit("✅ Загрузка завершена, отправляю файл...")
    return lambda d: app.loop.create_task(hook(d))

@app.on_message(filters.command("start"))
async def start_cmd(client, message: Message):
    await message.reply("🎬 Привет! Скинь ссылку с TikTok или YouTube, я скачаю и пришлю тебе видео или аудио!")

@app.on_message(filters.text & ~filters.command(["start"]))
async def ask_choice(client, message: Message):
    url = message.text.strip()
    user_choices[message.from_user.id] = {'url': url, 'choice': None}
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎥 Видео", callback_data="download_video"),
         InlineKeyboardButton("🎧 Аудио", callback_data="download_audio")]
    ])
    await message.reply("Что качаем? Видео или аудио?", reply_markup=keyboard)

@app.on_callback_query()
async def callback_handler(client, callback_query):
    user_id = callback_query.from_user.id
    data = callback_query.data

    if user_id not in user_choices or 'url' not in user_choices[user_id]:
        await callback_query.answer("Пожалуйста, сначала пришли ссылку на видео.")
        return

    url = user_choices[user_id]['url']
    await callback_query.answer("Начинаю загрузку...")

    if data == "download_video":
        user_choices[user_id]['choice'] = "video"
        await process_download(client, callback_query.message, url, "video")

    elif data == "download_audio":
        user_choices[user_id]['choice'] = "audio"
        await process_download(client, callback_query.message, url, "audio")

async def process_download(client, msg: Message, url: str, download_type: str):
    progress_msg = await msg.reply("🔄 Загружаю...")

    my_hook = progress_hook(progress_msg)

    opts = YDL_OPTS_VIDEO.copy() if download_type == "video" else YDL_OPTS_AUDIO.copy()
    opts['progress_hooks'] = [my_hook]

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

        if download_type == "audio":
            filename = os.path.splitext(filename)[0] + ".mp3"

        if download_type == "audio":
            await msg.reply_audio(audio=filename, title=info.get("title"), performer=info.get("uploader"))
        else:
            await msg.reply_video(video=filename, caption=info.get("title"))

        await progress_msg.delete()
        os.remove(filename)

    except Exception as e:
        logger.error(f"Ошибка загрузки: {e}")
        await progress_msg.edit("⚠️ Ошибка при загрузке. Проверь ссылку и попробуй ещё раз.")

if __name__ == "__main__":
    app.run()
