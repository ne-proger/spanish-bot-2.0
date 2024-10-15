import os
import logging
import openai
import asyncio
from cachetools import TTLCache
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackContext
from telegram.error import TelegramError
from dotenv import load_dotenv
from deep_translator import GoogleTranslator
from speech_recognition import Recognizer, AudioFile
from google.cloud import texttospeech
import random
import time

# Загрузка переменных окружения
load_dotenv()

# Получение ключей API и параметров
openai.api_key = os.getenv("OPENAI_API_KEY")
telegram_token = os.getenv("TELEGRAM_TOKEN")
max_tokens = int(os.getenv("MAX_TOKENS", 3000))
temperature = float(os.getenv("TEMPERATURE", 0.7))

openai.api_key = openai_api_key

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levellevelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Создание экземпляра переводчика
translator = GoogleTranslator(source='es', target='ru')

# Кэширование ответов с временем жизни 10 минут и максимумом в 100 записей
cache = TTLCache(maxsize=100, ttl=600)

# Клавиатура для выбора уровня
level_keyboard = [
    ['A1', 'A2', 'B1'],
    ['B2', 'C1', 'C2']
]
level_markup = ReplyKeyboardMarkup(level_keyboard, one_time_keyboard=True, resize_keyboard=True)

# Основное меню
reply_keyboard = [
    ['КВИЗ', 'Учи по одному слову в день', 'Игра в слова'],
    ['Твой уровень испанского']
]
markup = ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=False, resize_keyboard=True)

