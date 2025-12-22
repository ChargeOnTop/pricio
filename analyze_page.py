# -*- coding: utf-8 -*-
"""Анализ структуры страницы 5ka.ru"""

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
print("  АНАЛИЗ СТРАНИЦЫ 5KA.RU")
print("="*60)

options = Options()
options.add_argument('--window-size=1920,1080')
options.add_experimental_option("excludeSwitches", ["enable-automation"])

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)

print("\n[1] Открываю 5ka.ru...")
driver.get("https://5ka.ru/catalog/")

print("\n>>> Пройдите капчу если нужно, затем закройте это окно")
print(">>> или подождите 60 секунд...")

# Ждём пока пользователь пройдёт капчу
for i in range(60):
    time.sleep(1)
    # Проверяем загрузился ли каталог
    if "catalog" in driver.current_url:
        try:
            links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/catalog/']")
            if len(links) > 5:
                print(f"\n[OK] Каталог загружен! ({len(links)} ссылок)")
                break
        except:
            pass
    if i % 10 == 0:
        print(f"  Ожидание... {60-i} сек")

time.sleep(3)

# Переходим в категорию
print("\n[2] Перехожу в категорию 'Молочная продукция'...")
driver.get("https://5ka.ru/catalog/251C12887/")
time.sleep(5)

# Прокручиваем страницу
print("[3] Прокручиваю страницу...")
for i in range(5):
    driver.execute_script("window.scrollBy(0, 500);")
    time.sleep(0.5)

time.sleep(2)

# Сохраняем
print("\n[4] Сохраняю данные для анализа...")

driver.save_screenshot("page_screenshot.png")
print("  - page_screenshot.png")

with open("page_source.html", "w", encoding="utf-8") as f:
    f.write(driver.page_source)
print("  - page_source.html")

# Анализируем структуру
print("\n[5] Анализ структуры страницы...")

print("\n--- Все классы с 'product' или 'card' ---")
elements = driver.find_elements(By.CSS_SELECTOR, "*")
classes_found = set()

for el in elements[:500]:
    try:
        class_attr = el.get_attribute("class") or ""
        if "product" in class_attr.lower() or "card" in class_attr.lower():
            classes_found.add(class_attr[:80])
    except:
        pass

for cls in list(classes_found)[:20]:
    print(f"  {cls}")

print("\n--- Ссылки на /product/ ---")
product_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/product/']")
print(f"  Найдено: {len(product_links)} ссылок")

if product_links:
    print("\n  Первые 5:")
    for link in product_links[:5]:
        href = link.get_attribute("href")
        text = link.text.replace('\n', ' ')[:60] if link.text else "[пусто]"
        print(f"    {href}")
        print(f"      текст: {text}")

print("\n--- Элементы с ценами (₽) ---")
all_text = driver.find_element(By.TAG_NAME, "body").text
prices = re.findall(r'(\d+(?:[,\.]\d+)?)\s*₽', all_text)
print(f"  Найдено цен: {len(prices)}")
if prices:
    print(f"  Примеры: {prices[:10]}")

print("\n--- Попытка найти карточки товаров ---")
selectors_to_try = [
    "[class*='ProductCard']",
    "[class*='productCard']",
    "[class*='product-card']",
    "[class*='CardProduct']",
    "[class*='goods']",
    "[class*='Goods']",
    "[class*='Item']",
    "[data-testid*='product']",
    "article",
    "[role='listitem']",
    "li[class*='product']",
    "div[class*='product']",
]

for sel in selectors_to_try:
    try:
        els = driver.find_elements(By.CSS_SELECTOR, sel)
        if els:
            print(f"\n  {sel}: {len(els)} элементов")
            if els[0].text:
                sample = els[0].text.replace('\n', ' | ')[:100]
                print(f"    Пример: {sample}")
    except:
        pass

driver.quit()
print("\n[OK] Анализ завершён!")
print("Откройте page_screenshot.png и page_source.html для детального анализа")



