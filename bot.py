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

# Хранит ссылки и выбор пользователя (видео или аудио)
user_choices = {}

def progress_hook(msg):
    last_percent = {'value': None}

    def create_progress_bar(percent_float, length=20):
        filled_length = int(length * percent_float // 100)
        bar = '█' * filled_length + '-' * (length - filled_length)
        return f"[{bar}] {percent_float:.1f}%"

    def hook(d):
        if d['status'] == 'downloading':
            percent_str = d.get('_percent_str', '').strip()
            try:
                percent_float = float(percent_str.replace('%', ''))
            except:
                percent_float = 0.0
            if percent_str != last_percent['value']:
                last_percent['value'] = percent_str
                progress_line = create_progress_bar(percent_float)
                try:
                    app.loop.create_task(msg.edit(f"🔄 Загружаю... {progress_line}"))
                except Exception as e:
                    logger.warning(f"Не удалось обновить прогресс: {e}")
        elif d['status'] == 'finished':
            try:
                app.loop.create_task(msg.edit("✅ Загрузка завершена, обрабатываю..."))
            except Exception as e:
                logger.warning(f"Не удалось обновить сообщение о завершении: {e}")

    return hook

@app.on_message(filters.command("start"))
async def start_cmd(client, message: Message):
    await message.reply("🎬 Привет! Скинь ссылку на TikTok или YouTube, и я скачаю видео или аудио для тебя!")

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
        await callback_query.answer("Пожалуйста, сначала пришли ссылку.")
        return

    url = user_choices[user_id]['url']

    if data == "download_video":
        user_choices[user_id]['choice'] = "video"
        await callback_query.answer("Скачиваю видео...")
        await process_download(client, callback_query.message, url, download_type="video")

    elif data == "download_audio":
        user_choices[user_id]['choice'] = "audio"
        await callback_query.answer("Скачиваю аудио...")
        await process_download(client, callback_query.message, url, download_type="audio")

async def process_download(client, msg: Message, url: str, download_type: str):
    progress_msg = await msg.reply("🔄 Загружаю... 0%")
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

        logger.info(f"✅ Отправлен файл: {filename}")
        await progress_msg.delete()
        os.remove(filename)

    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        await progress_msg.edit("⚠️ Ошибка при загрузке. Проверь ссылку и попробуй ещё раз.")

if __name__ == "__main__":
    app.run()

