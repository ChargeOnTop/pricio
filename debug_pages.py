# -*- coding: utf-8 -*-
"""Отладка пагинации"""

import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import re

print("="*60)
print("  ОТЛАДКА ПАГИНАЦИИ")
print("="*60)

options = Options()
options.add_argument('--window-size=1920,1080')
options.add_experimental_option("excludeSwitches", ["enable-automation"])

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)

print("\n[1] Загрузка каталога...")
driver.get("https://5ka.ru/catalog/")

print("\n>>> Пройдите капчу если нужно")
input(">>> Нажмите ENTER когда каталог загрузится... ")

# Переходим в категорию "Готовая еда"
cat_url = "https://5ka.ru/catalog/gotovaya-eda--251C12884/"

print(f"\n[2] Тестируем категорию: Готовая еда")

for page in range(1, 4):
    if page == 1:
        url = cat_url
    else:
        url = f"{cat_url}?page={page}"
    
    print(f"\n--- Страница {page} ---")
    print(f"URL: {url}")
    
    driver.get(url)
    time.sleep(3)
    
    # Прокручиваем
    for _ in range(3):
        driver.execute_script("window.scrollBy(0, 500);")
        time.sleep(0.3)
    time.sleep(1)
    
    # Текущий URL после загрузки
    print(f"Текущий URL: {driver.current_url}")
    
    # Ищем ссылки на товары
    links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/product/']")
    print(f"Найдено ссылок на /product/: {len(links)}")
    
    # Уникальные ID товаров
    ids = set()
    for link in links:
        href = link.get_attribute("href") or ""
        match = re.search(r'--(\d+)/?', href)
        if match:
            ids.add(match.group(1))
    
    print(f"Уникальных товаров: {len(ids)}")
    
    # Показываем первые 3 товара
    if ids:
        print("Примеры ID:", list(ids)[:5])
    
    # Проверяем есть ли пагинация на странице
    page_text = driver.page_source
    if "?page=2" in page_text:
        print("Ссылка на page=2 есть в HTML")
    else:
        print("Ссылки на page=2 НЕТ в HTML")
    
    # Сохраняем скриншот
    driver.save_screenshot(f"debug_page{page}.png")
    print(f"Скриншот: debug_page{page}.png")

driver.quit()
print("\n[OK] Готово!")



