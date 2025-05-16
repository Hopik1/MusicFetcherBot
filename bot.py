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
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log')
    ]
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

def validate_config():
    """Проверка конфигурации перед запуском"""
    required_vars = {
        'API_ID': int,
        'API_HASH': str,
        'BOT_TOKEN': str
    }
    
    for var, var_type in required_vars.items():
        value = os.getenv(var)
        if not value:
            logger.error(f'Отсутствует обязательная переменная: {var}')
            exit(1)
        
        try:
            if var_type == int:
                int(value)
        except ValueError:
            logger.error(f'Некорректное значение для {var}. Ожидается {var_type.__name__}')
            exit(1)

validate_config()

# Конфигурация
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB - лимит Telegram

# Создание директории для загрузок
os.makedirs("downloads", exist_ok=True)

# Конфигурация yt-dlp
BASE_YDL_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "extract_flat": False,
    "socket_timeout": 30,
    "retries": 3,
}

YDL_OPTS_VIDEO = {
    **BASE_YDL_OPTS,
    "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    "outtmpl": "downloads/%(title)s.%(ext)s",
    "merge_output_format": "mp4",
}

YDL_OPTS_AUDIO = {
    **BASE_YDL_OPTS,
    "format": "bestaudio/best",
    "outtmpl": "downloads/%(title)s.%(ext)s",
    "postprocessors": [{
        "key": "FFmpegExtractAudio",
        "preferredcodec": "mp3",
        "preferredquality": "192",
    }],
}

# Инициализация клиента Pyrogram
try:
    app = Client(
        "music_bot",
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
        workers=4,
        sleep_threshold=30
    )
    logger.info("Pyrogram клиент успешно инициализирован")
except Exception as e:
    logger.error(f"Ошибка инициализации клиента: {e}")
    exit(1)

# Хранилище пользовательских выборов
user_choices = {}

def progress_hook(msg: Message):
    """Отображение прогресса загрузки"""
    last_update = {'percent': 0, 'time': 0}
    
    def hook(d):
        import time
        
        if d['status'] == 'downloading':
            percent = float(d.get('_percent_str', '0').replace('%', '') or 0
            now = time.time()
            
            # Обновляем прогресс не чаще чем раз в 2 секунды
            if percent != last_update['percent'] and now - last_update['time'] > 2:
                last_update['percent'] = percent
                last_update['time'] = now
                
                try:
                    progress_bar = f"[{'█' * int(percent // 5)}{'░' * (20 - int(percent // 5))}]"
                    text = f"🔄 Загружаю... {progress_bar} {percent:.1f}%"
                    app.loop.create_task(msg.edit(text))
                except Exception as e:
                    logger.warning(f"Ошибка обновления прогресса: {e}")
        
        elif d['status'] == 'finished':
            try:
                app.loop.create_task(msg.edit("✅ Загрузка завершена, начинаю обработку..."))
            except Exception as e:
                logger.warning(f"Ошибка обновления статуса: {e}")
    
    return hook

@app.on_message(filters.command(["start", "help"]))
async def start_cmd(client: Client, message: Message):
    """Обработчик команд start и help"""
    try:
        text = (
            "🎬 <b>YouTube/TikTok Downloader Bot</b>\n\n"
            "Отправьте мне ссылку на видео, и я скачаю его для вас!\n\n"
            "Поддерживаемые платформы:\n"
            "- YouTube\n"
            "- TikTok\n"
            "- Instagram Reels\n\n"
            "После отправки ссылки выберите формат скачивания."
        )
        await message.reply(text)
    except RPCError as e:
        logger.error(f"Ошибка в start_cmd: {e}")

@app.on_message(filters.text & ~filters.command(["start", "help"]))
async def handle_url(client: Client, message: Message):
    """Обработка URL от пользователя"""
    url = message.text.strip()
    user_id = message.from_user.id
    
    # Валидация URL
    if not any(domain in url for domain in ('youtube.com', 'youtu.be', 'tiktok.com', 'instagram.com')):
        await message.reply("⚠️ Поддерживаются только ссылки с YouTube, TikTok и Instagram Reels")
        return
    
    user_choices[user_id] = {'url': url}
    
    try:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎥 Видео (MP4)", callback_data="video"),
             InlineKeyboardButton("🎧 Аудио (MP3)", callback_data="audio")]
        ])
        await message.reply(
            "📥 Выберите формат для скачивания:",
            reply_markup=keyboard
        )
    except RPCError as e:
        logger.error(f"Ошибка при отправке клавиатуры: {e}")
        await message.reply("⚠️ Произошла ошибка. Пожалуйста, попробуйте позже.")

@app.on_callback_query()
async def callback_handler(client: Client, callback_query):
    """Обработка выбора формата"""
    user_id = callback_query.from_user.id
    data = callback_query.data
    
    if user_id not in user_choices:
        await callback_query.answer("❌ Ссылка устарела. Отправьте новую.")
        return
    
    url = user_choices[user_id]['url']
    await callback_query.answer()
    
    try:
        progress_msg = await callback_query.message.reply("⏳ Начинаю загрузку...")
        
        opts = YDL_OPTS_VIDEO if data == "video" else YDL_OPTS_AUDIO
        opts['progress_hooks'] = [progress_hook(progress_msg)]
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            if data == "audio":
                filename = os.path.splitext(filename)[0] + ".mp3"
            
            # Проверка размера файла
            file_size = os.path.getsize(filename)
            if file_size > MAX_FILE_SIZE:
                raise ValueError(f"Файл слишком большой ({file_size/1024/1024:.1f}MB). Лимит Telegram: {MAX_FILE_SIZE/1024/1024}MB")
            
            # Отправка файла
            if data == "audio":
                await callback_query.message.reply_audio(
                    audio=filename,
                    title=info.get('title', 'Аудио')[:64],
                    performer=info.get('uploader', 'Неизвестный исполнитель')[:32],
                    duration=info.get('duration', 0)
                )
            else:
                await callback_query.message.reply_video(
                    video=filename,
                    caption=info.get('title', 'Видео')[:1024],
                    duration=info.get('duration', 0),
                    width=info.get('width', 0),
                    height=info.get('height', 0)
                )
            
            await progress_msg.delete()
            logger.info(f"Успешно отправлен файл: {filename}")
            
    except yt_dlp.DownloadError as e:
        logger.error(f"Ошибка загрузки: {e}")
        await progress_msg.edit("⚠️ Ошибка при загрузке. Проверьте ссылку и попробуйте снова.")
    except ValueError as e:
        logger.error(f"Ошибка размера файла: {e}")
        await progress_msg.edit(f"⚠️ {e}")
    except RPCError as e:
        logger.error(f"Ошибка Telegram API: {e}")
        await progress_msg.edit("⚠️ Ошибка при отправке файла. Попробуйте позже.")
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}", exc_info=True)
        await progress_msg.edit("⚠️ Произошла непредвиденная ошибка.")
    finally:
        # Очистка
        if 'filename' in locals() and os.path.exists(filename):
            try:
                os.remove(filename)
            except Exception as e:
                logger.warning(f"Ошибка удаления файла: {e}")
        
        user_choices.pop(user_id, None)

if __name__ == "__main__":
    logger.info("Запуск бота...")
    try:
        app.run()
    except KeyboardInterrupt:
        logger.info("Бот остановлен")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        exit(1)
