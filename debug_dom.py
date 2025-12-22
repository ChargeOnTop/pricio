# -*- coding: utf-8 -*-
import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time

options = Options()
options.add_argument('--window-size=1920,1080')

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)

driver.get('https://5ka.ru/')
time.sleep(3)
driver.get('https://5ka.ru/catalog/251C12884/')
time.sleep(5)

# Сохраняем скриншот
driver.save_screenshot('debug_category_detail.png')
print('Скриншот сохранён')

# Сохраняем HTML
with open('debug_category.html', 'w', encoding='utf-8') as f:
    f.write(driver.page_source)
print('HTML сохранён в debug_category.html')

# Смотрим какие элементы есть
print('\nИщем карточки товаров...')
selectors = [
    "[class*='ProductCard']",
    "[class*='product-card']",
    "[data-qa*='product']",
    "a[href*='/product/']",
    "[class*='Card']",
    "[class*='card']",
    "[class*='Item']",
    "[class*='item']",
]

for sel in selectors:
    try:
        els = driver.find_elements(By.CSS_SELECTOR, sel)
        if els:
            print(f'{sel}: найдено {len(els)} элементов')
            if len(els) > 0 and els[0].text:
                text = els[0].text.replace('\n', ' | ')[:150]
                print(f'  Первый текст: {text}')
    except Exception as e:
        print(f'{sel}: ошибка')

# Ищем все ссылки на товары
print('\nВсе ссылки на /product/:')
links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/product/']")
for link in links[:5]:
    href = link.get_attribute('href')
    text = link.text.replace('\n', ' ')[:50] if link.text else '[no text]'
    print(f'  {href} -> {text}')

driver.quit()



