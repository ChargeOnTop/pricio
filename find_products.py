# -*- coding: utf-8 -*-
import re
import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

with open('page_source.html', 'r', encoding='utf-8') as f:
    html = f.read()

print("="*60)
print("АНАЛИЗ СТРУКТУРЫ ТОВАРОВ")
print("="*60)

# Ищем ссылки на продукты
print("\n1. Ссылки на /product/:")
product_links = re.findall(r'href="(/product/[^"]+)"', html)
print(f"   Найдено: {len(product_links)}")
for link in product_links[:5]:
    print(f"   {link}")

# Ищем названия товаров которые видели на скриншоте
print("\n2. Поиск известных товаров:")
products_to_find = [
    "Oldenburger",
    "Простоквашино", 
    "Adrenaline",
    "Hochland",
    "Вкуснотеево"
]

for prod in products_to_find:
    idx = html.find(prod)
    if idx > 0:
        print(f"\n   {prod} найден на позиции {idx}")
        # Смотрим контекст
        start = max(0, idx - 300)
        end = min(len(html), idx + 200)
        snippet = html[start:end]
        
        # Ищем родительские теги
        tags = re.findall(r'<([a-z]+)[^>]*class="([^"]*)"', snippet)
        print("   Теги и классы рядом:")
        for tag, cls in tags[-5:]:
            print(f"     <{tag}> class=\"{cls[:60]}\"")

# Ищем элементы с data-qa
print("\n3. Элементы data-qa:")
qa_elements = re.findall(r'data-qa="([^"]+)"', html)
unique_qa = set(qa_elements)
for qa in sorted(unique_qa)[:15]:
    print(f"   {qa}")

# Ищем цены
print("\n4. Структура цен:")
# Ищем паттерн цены типа 169<sup>99</sup>
price_pattern = r'>(\d+)<sup[^>]*>(\d+)</sup>'
prices = re.findall(price_pattern, html)
print(f"   Найдено цен: {len(prices)}")
for p in prices[:5]:
    print(f"   {p[0]}.{p[1]} руб")



