# -*- coding: utf-8 -*-
import re
import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

with open('page_source.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Ищем классы содержащие product или card
pattern = r'class="([^"]*)"'
all_classes = re.findall(pattern, html)

unique = set()
for c in all_classes:
    for part in c.split():
        if 'product' in part.lower() or 'card' in part.lower() or 'item' in part.lower():
            unique.add(part)

print('Классы с product/card/item:')
for c in sorted(unique)[:40]:
    print(f'  {c}')

# Ищем data-атрибуты
print('\nData-атрибуты:')
data_attrs = re.findall(r'(data-[a-z-]+)=', html)
unique_data = set(data_attrs)
for d in sorted(unique_data)[:20]:
    print(f'  {d}')

# Ищем структуру около цены
print('\nСтруктура около цены (169):')
idx = html.find('169')
if idx > 0:
    snippet = html[max(0, idx-200):idx+100]
    # Находим классы в этом фрагменте
    classes_near = re.findall(r'class="([^"]+)"', snippet)
    for c in classes_near:
        print(f'  {c[:80]}')



