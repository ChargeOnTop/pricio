# -*- coding: utf-8 -*-
import sqlite3

conn = sqlite3.connect('products.db')
c = conn.cursor()

try:
    c.execute('SELECT COUNT(*) FROM products')
    count = c.fetchone()[0]
    print(f"Товаров в БД: {count}")
    
    c.execute('SELECT name, price FROM products LIMIT 5')
    print("\nПримеры:")
    for row in c.fetchall():
        name = row[0][:40] if row[0] else "Без названия"
        print(f"  {name}... = {row[1]} руб")
except Exception as e:
    print(f"Ошибка: {e}")
    print("База данных пуста или не существует")

conn.close()



