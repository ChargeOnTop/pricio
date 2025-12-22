import sqlite3

conn = sqlite3.connect('products_magnit.db')
cur = conn.cursor()

# Найти все товары с "лимон" в названии
cur.execute("SELECT product_id, name FROM products WHERE LOWER(name) LIKE '%лимон%' LIMIT 15")
rows = cur.fetchall()

print("Товары с 'лимон' в названии:")
for row in rows:
    print(f"  {row[0]}: {row[1]}")

print()

# Найти товар "Лимоны"
cur.execute("SELECT product_id, name FROM products WHERE name LIKE 'Лимон%' LIMIT 5")
rows = cur.fetchall()
print("Товары начинающиеся на 'Лимон':")
for row in rows:
    print(f"  {row[0]}: {row[1]}")

conn.close()



