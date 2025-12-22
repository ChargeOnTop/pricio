# -*- coding: utf-8 -*-
"""
Инициализация базы данных с поддержкой истории цен
"""
import sqlite3
import os

DB_FILE = 'products.db'

def init_database():
    """Создаёт новую структуру БД"""
    
    # Удаляем старую БД
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
        print(f"[OK] Старая база {DB_FILE} удалена")
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Таблица товаров (без дубликатов)
    cursor.execute('''
        CREATE TABLE products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            category TEXT,
            current_price REAL DEFAULT 0,
            min_price REAL DEFAULT 0,
            max_price REAL DEFAULT 0,
            first_seen TIMESTAMP,
            last_updated TIMESTAMP
        )
    ''')
    
    # Таблица истории цен
    cursor.execute('''
        CREATE TABLE price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            price REAL NOT NULL,
            old_price REAL,
            recorded_at TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        )
    ''')
    
    # Индексы для быстрого поиска
    cursor.execute('CREATE INDEX idx_products_product_id ON products(product_id)')
    cursor.execute('CREATE INDEX idx_price_history_product_id ON price_history(product_id)')
    cursor.execute('CREATE INDEX idx_price_history_recorded_at ON price_history(recorded_at)')
    
    conn.commit()
    conn.close()
    
    print("[OK] База данных создана с новой структурой:")
    print("     - products: товары без дубликатов")
    print("     - price_history: история изменения цен")

if __name__ == "__main__":
    init_database()



