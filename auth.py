# -*- coding: utf-8 -*-
"""
Модуль авторизации и управления пользователями
"""

import sqlite3
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from flask import session, redirect, url_for, flash, request

# База данных пользователей
USERS_DB = 'users.db'


def get_users_db():
    """Получить подключение к базе пользователей"""
    if not os.path.exists(USERS_DB):
        init_users_db()
    conn = sqlite3.connect(USERS_DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_users_db():
    """Инициализация базы данных пользователей"""
    conn = sqlite3.connect(USERS_DB)
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            telegram_chat_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        )
    ''')
    
    # Таблица избранного
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            store_id TEXT NOT NULL,
            product_id TEXT NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(user_id, store_id, product_id)
        )
    ''')
    
    # Таблица подписок на снижение цены
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS price_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            store_id TEXT NOT NULL,
            product_id TEXT NOT NULL,
            target_price REAL,
            notify_any_decrease INTEGER DEFAULT 1,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_notified_at TIMESTAMP,
            last_price REAL,
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(user_id, store_id, product_id)
        )
    ''')
    
    # Индексы для быстрого поиска
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_favorites_user ON favorites(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_favorites_product ON favorites(store_id, product_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_alerts_user ON price_alerts(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_alerts_product ON price_alerts(store_id, product_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_alerts_active ON price_alerts(is_active)')
    
    conn.commit()
    conn.close()
    print("[OK] База данных пользователей инициализирована")


# ============================================================================
# АВТОРИЗАЦИЯ
# ============================================================================

def register_user(username: str, email: str, password: str) -> dict:
    """
    Регистрация нового пользователя
    
    Returns:
        dict: {'success': bool, 'message': str, 'user_id': int (if success)}
    """
    if len(username) < 3:
        return {'success': False, 'message': 'Имя пользователя должно содержать минимум 3 символа'}
    
    if len(password) < 6:
        return {'success': False, 'message': 'Пароль должен содержать минимум 6 символов'}
    
    if '@' not in email:
        return {'success': False, 'message': 'Введите корректный email'}
    
    conn = get_users_db()
    cursor = conn.cursor()
    
    # Проверяем, не занят ли username или email
    existing = cursor.execute(
        'SELECT id FROM users WHERE username = ? OR email = ?',
        (username, email)
    ).fetchone()
    
    if existing:
        conn.close()
        return {'success': False, 'message': 'Пользователь с таким именем или email уже существует'}
    
    # Создаём пользователя
    password_hash = generate_password_hash(password)
    
    try:
        cursor.execute(
            'INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
            (username, email, password_hash)
        )
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        return {'success': True, 'message': 'Регистрация успешна!', 'user_id': user_id}
    except Exception as e:
        conn.close()
        return {'success': False, 'message': f'Ошибка при регистрации: {str(e)}'}


def login_user(login: str, password: str) -> dict:
    """
    Авторизация пользователя
    
    Args:
        login: username или email
        password: пароль
    
    Returns:
        dict: {'success': bool, 'message': str, 'user': dict (if success)}
    """
    conn = get_users_db()
    
    # Ищем пользователя по username или email
    user = conn.execute(
        'SELECT * FROM users WHERE username = ? OR email = ?',
        (login, login)
    ).fetchone()
    
    if not user:
        conn.close()
        return {'success': False, 'message': 'Пользователь не найден'}
    
    if not check_password_hash(user['password_hash'], password):
        conn.close()
        return {'success': False, 'message': 'Неверный пароль'}
    
    # Обновляем last_login
    conn.execute(
        'UPDATE users SET last_login = ? WHERE id = ?',
        (datetime.now(), user['id'])
    )
    conn.commit()
    conn.close()
    
    return {
        'success': True,
        'message': 'Вход выполнен!',
        'user': {
            'id': user['id'],
            'username': user['username'],
            'email': user['email'],
            'telegram_chat_id': user['telegram_chat_id']
        }
    }


def get_current_user():
    """Получить текущего пользователя из сессии"""
    if 'user_id' not in session:
        return None
    
    conn = get_users_db()
    user = conn.execute(
        'SELECT id, username, email, telegram_chat_id FROM users WHERE id = ?',
        (session['user_id'],)
    ).fetchone()
    conn.close()
    
    if user:
        return dict(user)
    return None


def login_required(f):
    """Декоратор для защиты маршрутов"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Пожалуйста, войдите в систему', 'warning')
            return redirect(url_for('login_page', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


# ============================================================================
# ИЗБРАННОЕ
# ============================================================================

def add_to_favorites(user_id: int, store_id: str, product_id: str) -> dict:
    """Добавить товар в избранное"""
    conn = get_users_db()
    try:
        conn.execute(
            'INSERT OR IGNORE INTO favorites (user_id, store_id, product_id) VALUES (?, ?, ?)',
            (user_id, store_id, product_id)
        )
        conn.commit()
        conn.close()
        return {'success': True, 'message': 'Добавлено в избранное'}
    except Exception as e:
        conn.close()
        return {'success': False, 'message': str(e)}


def remove_from_favorites(user_id: int, store_id: str, product_id: str) -> dict:
    """Удалить товар из избранного"""
    conn = get_users_db()
    conn.execute(
        'DELETE FROM favorites WHERE user_id = ? AND store_id = ? AND product_id = ?',
        (user_id, store_id, product_id)
    )
    conn.commit()
    conn.close()
    return {'success': True, 'message': 'Удалено из избранного'}


def get_favorites(user_id: int) -> list:
    """Получить список избранных товаров пользователя"""
    conn = get_users_db()
    favorites = conn.execute(
        'SELECT store_id, product_id, added_at FROM favorites WHERE user_id = ? ORDER BY added_at DESC',
        (user_id,)
    ).fetchall()
    conn.close()
    return [dict(f) for f in favorites]


def is_favorite(user_id: int, store_id: str, product_id: str) -> bool:
    """Проверить, в избранном ли товар"""
    conn = get_users_db()
    result = conn.execute(
        'SELECT 1 FROM favorites WHERE user_id = ? AND store_id = ? AND product_id = ?',
        (user_id, store_id, product_id)
    ).fetchone()
    conn.close()
    return result is not None


# ============================================================================
# ПОДПИСКИ НА СНИЖЕНИЕ ЦЕНЫ
# ============================================================================

def add_price_alert(user_id: int, store_id: str, product_id: str, 
                    target_price: float = None, notify_any_decrease: bool = True) -> dict:
    """
    Подписаться на уведомление о снижении цены
    
    Args:
        user_id: ID пользователя
        store_id: ID магазина
        product_id: ID товара
        target_price: Целевая цена (None = любое снижение)
        notify_any_decrease: Уведомлять о любом снижении
    """
    conn = get_users_db()
    try:
        conn.execute('''
            INSERT OR REPLACE INTO price_alerts 
            (user_id, store_id, product_id, target_price, notify_any_decrease, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
        ''', (user_id, store_id, product_id, target_price, int(notify_any_decrease)))
        conn.commit()
        conn.close()
        return {'success': True, 'message': 'Подписка оформлена'}
    except Exception as e:
        conn.close()
        return {'success': False, 'message': str(e)}


def remove_price_alert(user_id: int, store_id: str, product_id: str) -> dict:
    """Отписаться от уведомлений о цене товара"""
    conn = get_users_db()
    conn.execute(
        'DELETE FROM price_alerts WHERE user_id = ? AND store_id = ? AND product_id = ?',
        (user_id, store_id, product_id)
    )
    conn.commit()
    conn.close()
    return {'success': True, 'message': 'Подписка отменена'}


def get_price_alerts(user_id: int, active_only: bool = True) -> list:
    """Получить список подписок пользователя"""
    conn = get_users_db()
    query = 'SELECT * FROM price_alerts WHERE user_id = ?'
    if active_only:
        query += ' AND is_active = 1'
    query += ' ORDER BY created_at DESC'
    
    alerts = conn.execute(query, (user_id,)).fetchall()
    conn.close()
    return [dict(a) for a in alerts]


def has_price_alert(user_id: int, store_id: str, product_id: str) -> bool:
    """Проверить, есть ли подписка на товар"""
    conn = get_users_db()
    result = conn.execute(
        'SELECT 1 FROM price_alerts WHERE user_id = ? AND store_id = ? AND product_id = ? AND is_active = 1',
        (user_id, store_id, product_id)
    ).fetchone()
    conn.close()
    return result is not None


def check_price_alerts_for_product(store_id: str, product_id: str, new_price: float, old_price: float) -> list:
    """
    Проверить подписки для товара при изменении цены
    Возвращает список пользователей для уведомления
    
    ⚠️ ЗАГЛУШКА: В будущем здесь будет интеграция с Telegram ботом
    """
    if new_price >= old_price:
        return []  # Цена не снизилась
    
    conn = get_users_db()
    
    # Находим всех подписчиков
    alerts = conn.execute('''
        SELECT pa.*, u.username, u.email, u.telegram_chat_id
        FROM price_alerts pa
        JOIN users u ON pa.user_id = u.id
        WHERE pa.store_id = ? AND pa.product_id = ? AND pa.is_active = 1
    ''', (store_id, product_id)).fetchall()
    
    notifications = []
    
    for alert in alerts:
        should_notify = False
        
        # Проверяем условия уведомления
        if alert['notify_any_decrease']:
            should_notify = True
        elif alert['target_price'] and new_price <= alert['target_price']:
            should_notify = True
        
        if should_notify:
            notifications.append({
                'user_id': alert['user_id'],
                'username': alert['username'],
                'email': alert['email'],
                'telegram_chat_id': alert['telegram_chat_id'],
                'old_price': old_price,
                'new_price': new_price,
                'target_price': alert['target_price']
            })
            
            # Обновляем запись
            conn.execute('''
                UPDATE price_alerts 
                SET last_notified_at = ?, last_price = ?
                WHERE id = ?
            ''', (datetime.now(), new_price, alert['id']))
    
    conn.commit()
    conn.close()
    
    # ⚠️ ЗАГЛУШКА: Здесь будет отправка уведомлений через Telegram бота
    # TODO: Интеграция с Telegram Bot API
    for n in notifications:
        print(f"[NOTIFY] Уведомление для {n['username']}: цена снизилась {old_price} руб -> {new_price} руб")
    
    return notifications


def update_telegram_chat_id(user_id: int, chat_id: str) -> dict:
    """Привязать Telegram для уведомлений"""
    conn = get_users_db()
    conn.execute(
        'UPDATE users SET telegram_chat_id = ? WHERE id = ?',
        (chat_id, user_id)
    )
    conn.commit()
    conn.close()
    return {'success': True, 'message': 'Telegram привязан'}


# Инициализация при импорте
init_users_db()

