import os
import yt_dlp
import logging
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import RPCError

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

# Проверка обязательных переменных окружения
required_vars = ['API_ID', 'API_HASH', 'BOT_TOKEN']
for var in required_vars:
    if not os.getenv(var):
        logger.error(f'Необходимо установить переменную окружения {var}')
        exit(1)

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Создание директории для загрузок
os.makedirs("downloads", exist_ok=True)

# Конфигурация yt-dlp
YDL_OPTS_VIDEO = {
    "format": "bestvideo+bestaudio/best",
    "outtmpl": "downloads/%(title)s.%(ext)s",
    "merge_output_format": "mp4",
    "quiet": True,
    "noplaylist": True,
    "extract_flat": False,
}

YDL_OPTS_AUDIO = {
    "format": "bestaudio/best",
    "outtmpl": "downloads/%(title)s.%(ext)s",
    "quiet": True,
    "noplaylist": True,
    "extract_flat": False,
    "postprocessors": [{
        "key": "FFmpegExtractAudio",
        "preferredcodec": "mp3",
        "preferredquality": "192",
    }],
}

# Инициализация клиента Pyrogram
app = Client(
    "music_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Хранилище пользовательских выборов
user_choices = {}

def progress_hook(msg: Message):
    last_percent = {'value': 0}
    
    def hook(d):
        if d['status'] == 'downloading':
            percent = d.get('_percent_str', '0%').strip()
            if percent != last_percent['value']:
                last_percent['value'] = percent
                try:
                    app.loop.create_task(
                        msg.edit(f"🔄 Загружаю... {percent}")
                    )
                except Exception as e:
                    logger.warning(f"Ошибка обновления прогресса: {e}")
        elif d['status'] == 'finished':
            try:
                app.loop.create_task(
                    msg.edit("✅ Загрузка завершена, обрабатываю...")
                )
            except Exception as e:
                logger.warning(f"Ошибка обновления статуса завершения: {e}")
    
    return hook

@app.on_message(filters.command("start"))
async def start_cmd(client: Client, message: Message):
    try:
        await message.reply(
            "🎬 Привет! Отправь мне ссылку на видео с YouTube или TikTok, "
            "и я скачаю его для тебя в видео или аудио формате!"
        )
    except RPCError as e:
        logger.error(f"Ошибка в start_cmd: {e}")

@app.on_message(filters.text & ~filters.command(["start", "help"]))
async def handle_url(client: Client, message: Message):
    url = message.text.strip()
    if not url.startswith(('http://', 'https://')):
        await message.reply("⚠️ Пожалуйста, отправьте корректную ссылку на видео.")
        return
    
    user_id = message.from_user.id
    user_choices[user_id] = {'url': url}
    
    try:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎥 Видео", callback_data="video"),
             InlineKeyboardButton("🎧 Аудио", callback_data="audio")]
        ])
        await message.reply(
            "Выберите формат для скачивания:",
            reply_markup=keyboard
        )
    except RPCError as e:
        logger.error(f"Ошибка при отправке клавиатуры: {e}")
        await message.reply("Произошла ошибка. Пожалуйста, попробуйте позже.")

@app.on_callback_query()
async def callback_handler(client: Client, callback_query):
    user_id = callback_query.from_user.id
    data = callback_query.data
    
    if user_id not in user_choices:
        await callback_query.answer("Ссылка устарела. Отправьте новую.")
        return
    
    url = user_choices[user_id]['url']
    await callback_query.answer()
    
    try:
        progress_msg = await callback_query.message.reply("🔄 Начинаю загрузку...")
        
        opts = YDL_OPTS_VIDEO if data == "video" else YDL_OPTS_AUDIO
        opts['progress_hooks'] = [progress_hook(progress_msg)]
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            if data == "audio":
                filename = os.path.splitext(filename)[0] + ".mp3"
            
            if os.path.getsize(filename) > 50 * 1024 * 1024:  # 50MB limit
                raise ValueError("Файл слишком большой для отправки в Telegram")
            
            if data == "audio":
                await callback_query.message.reply_audio(
                    audio=filename,
                    title=info.get('title', 'Аудио'),
                    performer=info.get('uploader', 'Неизвестный исполнитель')
                )
            else:
                await callback_query.message.reply_video(
                    video=filename,
                    caption=info.get('title', 'Видео')
                )
            
            await progress_msg.delete()
            os.remove(filename)
            
    except yt_dlp.DownloadError as e:
        logger.error(f"Ошибка загрузки: {e}")
        await progress_msg.edit("⚠️ Ошибка при загрузке видео. Проверьте ссылку.")
    except RPCError as e:
        logger.error(f"Ошибка Telegram API: {e}")
        await progress_msg.edit("⚠️ Ошибка при отправке файла. Попробуйте позже.")
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}")
        await progress_msg.edit("⚠️ Произошла непредвиденная ошибка.")
    finally:
        if 'filename' in locals() and os.path.exists(filename):
            os.remove(filename)
        user_choices.pop(user_id, None)

if __name__ == "__main__":
    logger.info("Запуск бота...")
    app.run()
