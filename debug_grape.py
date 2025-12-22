# -*- coding: utf-8 -*-
"""Отладка цены винограда"""

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
print("  ОТЛАДКА ЦЕНЫ ВИНОГРАДА")
print("="*60)

options = Options()
options.add_argument('--window-size=1920,1080')

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)

print("\n[1] Загрузка каталога...")
driver.get("https://5ka.ru/catalog/")

print("\n>>> Пройдите капчу если нужно")
input(">>> Нажмите ENTER когда загрузится... ")

# Ищем виноград
driver.get("https://5ka.ru/catalog/251C12886/?page=41")  # Овощи/фрукты
time.sleep(3)

for _ in range(15):
    driver.execute_script("window.scrollBy(0, 500);")
    time.sleep(0.3)
time.sleep(2)

# Ищем товар с "Виноград" или "Шайн"
html = driver.page_source

# Ищем позицию винограда
idx = html.find("Виноград Шайн")
if idx == -1:
    idx = html.find("Шайн Мускат")
if idx == -1:
    idx = html.find("Виноград")

if idx > 0:
    print(f"\nНайден на позиции {idx}")
    
    # Берём большой кусок HTML вокруг
    start = max(0, idx - 2000)
    end = min(len(html), idx + 1000)
    
    # Ищем начало карточки (ближайший <a с product)
    snippet = html[start:end]
    
    # Сохраняем
    with open('debug_grape.html', 'w', encoding='utf-8') as f:
        f.write(snippet)
    print("Сохранено в debug_grape.html")
    
    # Анализируем цены в этом фрагменте
    print("\n--- Анализ цен ---")
    
    # Все content="число"
    contents = re.findall(r'content="([\d.]+)"', snippet)
    print(f"Все content: {contents}")
    
    # itemprop="price"
    prices = re.findall(r'itemprop="price"[^>]*content="([\d.]+)"', snippet)
    print(f"itemprop=price: {prices}")
    
    # Числа перед ₽
    before_rub = re.findall(r'>(\d+)<[^₽]{0,50}>(\d+)<[^₽]{0,20}>₽', snippet)
    print(f"Числа перед ₽: {before_rub}")
    
    # Ищем 449
    if "449" in snippet:
        idx449 = snippet.find("449")
        print(f"\n449 найдено! Контекст:")
        print(snippet[max(0,idx449-100):idx449+100])
else:
    print("Виноград не найден")

driver.quit()
print("\n[OK] Готово!")



