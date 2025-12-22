import sqlite3
import sys
sys.stdout.reconfigure(encoding='utf-8')

# Проверяем 5ка
conn = sqlite3.connect('products.db')
c = conn.cursor()

# Ищем товары где "банан" в начале названия
c.execute("SELECT product_id, name, category FROM products WHERE LOWER(name) LIKE 'банан%' LIMIT 5")
print("=== Бананы (начинается с) в Пятёрочке ===")
for row in c.fetchall():
    print(f"  ID: {row[0]} | {row[1][:50]} | {row[2]}")

c.execute("SELECT product_id, name, category FROM products WHERE LOWER(name) LIKE '%банан%' LIMIT 10")
print("\n=== Бананы (содержит) в Пятёрочке ===")
for row in c.fetchall():
    print(f"  ID: {row[0]} | {row[1][:50]} | {row[2]}")
conn.close()

# Проверяем Магнит
conn = sqlite3.connect('products_magnit.db')
c = conn.cursor()
c.execute("SELECT product_id, name, category FROM products WHERE LOWER(name) LIKE 'банан%' LIMIT 5")
print("\n=== Бананы (начинается с) в Магните ===")
for row in c.fetchall():
    print(f"  ID: {row[0]} | {row[1][:50]} | {row[2]}")

c.execute("SELECT product_id, name, category FROM products WHERE LOWER(name) LIKE '%банан%' LIMIT 10")
print("\n=== Бананы (содержит) в Магните ===")
for row in c.fetchall():
    print(f"  ID: {row[0]} | {row[1][:50]} | {row[2]}")
conn.close()

