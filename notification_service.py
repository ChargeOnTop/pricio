# -*- coding: utf-8 -*-
"""
Сервис уведомлений о снижении цен

Проверяет изменения цен в базах данных и отправляет
уведомления пользователям через Telegram.

Запуск:
    python notification_service.py          # Одноразовая проверка
    python notification_service.py --daemon # Постоянная работа (каждый час)
"""

import sqlite3
import asyncio
import argparse
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional

try:
    from telegram import Bot
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    print("[!] python-telegram-bot не установлен")

from config import (
    TELEGRAM_BOT_TOKEN, 
    DATABASES, 
    APP_URL,
    PRICE_CHECK_INTERVAL,
    MIN_PRICE_DIFFERENCE
)

# База пользователей
USERS_DB = 'users.db'


def get_users_db():
    """Подключение к базе пользователей"""
    conn = sqlite3.connect(USERS_DB)
    conn.row_factory = sqlite3.Row
    return conn


def get_store_db(store_id: str):
    """Подключение к базе магазина"""
    # Проверяем оба возможных ключа для совместимости
    db_info = DATABASES.get(store_id, {})
    db_path = db_info.get('path') or db_info.get('file')
    if not db_path:
        return None
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_active_alerts() -> List[Dict]:
    """Получить все активные подписки с telegram_chat_id"""
    conn = get_users_db()
    alerts = conn.execute('''
        SELECT 
            pa.id as alert_id,
            pa.user_id,
            pa.store_id,
            pa.product_id,
            pa.target_price,
            pa.notify_any_decrease,
            pa.last_price,
            pa.last_notified_at,
            u.username,
            u.telegram_chat_id
        FROM price_alerts pa
        JOIN users u ON pa.user_id = u.id
        WHERE pa.is_active = 1 
          AND u.telegram_chat_id IS NOT NULL
          AND u.telegram_chat_id != ''
    ''').fetchall()
    conn.close()
    return [dict(a) for a in alerts]


def get_product_info(store_id: str, product_id: str) -> Optional[Dict]:
    """Получить информацию о товаре"""
    conn = get_store_db(store_id)
    if not conn:
        return None
    
    product = conn.execute(
        'SELECT name, current_price as price FROM products WHERE product_id = ?',
        (product_id,)
    ).fetchone()
    conn.close()
    
    return dict(product) if product else None


def get_price_history(store_id: str, product_id: str, limit: int = 2) -> List[Dict]:
    """Получить последние записи истории цен"""
    conn = get_store_db(store_id)
    if not conn:
        return []
    
    history = conn.execute('''
        SELECT price, recorded_at as timestamp
        FROM price_history
        WHERE product_id = ?
        ORDER BY recorded_at DESC
        LIMIT ?
    ''', (product_id, limit)).fetchall()
    conn.close()
    
    return [dict(h) for h in history]


def update_alert_after_notification(alert_id: int, new_price: float):
    """Обновить подписку после отправки уведомления"""
    conn = get_users_db()
    conn.execute('''
        UPDATE price_alerts 
        SET last_notified_at = ?, last_price = ?
        WHERE id = ?
    ''', (datetime.now(), new_price, alert_id))
    conn.commit()
    conn.close()


def should_notify(alert: Dict, current_price: float) -> tuple:
    """
    Проверить, нужно ли отправлять уведомление
    
    Returns:
        (should_notify: bool, reason: str, old_price: float)
    """
    last_price = alert.get('last_price')
    target_price = alert.get('target_price')
    notify_any = alert.get('notify_any_decrease', 1)
    
    # Если это первая проверка - сохраняем цену, не уведомляем
    if last_price is None:
        return (False, 'first_check', current_price)
    
    # Цена не изменилась или выросла
    if current_price >= last_price:
        return (False, 'no_decrease', last_price)
    
    # Проверяем минимальную разницу
    diff = last_price - current_price
    if diff < MIN_PRICE_DIFFERENCE:
        return (False, 'too_small_diff', last_price)
    
    # Проверяем последнее уведомление (не чаще раза в час)
    last_notified = alert.get('last_notified_at')
    if last_notified:
        try:
            last_time = datetime.fromisoformat(str(last_notified))
            if datetime.now() - last_time < timedelta(hours=1):
                return (False, 'too_soon', last_price)
        except:
            pass
    
    # Уведомляем о любом снижении
    if notify_any:
        return (True, 'any_decrease', last_price)
    
    # Уведомляем о достижении целевой цены
    if target_price and current_price <= target_price:
        return (True, 'target_reached', last_price)
    
    return (False, 'target_not_reached', last_price)


