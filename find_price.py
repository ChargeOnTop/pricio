# -*- coding: utf-8 -*-
import re
import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

with open('page_source.html', 'r', encoding='utf-8') as f:
    html = f.read()

print("Поиск структуры цен...")

# Ищем 169 (цена со скриншота)
idx = html.find('>169<')
if idx > 0:
    print(f"\n'>169<' найдено на позиции {idx}")
    snippet = html[idx-50:idx+150]
    print(f"Контекст:\n{snippet}")

# Ищем 99 как копейки
idx2 = html.find('>99<')
if idx2 > 0:
    print(f"\n'>99<' найдено на позиции {idx2}")
    snippet = html[idx2-100:idx2+50]
    print(f"Контекст:\n{snippet}")

# Ищем рубль
idx3 = html.find('₽')
if idx3 > 0:
    print(f"\n'₽' найдено на позиции {idx3}")
    snippet = html[idx3-100:idx3+20]
    print(f"Контекст:\n{snippet}")

# Ищем цены через регулярку
print("\n\nВсе числа перед ₽:")
prices = re.findall(r'(\d+)\s*₽', html)
print(f"Найдено: {len(prices)}")
print(f"Примеры: {prices[:10]}")

# Ищем цены в формате 16999 (без точки)
print("\n\nЧисла 3-5 цифр (возможные цены в копейках):")
nums = re.findall(r'>(\d{3,5})<', html)
# Фильтруем только те что похожи на цены
prices_raw = [n for n in nums if 1000 < int(n) < 500000]
print(f"Найдено: {len(prices_raw)}")
print(f"Примеры: {prices_raw[:15]}")
if prices_raw:
    print("Как цены (разделить на 100):")
    for p in prices_raw[:10]:
        print(f"  {p} -> {int(p)/100:.2f} руб")



