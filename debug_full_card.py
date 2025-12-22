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
import re

options = Options()
options.add_argument('--window-size=1920,1080')

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)

driver.get("https://5ka.ru/catalog/")
print(">>> Пройдите капчу и нажмите ENTER...")
input()

# Овощи/фрукты
driver.get("https://5ka.ru/catalog/251C12886/?page=41")
time.sleep(4)

for _ in range(20):
    driver.execute_script("window.scrollBy(0, 500);")
    time.sleep(0.2)
time.sleep(2)

# Ищем карточку винограда по ID
try:
    card = driver.find_element(By.CSS_SELECTOR, '[data-qa="product-card-4327381"]')
    html = card.get_attribute("outerHTML")
    
    with open('grape_card.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print("Карточка сохранена в grape_card.html")
    
    # Анализ
    print("\n--- Анализ ---")
    print(f"Длина HTML: {len(html)}")
    
    # Все content
    contents = re.findall(r'content="([\d.]+)"', html)
    print(f"Все content: {contents}")
    
    # itemprop="price"
    prices = re.findall(r'itemprop="price"[^>]*content="([\d.]+)"', html)
    print(f"itemprop=price: {prices}")
    
    # Ищем 449
    if "449" in html:
        idx = html.find("449")
        print(f"\n449 найдено на позиции {idx}")
        print(f"Контекст: ...{html[max(0,idx-50):idx+80]}...")
    else:
        print("\n449 НЕ найдено в карточке!")
        
    # Текст карточки
    print(f"\nТекст карточки:\n{card.text}")
    
except Exception as e:
    print(f"Ошибка: {e}")

driver.quit()



