# -*- coding: utf-8 -*-
"""Отладка цен"""

import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time
import re

print("="*60)
print("  ОТЛАДКА ЦЕН")
print("="*60)

options = Options()
options.add_argument('--window-size=1920,1080')

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)

print("\n[1] Загрузка каталога...")
driver.get("https://5ka.ru/catalog/")

print("\n>>> Пройдите капчу если нужно")
input(">>> Нажмите ENTER когда загрузится... ")

# Переходим в категорию "Молочная продукция"
driver.get("https://5ka.ru/catalog/251C12887/?page=41")
time.sleep(3)

# Прокрутка
for _ in range(10):
    driver.execute_script("window.scrollBy(0, 500);")
    time.sleep(0.3)
time.sleep(2)

# Ищем контейнер
try:
    container = driver.find_element(By.CSS_SELECTOR, 'div[itemtype="https://schema.org/ItemList"]')
    items = container.find_elements(By.CSS_SELECTOR, '> div')
except Exception as e:
    print(f"Контейнер не найден: {e}")
    # Пробуем найти товары напрямую
    items = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/product/"]')
    print(f"Найдено ссылок на товары: {len(items)}")

print(f"\nНайдено {len(items)} элементов")

# Берём первые 3 товара и анализируем
for i, item in enumerate(items[:5]):
    print(f"\n{'='*50}")
    print(f"ТОВАР {i+1}")
    print('='*50)
    
    item_html = item.get_attribute("outerHTML")
    
    # Ищем meta price
    price_meta = re.findall(r'<meta[^>]*itemprop="price"[^>]*>', item_html)
    print(f"\nmeta itemprop='price': {price_meta}")
    
    # Ищем все content=
    contents = re.findall(r'content="([\d.]+)"', item_html)
    print(f"Все content='число': {contents}")
    
    # Ищем числа перед ₽
    rubles = re.findall(r'>(\d+)<[^>]*>[^<]*>(\d+)<[^>]*>[^<]*>₽', item_html)
    print(f"Числа перед ₽: {rubles}")
    
    # Текст элемента
    text = item.text[:300].replace('\n', ' | ')
    print(f"\nТекст: {text}")
    
    # Сохраним HTML первого товара
    if i == 0:
        with open('debug_item.html', 'w', encoding='utf-8') as f:
            f.write(item_html)
        print("\nHTML сохранён в debug_item.html")

driver.quit()
print("\n[OK] Готово!")