# Асинхронная функция для отправки запроса к OpenAI GPT с кэшированием
async def gpt_response(question):
    if question in cache:
        logger.info("Используем кэшированный ответ")
        return cache[question]

    try:
        response = await openai.ChatCompletion.acreate(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Ты — учитель испанского языка. Отвечай на вопросы максимально кратко, четко и по существу."},
                {"role": "user", "content": question},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        answer = response['choices'][0]['message']['content'].strip()
        cache[question] = answer
        return answer
    except Exception as e:
        logger.error(f"Ошибка при взаимодействии с OpenAI: {e}")
        return "Извините, произошла ошибка при обработке вашего запроса."

# Функция для отображения индикации "печатает"
async def send_typing_action(update: Update, context: CallbackContext):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

# Функция для отображения индикации "записывает голос"
async def send_voice_action(update: Update, context: CallbackContext):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_voice")


# Функция для приветствия пользователя
async def start(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "¡Hola! Я твой бот для изучения испанского. Задавай вопросы на испанском или английском, и я помогу!\n"
        "Используйте меню ниже для взаимодействия со мной.",
        reply_markup=markup
    )
    
    
# Функция для помощи пользователю
async def help_command(update: Update, context: CallbackContext):
    help_text = (
        "Я бот для изучения испанского языка! Вот что я умею:\n"
        "- Напишите сообщение на испанском или английском, и я помогу с переводом или объяснением.\n"
        "- Используйте команду /quiz для викторины.\n"
        "- Используйте команду /daily для получения нового слова на каждый день.\n"
        "- Используйте команду /wordgame для игры в слова.\n"
        "- Используйте команду /setlevel для установки вашего уровня изучения.\n"
        "- Отправьте голосовое сообщение, и я попробую его распознать.\n"
    )
    await update.message.reply_text(help_text)


# Обработчик для показа клавиатуры с уровнями
async def show_level_selection(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "Выберите ваш уровень изучения испанского:",
        reply_markup=level_markup
    )
    context.user_data['awaiting_level_selection'] = True

# Обработка выбора уровня
async def handle_level_selection(update: Update, context: CallbackContext):
    user_message = update.message.text.strip().upper()
    valid_levels = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2']

  # Отображаем индикацию "печатает"
    await send_typing_action(update, context)

    if user_message in valid_levels:
        context.user_data['level'] = user_message
        await update.message.reply_text(
            f"Ваш уровень изучения установлен на {user_message}.",
            reply_markup=markup
        )
        context.user_data['awaiting_level_selection'] = False
    else:
        await update.message.reply_text(
            "Пожалуйста, выберите уровень, используя кнопки ниже:",
            reply_markup=level_markup
        )
from telegram.constants import ChatAction


# Викторина
daily_words = [
    "gato - кошка", "perro - собака", "casa - дом", "libro - книга", "mesa - стол", 
    "silla - стул", "agua - вода", "comida - еда", "familia - семья", "escuela - школа", 
    "amigo - друг", "ciudad - город", "cielo - небо", "sol - солнце", "luna - луна", 
    "estrella - звезда", "flor - цветок", "árbol - дерево", "montaña - гора", 
    "río - река", "mar - море", "tierra - земля", "camino - дорога", "auto - машина", 
    "tren - поезд", "avión - самолет", "puerta - дверь", "ventana - окно", 
    "rojo - красный", "azul - синий", "verde - зелёный", "amarillo - жёлтый", 
    "blanco - белый", "negro - чёрный", "feliz - счастливый", "triste - грустный", 
    "rápido - быстрый", "lento - медленный", "calor - жара", "frío - холод", 
    "manzana - яблоко", "plátano - банан", "naranja - апельсин", "limón - лимон", 
    "uva - виноград", "queso - сыр", "pan - хлеб", "pescado - рыба", "carne - мясо", 
    "pollo - курица", "tenedor - вилка"
]

async def quiz(update: Update, context):
    
      # Отображаем индикацию "печатает"
    await send_typing_action(update, context)
    
    word_pair = random.choice(daily_words)
    word, correct_translation = word_pair.split(" - ")

    incorrect_translations = random.sample(
        [w.split(" - ")[1] for w in daily_words if w != word_pair], 3
    )
    options = [correct_translation] + incorrect_translations
    random.shuffle(options)
    correct_answer = options.index(correct_translation) + 1

    question = f"Как переводится слово '{word}' на русский?"
    options_text = "\n".join([f"{chr(64+i)}) {opt}" for i, opt in enumerate(options, start=1)])
    quiz_message = f"{question}\n\n{options_text}"
    await update.message.reply_text(quiz_message)

    context.user_data['quiz_answer'] = chr(64+correct_answer)
    context.user_data['awaiting_quiz_response'] = True

# Обработка ответа на квиз
async def handle_quiz_response(update: Update, context):
    if context.user_data.get('awaiting_quiz_response'):
        user_answer = update.message.text.strip().upper()
        correct_answer = context.user_data.get('quiz_answer')

        if user_answer == correct_answer:
            await update.message.reply_text("Правильно! Молодец!")
        else:
            await update.message.reply_text(f"Неправильно. Правильный ответ был: {correct_answer}")

        context.user_data['awaiting_quiz_response'] = False
    else:
        await update.message.reply_text("Ваш вопрос непонятен, пожалуйста, уточните.")

# Игра в слова
async def word_game(update: Update, context):
    
      # Отображаем индикацию "печатает"
    await send_typing_action(update, context)
    
    last_word = context.user_data.get("last_word", "gato")
    await update.message.reply_text(
        f"Ваше слово: {last_word}. Напишите слово на испанском, которое начинается на букву '{last_word[-1]}'.\n"
        "Чтобы закончить игру, напишите /endgame.",
        reply_markup=markup
    )
    context.user_data['in_word_game'] = True

# Обработка ответа в игре в слова
async def handle_word_response(update: Update, context):
    if context.user_data.get('in_word_game'):
        user_word = update.message.text.strip().lower()
        last_word = context.user_data.get("last_word", "gato")

        if user_word.startswith(last_word[-1]):
            context.user_data["last_word"] = user_word
            await update.message.reply_text(
                f"Хорошо! Теперь вам слово на '{user_word[-1]}'.\n"
                "Чтобы закончить игру, напишите /endgame.",
                reply_markup=markup
            )
        else:
            await update.message.reply_text(
                f"Ваше слово должно начинаться с буквы '{last_word[-1]}'! Попробуйте ещё раз или напишите /endgame, чтобы закончить игру.",
                reply_markup=markup
            )
    else:
        await update.message.reply_text("Сначала начните игру с помощью команды /wordgame.", reply_markup=markup)

# Завершение игры в слова
async def end_game(update: Update, context):
    
      # Отображаем индикацию "печатает"
    await send_typing_action(update, context)
    
    if context.user_data.get('in_word_game'):
        await update.message.reply_text("Игра завершена. Надеюсь, вам понравилось!", reply_markup=markup)
        context.user_data.pop('in_word_game', None)
        context.user_data.pop('last_word', None)
    else:
        await update.message.reply_text("Вы сейчас не в игре.", reply_markup=markup)

# Ежедневное слово
async def daily_word(update: Update, context):
    word = random.choice(daily_words)
    await update.message.reply_text(f"Ваше сегодняшнее слово: {word}")

# Обработка текстовых сообщений
async def handle_message(update: Update, context: CallbackContext):
    user_message = update.message.text.strip()
    logger.info(f"Вопрос пользователя: {user_message}")
    
     # Отображаем индикацию "печатает"
    await send_typing_action(update, context)

    if context.user_data.get('awaiting_level_selection'):
        await handle_level_selection(update, context)
    elif context.user_data.get('awaiting_quiz_response'):
        await handle_quiz_response(update, context)
    elif context.user_data.get('in_word_game'):
        await handle_word_response(update, context)
    elif user_message == 'КВИЗ':
        await quiz(update, context)
    elif user_message == 'Учи по одному слову в день':
        await daily_word(update, context)
    elif user_message == 'Игра в слова':
        await word_game(update, context)
    elif user_message == 'Твой уровень испанского':
        await show_level_selection(update, context)
    else:
        response = await gpt_response(user_message)
        await update.message.reply_text(response)
        
# os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/Users/dmitrytaran/Desktop/bot/vs_code/emerald-entity-438210-k7-bea7a0cd69ae.json"

# os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/etc/secrets/GOOGLE_APPLICATION_CREDENTIALS"



# Обработка голосовых сообщений с ответом голосом
async def handle_voice_message(update: Update, context):
    try:
        voice = update.message.voice

        # Отображаем индикацию "записывает голос"
        await send_voice_action(update, context)

        file = await voice.get_file()
        audio_path = "voice_message.oga"
        await file.download_to_drive(audio_path)
        logger.info("Аудиофайл скачан и сохранен как voice_message.oga")

        # Конвертируем OGA в WAV
        wav_path = "voice_message.wav"
        os.system(f"ffmpeg -y -i {audio_path} {wav_path}")
        time.sleep(1)
        logger.info("Аудиофайл конвертирован в voice_message.wav")

        # Распознавание речи
        recognizer = Recognizer()
        with AudioFile(wav_path) as audio_file:
            audio_data = recognizer.record(audio_file)
            try:
                text = recognizer.recognize_google(audio_data, language='ru')
                logger.info(f"Распознанный текст: {text}")
                response_text = await gpt_response(text)
                response_audio_path = "response_audio.ogg"
                generate_google_speech(response_text, response_audio_path)
                with open(response_audio_path, 'rb') as audio_file:
                    await update.message.reply_voice(audio_file)
                os.remove(audio_path)
                os.remove(wav_path)
                os.remove(response_audio_path)
            except Exception as e:
                await update.message.reply_text("Извините, не могу распознать аудиосообщение.")
                logger.error(f"Ошибка распознавания аудио: {e}")
    except Exception as e:
        await update.message.reply_text("Произошла ошибка обработки голосового сообщения.")
        logger.error(f"Ошибка обработки голосового сообщения: {e}")

# Функция генерации речи с использованием Google Cloud Text-to-Speech
def generate_google_speech(text, output_file):
    client = texttospeech.TextToSpeechClient()
    input_text = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(
        language_code="ru-RU",
        ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL
    )
    audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.OGG_OPUS)
    response = client.synthesize_speech(input=input_text, voice=voice, audio_config=audio_config)
    with open(output_file, "wb") as out:
        out.write(response.audio_content)
    logger.info(f"Аудио ответ сохранен в файл {output_file}")