async def send_notification(bot: Bot, chat_id: str, product_name: str, 
                           store_name: str, store_id: str, product_id: str,
                           old_price: float, new_price: float) -> bool:
    """Отправить уведомление в Telegram"""
    
    savings = old_price - new_price
    percent = (savings / old_price) * 100
    product_url = f"{APP_URL}/store/{store_id}/product/{product_id}"
    
    text = (
        f"🔔 <b>Цена снизилась!</b>\n\n"
        f"📦 {product_name}\n"
        f"🏪 {store_name}\n\n"
        f"💰 Было: <s>{old_price:.2f}₽</s>\n"
        f"✅ Стало: <b>{new_price:.2f}₽</b>\n\n"
        f"📉 Экономия: {savings:.2f}₽ ({percent:.1f}%)\n\n"
        f"🔗 <a href='{product_url}'>Открыть товар</a>"
    )
    
    try:
        await bot.send_message(
            chat_id=int(chat_id),
            text=text,
            parse_mode='HTML',
            disable_web_page_preview=True
        )
        print(f"  [OK] Уведомление отправлено: {chat_id}")
        return True
    except Exception as e:
        print(f"  [ERR] Ошибка отправки {chat_id}: {e}")
        return False


async def check_and_notify():
    """Основная функция проверки цен и отправки уведомлений"""
    
    print(f"\n{'='*60}")
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Проверка цен...")
    print('='*60)
    
    if not TELEGRAM_AVAILABLE:
        print("[ERR] Telegram не доступен")
        return
    
    if TELEGRAM_BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
        print("[ERR] Токен бота не настроен")
        return
    
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    
    # Получаем все активные подписки
    alerts = get_active_alerts()
    print(f"[*] Активных подписок: {len(alerts)}")
    
    if not alerts:
        print("[*] Нет подписок для проверки")
        return
    
    notifications_sent = 0
    errors = 0
    
    for alert in alerts:
        store_id = alert['store_id']
        product_id = alert['product_id']
        store_name = DATABASES.get(store_id, {}).get('name', store_id)
        
        # Получаем текущую цену товара
        product = get_product_info(store_id, product_id)
        if not product:
            print(f"  [SKIP] Товар не найден: {store_id}/{product_id}")
            continue
        
        current_price = product['price']
        product_name = product['name']
        
        # Проверяем, нужно ли уведомлять
        should, reason, old_price = should_notify(alert, current_price)
        
        if reason == 'first_check':
            # Первая проверка - сохраняем цену
            update_alert_after_notification(alert['alert_id'], current_price)
            print(f"  [INIT] {product_name[:40]}... - {current_price} rub")
            continue
        
        if not should:
            continue
        
        print(f"\n  [NOTIFY] {product_name[:40]}...")
        print(f"           {old_price} rub -> {current_price} rub ({reason})")
        
        # Отправляем уведомление
        success = await send_notification(
            bot=bot,
            chat_id=alert['telegram_chat_id'],
            product_name=product_name,
            store_name=store_name,
            store_id=store_id,
            product_id=product_id,
            old_price=old_price,
            new_price=current_price
        )
        
        if success:
            notifications_sent += 1
            update_alert_after_notification(alert['alert_id'], current_price)
        else:
            errors += 1
    
    print(f"\n[*] Итого: отправлено {notifications_sent}, ошибок {errors}")


async def daemon_mode():
    """Режим демона - постоянная проверка"""
    print(f"[*] Запуск в режиме демона")
    print(f"[*] Интервал проверки: {PRICE_CHECK_INTERVAL} сек ({PRICE_CHECK_INTERVAL//60} мин)")
    
    while True:
        try:
            await check_and_notify()
        except Exception as e:
            print(f"[ERR] Ошибка: {e}")
        
        print(f"\n[*] Следующая проверка через {PRICE_CHECK_INTERVAL//60} мин...")
        await asyncio.sleep(PRICE_CHECK_INTERVAL)


def main():
    """Точка входа"""
    parser = argparse.ArgumentParser(description='Сервис уведомлений о ценах')
    parser.add_argument('--daemon', '-d', action='store_true',
                       help='Запуск в режиме демона (постоянная работа)')
    args = parser.parse_args()
    
    if args.daemon:
        asyncio.run(daemon_mode())
    else:
        asyncio.run(check_and_notify())


if __name__ == '__main__':
    main()

