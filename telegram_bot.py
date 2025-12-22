# -*- coding: utf-8 -*-
"""
Telegram бот для уведомлений о снижении цен

Команды бота:
/start - Начало работы, получение кода привязки
/link <код> - Привязка аккаунта Pricio
/unlink - Отвязка аккаунта
/status - Статус подписок
/help - Помощь

Запуск: python telegram_bot.py
"""

import logging
import sqlite3
import secrets
import asyncio
from datetime import datetime, timedelta
from typing import Optional

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    print("[!] python-telegram-bot не установлен. Установите: pip install python-telegram-bot")

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_BOT_USERNAME, APP_URL, DATABASES

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# База данных пользователей
USERS_DB = 'users.db'

def get_users_db():
    """Подключение к базе пользователей"""
    conn = sqlite3.connect(USERS_DB)
    conn.row_factory = sqlite3.Row
    return conn


def generate_linking_code(chat_id: int) -> str:
    """Генерация кода привязки и сохранение в БД"""
    code = secrets.token_hex(4).upper()  # 8-символьный код
    
    # Сохраняем код в базу данных
    conn = get_users_db()
    expires_at = datetime.now() + timedelta(minutes=10)
    
    try:
        # Удаляем старые коды для этого chat_id
        conn.execute('DELETE FROM telegram_linking_codes WHERE chat_id = ?', (str(chat_id),))
        # Сохраняем новый код
        conn.execute(
            'INSERT INTO telegram_linking_codes (code, chat_id, expires_at) VALUES (?, ?, ?)',
            (code, str(chat_id), expires_at)
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Error saving linking code: {e}")
    finally:
        conn.close()
    
    return code


def get_user_by_telegram(chat_id: int) -> Optional[dict]:
    """Получить пользователя по Telegram chat_id"""
    conn = get_users_db()
    user = conn.execute(
        'SELECT id, username, email FROM users WHERE telegram_chat_id = ?',
        (str(chat_id),)
    ).fetchone()
    conn.close()
    return dict(user) if user else None


def link_telegram_to_user(user_id: int, chat_id: int) -> bool:
    """Привязать Telegram к аккаунту пользователя"""
    conn = get_users_db()
    try:
        conn.execute(
            'UPDATE users SET telegram_chat_id = ? WHERE id = ?',
            (str(chat_id), user_id)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error linking telegram: {e}")
        conn.close()
        return False


def unlink_telegram(chat_id: int) -> bool:
    """Отвязать Telegram от аккаунта"""
    conn = get_users_db()
    try:
        conn.execute(
            'UPDATE users SET telegram_chat_id = NULL WHERE telegram_chat_id = ?',
            (str(chat_id),)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error unlinking telegram: {e}")
        conn.close()
        return False


def get_user_alerts_count(user_id: int) -> int:
    """Получить количество активных подписок пользователя"""
    conn = get_users_db()
    count = conn.execute(
        'SELECT COUNT(*) FROM price_alerts WHERE user_id = ? AND is_active = 1',
        (user_id,)
    ).fetchone()[0]
    conn.close()
    return count


# ============================================================================
# КОМАНДЫ БОТА
# ============================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    chat_id = update.effective_chat.id
    user = get_user_by_telegram(chat_id)
    
    if user:
        # Пользователь уже привязан
        alerts_count = get_user_alerts_count(user['id'])
        await update.message.reply_text(
            f"👋 Привет, {user['username']}!\n\n"
            f"✅ Ваш аккаунт Pricio привязан.\n"
            f"🔔 Активных подписок: {alerts_count}\n\n"
            f"📱 Вы будете получать уведомления о снижении цен на отслеживаемые товары.\n\n"
            f"Команды:\n"
            f"/status - Статус подписок\n"
            f"/unlink - Отвязать аккаунт\n"
            f"/help - Помощь"
        )
    else:
        # Новый пользователь - выдаём код привязки
        code = generate_linking_code(chat_id)
        
        # Показываем кнопку только если URL не localhost
        reply_markup = None
        if APP_URL and 'localhost' not in APP_URL and '127.0.0.1' not in APP_URL:
            keyboard = [[InlineKeyboardButton("🌐 Открыть Pricio", url=APP_URL)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
        
        message_text = (
            f"👋 Добро пожаловать в Pricio Notify Bot!\n\n"
            f"Этот бот отправляет уведомления о снижении цен на товары, "
            f"которые вы отслеживаете на сайте.\n\n"
            f"📌 Для привязки аккаунта:\n"
            f"1. Войдите в свой аккаунт на сайте Pricio\n"
            f"2. Перейдите в Профиль → Настройки\n"
            f"3. Введите этот код привязки:\n\n"
            f"🔑 <code>{code}</code>\n\n"
            f"⏰ Код действителен 10 минут.\n\n"
        )
        
        if reply_markup:
            message_text += "Используйте кнопку ниже для перехода на сайт."
        else:
            message_text += f"Сайт: {APP_URL}"
        
        await update.message.reply_text(
            message_text,
            parse_mode='HTML',
            reply_markup=reply_markup
        )


async def link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /link - привязка через код с сайта"""
    chat_id = update.effective_chat.id
    
    # Проверяем, не привязан ли уже
    existing_user = get_user_by_telegram(chat_id)
    if existing_user:
        await update.message.reply_text(
            f"✅ Ваш Telegram уже привязан к аккаунту: {existing_user['username']}\n\n"
            f"Для смены аккаунта сначала отвяжите текущий: /unlink"
        )
        return
    
    # Если код не передан - выдаём новый код
    if not context.args:
        code = generate_linking_code(chat_id)
        await update.message.reply_text(
            f"📌 Ваш код привязки:\n\n"
            f"🔑 <code>{code}</code>\n\n"
            f"Введите этот код в настройках профиля на сайте Pricio.\n"
            f"⏰ Код действителен 10 минут.",
            parse_mode='HTML'
        )
        return
    
    # Здесь мог бы быть код для обратной привязки (с сайта)
    await update.message.reply_text(
        "ℹ️ Для привязки аккаунта введите код в настройках профиля на сайте.\n"
        "Используйте /link без аргументов для получения нового кода."
    )


async def unlink_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /unlink - отвязка аккаунта"""
    chat_id = update.effective_chat.id
    user = get_user_by_telegram(chat_id)
    
    if not user:
        await update.message.reply_text(
            "❌ Ваш Telegram не привязан ни к одному аккаунту.\n"
            "Используйте /start для привязки."
        )
        return
    
    if unlink_telegram(chat_id):
        await update.message.reply_text(
            f"✅ Аккаунт {user['username']} успешно отвязан.\n\n"
            f"Вы больше не будете получать уведомления о ценах.\n"
            f"Для повторной привязки используйте /start"
        )
    else:
        await update.message.reply_text("❌ Ошибка при отвязке. Попробуйте позже.")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /status - статус подписок"""
    chat_id = update.effective_chat.id
    user = get_user_by_telegram(chat_id)
    
    if not user:
        await update.message.reply_text(
            "❌ Аккаунт не привязан. Используйте /start для привязки."
        )
        return
    
    # Получаем подписки пользователя
    conn = get_users_db()
    alerts = conn.execute('''
        SELECT store_id, product_id, target_price, created_at, last_price
        FROM price_alerts 
        WHERE user_id = ? AND is_active = 1
        ORDER BY created_at DESC
        LIMIT 10
    ''', (user['id'],)).fetchall()
    conn.close()
    
    if not alerts:
        await update.message.reply_text(
            f"👤 Аккаунт: {user['username']}\n\n"
            f"📭 У вас нет активных подписок на товары.\n\n"
            f"Добавьте товары в отслеживание на сайте Pricio!",
        )
        return
    
    # Формируем список подписок
    text = f"👤 Аккаунт: {user['username']}\n"
    text += f"🔔 Активных подписок: {len(alerts)}\n\n"
    
    for i, alert in enumerate(alerts, 1):
        store_name = DATABASES.get(alert['store_id'], {}).get('name', alert['store_id'])
        target = f"≤ {alert['target_price']}₽" if alert['target_price'] else "любое снижение"
        last_price = f"{alert['last_price']}₽" if alert['last_price'] else "—"
        
        text += f"{i}. {store_name} (ID: {alert['product_id']})\n"
        text += f"   📊 Цель: {target} | Посл.: {last_price}\n\n"
    
    if len(alerts) == 10:
        text += "...\n(показаны первые 10 подписок)"
    
    await update.message.reply_text(text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help"""
    await update.message.reply_text(
        "🤖 <b>Pricio Notify Bot</b>\n\n"
        "Бот для получения уведомлений о снижении цен на товары.\n\n"
        "<b>Команды:</b>\n"
        "/start - Начало работы, получение кода привязки\n"
        "/link - Получить новый код привязки\n"
        "/unlink - Отвязать аккаунт Pricio\n"
        "/status - Статус ваших подписок\n"
        "/help - Эта справка\n\n"
        "<b>Как это работает:</b>\n"
        "1. Зарегистрируйтесь на сайте Pricio\n"
        "2. Привяжите Telegram через настройки профиля\n"
        "3. Добавляйте товары в отслеживание\n"
        "4. Получайте уведомления при снижении цен! 📉\n\n"
        f"🌐 Сайт: {APP_URL}",
        parse_mode='HTML'
    )


# ============================================================================
# ФУНКЦИИ ОТПРАВКИ УВЕДОМЛЕНИЙ
# ============================================================================

async def send_price_alert(bot, chat_id: int, product_name: str, store_name: str,
                           old_price: float, new_price: float, product_url: str):
    """Отправить уведомление о снижении цены"""
    savings = old_price - new_price
    percent = (savings / old_price) * 100
    
    keyboard = [[InlineKeyboardButton("🛒 Посмотреть товар", url=product_url)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        f"🔔 <b>Цена снизилась!</b>\n\n"
        f"📦 {product_name}\n"
        f"🏪 {store_name}\n\n"
        f"💰 Было: <s>{old_price:.2f}₽</s>\n"
        f"✅ Стало: <b>{new_price:.2f}₽</b>\n\n"
        f"📉 Экономия: {savings:.2f}₽ ({percent:.1f}%)"
    )
    
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        logger.info(f"Sent price alert to {chat_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to send alert to {chat_id}: {e}")
        return False


# ============================================================================
# ЗАПУСК БОТА
# ============================================================================

def main():
    """Запуск бота"""
    if not TELEGRAM_AVAILABLE:
        print("[ERROR] python-telegram-bot не установлен!")
        print("Установите: pip install python-telegram-bot")
        return
    
    if TELEGRAM_BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
        print("[ERROR] Установите токен бота!")
        print("1. Создайте бота у @BotFather в Telegram")
        print("2. Укажите токен в config.py или переменной окружения TELEGRAM_BOT_TOKEN")
        return
    
    print(f"[*] Запуск Pricio Notify Bot...")
    print(f"[*] Bot username: @{TELEGRAM_BOT_USERNAME}")
    
    # Создаём приложение
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("link", link_command))
    application.add_handler(CommandHandler("unlink", unlink_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("help", help_command))
    
    # Запускаем бота
    print("[OK] Бот запущен. Нажмите Ctrl+C для остановки.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()