# Обработка ошибок Telegram API
async def error_handler(update: Update, context):
    logger.error(f"Произошла ошибка: {context.error}")
    try:
        await update.message.reply_text("Извините, произошла ошибка. Пожалуйста, попробуйте снова позже.")
    except TelegramError as e:
        logger.error(f"Ошибка при отправке сообщения об ошибке: {e}")
        
        
def generate_google_speech(text, output_file):
    try:
        client = texttospeech.TextToSpeechClient()
        input_text = texttospeech.SynthesisInput(text=text)
        voice = texttospeech.VoiceSelectionParams(
            language_code="ru-RU",
            ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL
        )
        audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.OGG_OPUS)
        response = client.synthesize_speech(input=input_text, voice=voice, audio_config=audio_config)
        with open(output_file, "wb") as out:
            out.write(response.audio_content)
        logger.info(f"Аудио ответ сохранен в файл {output_file}")
    except Exception as e:
        logger.error(f"Ошибка при генерации аудио через Google Text-to-Speech: {e}")


# Игра в слова
spanish_words = [
    "gato", "perro", "casa", "libro", "mesa", "silla", "agua", "comida", 
    "familia", "escuela", "amigo", "ciudad", "cielo", "sol", "luna", 
    "estrella", "flor", "árbol", "montaña", "río", "mar", "tierra", 
    "camino", "auto", "tren", "avión", "puerta", "ventana", "rojo", 
    "azul", "verde", "amarillo", "blanco", "negro", "feliz", "triste", 
    "rápido", "lento", "calor", "frío", "manzana", "plátano", "naranja", 
    "limón", "uva", "queso", "pan", "pescado", "carne", "pollo", "tenedor"
]

async def word_game(update: Update, context: CallbackContext):
    """Запуск игры в слова — бот начинает с рандомного слова"""
    
    # Бот генерирует случайное слово
    first_word = random.choice(spanish_words)
    context.user_data['last_word'] = first_word
    
    await update.message.reply_text(
        f"Начнем игру! Ваше слово: {first_word}. Напишите слово, которое начинается на букву '{first_word[-1]}'.",
        reply_markup=markup
    )
    context.user_data['in_word_game'] = True  # Игра активна

async def handle_word_response(update: Update, context: CallbackContext):
    """Обработка ответа игрока и ответ бота"""
    if context.user_data.get('in_word_game'):
        user_word = update.message.text.strip().lower()
        last_word = context.user_data.get("last_word")
        
        # Проверяем, начинается ли слово пользователя с последней буквы слова бота
        if user_word.startswith(last_word[-1]):
            
            # Ищем слово для ответа бота, которое начинается на последнюю букву слова пользователя
            possible_words = [word for word in spanish_words if word.startswith(user_word[-1])]
            
            if possible_words:
                bot_word = random.choice(possible_words)
                context.user_data['last_word'] = bot_word  # Сохраняем новое слово бота
                
                await update.message.reply_text(
                    f"Ваше слово: {user_word}. Моё слово: {bot_word}. Ваш ход — на букву '{bot_word[-1]}'.",
                    reply_markup=markup
                )
            else:
                await update.message.reply_text(
                    f"Ваше слово: {user_word}, но я не знаю больше слов на букву '{user_word[-1]}'. Вы выиграли!",
                    reply_markup=markup
                )
                context.user_data['in_word_game'] = False  # Завершаем игру
        else:
            await update.message.reply_text(
                f"Ваше слово должно начинаться на букву '{last_word[-1]}'. Попробуйте еще раз.",
                reply_markup=markup
            )
    else:
        await update.message.reply_text("Вы не начали игру. Используйте команду /wordgame, чтобы начать.")

# Завершение игры в слова
async def end_game(update: Update, context):
    if context.user_data.get('in_word_game'):
        await update.message.reply_text("Игра завершена. Надеюсь, вам понравилось!", reply_markup=markup)
        context.user_data.pop('in_word_game', None)
        context.user_data.pop('last_word', None)
    else:
        await update.message.reply_text("Вы сейчас не в игре.", reply_markup=markup)

# Основная функция для запуска бота
def main():
    application = ApplicationBuilder().token(telegram_token).build()

    # Регистрация обработчиков команд и сообщений
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice_message))  # Обработчик для голосовых сообщений
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("endgame", end_game))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)

    # Запуск бота
    logger.info("Бот запущен и ожидает сообщений.")
    application.run_polling()

if __name__ == '__main__':
    main()
