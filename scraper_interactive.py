# -*- coding: utf-8 -*-
"""
Интерактивный скраппер для 5ka.ru
Позволяет вручную пройти капчу, затем автоматически собирает товары
"""

import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

import json
import time
import csv
import re
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def main():
    print("="*60)
    print("  ИНТЕРАКТИВНЫЙ СКРАППЕР ПЯТЁРОЧКА")
    print("="*60)
    
    # Запускаем браузер в видимом режиме
    print("\n[1] Запуск браузера...")
    
    options = Options()
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    print("[OK] Браузер запущен")
    
    # Открываем сайт
    print("\n[2] Открываю 5ka.ru...")
    driver.get("https://5ka.ru/catalog/")
    
    print("\n" + "="*60)
    print("  ВНИМАНИЕ!")
    print("="*60)
    print("""
    Если появилась капча с котиком:
    1. Найдите окно браузера Chrome
    2. Поверните картинку горизонтально (двигайте слайдер)
    3. Дождитесь загрузки каталога
    
    Если нужно выбрать адрес доставки:
    1. Кликните на 'Уточните адрес доставки'
    2. Введите любой адрес в Москве
    3. Выберите из подсказок
    """)
    print("="*60)
    
    input("\n>>> Нажмите ENTER когда каталог загрузится... ")
    
    # Проверяем что каталог загружен
    print("\n[3] Проверка загрузки каталога...")
    
    try:
        # Ждём появления категорий
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/catalog/']"))
        )
        print("[OK] Каталог загружен!")
    except:
        print("[!] Каталог не загружен. Попробуйте ещё раз.")
        input(">>> Нажмите ENTER когда будете готовы... ")
    
    # Извлекаем категории
    print("\n[4] Извлечение категорий...")
    
    categories = []
    try:
        # Парсим __NEXT_DATA__
        script = driver.find_element(By.ID, "__NEXT_DATA__")
        data = json.loads(script.get_attribute("innerHTML"))
        
        props = data.get("props", {}).get("pageProps", {}).get("props", {})
        catalog_store = props.get("catalogStore", "{}")
        
        if isinstance(catalog_store, str):
            catalog_store = json.loads(catalog_store)
        
        sections = catalog_store.get("_sections", [])
        
        for section in sections:
            cat_id = section.get("id", "")
            cat_name = section.get("name", "")
            if cat_id and cat_name:
                categories.append({
                    "id": cat_id,
                    "name": cat_name,
                    "url": f"/catalog/{cat_id}/"
                })
        
        print(f"[OK] Найдено {len(categories)} категорий")
        
    except Exception as e:
        print(f"[!] Ошибка: {e}")
    
    if not categories:
        print("[!] Категории не найдены")
        driver.quit()
        return
    
    # Выбираем категории для скрапинга
    print("\nКатегории:")
    for i, cat in enumerate(categories[:15], 1):
        print(f"  {i}. {cat['name']}")
    
    print(f"\nВсего: {len(categories)} категорий")
    
    try:
        num = int(input("\nСколько категорий скрапить (1-19)? [5]: ").strip() or "5")
        num = min(num, len(categories))
    except:
        num = 5
    
    # Скрапим товары
    print(f"\n[5] Скрапинг товаров из {num} категорий...")
    
    all_products = []
    
    for i, category in enumerate(categories[:num], 1):
        cat_name = category['name']
        cat_url = f"https://5ka.ru{category['url']}"
        
        print(f"\n  [{i}/{num}] {cat_name}...")
        
        driver.get(cat_url)
        time.sleep(3)
        
        # Проверяем капчу
        if "Разверните картинку" in driver.page_source:
            print("    [!] Появилась капча!")
            input("    >>> Пройдите капчу и нажмите ENTER... ")
            time.sleep(2)
        
        # Ждём загрузки товаров
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/product/']"))
            )
        except:
            print("    [!] Товары не загрузились")
            continue
        
        # Прокручиваем страницу для подгрузки товаров
        for _ in range(3):
            driver.execute_script("window.scrollBy(0, 1000);")
            time.sleep(1)
        
        # Извлекаем товары
        products = extract_products_from_page(driver, cat_name)
        all_products.extend(products)
        
        print(f"    Найдено: {len(products)} товаров")
        
        time.sleep(2)
    
    # Сохраняем результаты
    print(f"\n[6] Сохранение результатов...")
    print(f"    Всего собрано: {len(all_products)} товаров")
    
    if all_products:
        # JSON
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_file = f"products_5ka_{timestamp}.json"
        
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump({
                "metadata": {
                    "source": "5ka.ru",
                    "scraped_at": datetime.now().isoformat(),
                    "total_products": len(all_products)
                },
                "products": all_products
            }, f, ensure_ascii=False, indent=2)
        
        print(f"    [OK] Сохранено в {json_file}")
        
        # CSV
        csv_file = f"products_5ka_{timestamp}.csv"
        with open(csv_file, "w", encoding="utf-8-sig", newline="") as f:
            if all_products:
                writer = csv.DictWriter(f, fieldnames=all_products[0].keys())
                writer.writeheader()
                writer.writerows(all_products)
        
        print(f"    [OK] Сохранено в {csv_file}")
        
        # Показываем примеры
        print("\nПримеры товаров:")
        for p in all_products[:5]:
            print(f"  - {p['name'][:50]} ... {p['price']} руб.")
    
    driver.quit()
    print("\n[OK] Готово!")


def extract_products_from_page(driver, category_name):
    """Извлекает товары со страницы"""
    products = []
    seen = set()
    
    # Находим все ссылки на товары
    links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/product/']")
    
    for link in links:
        try:
            href = link.get_attribute("href") or ""
            
            # Извлекаем ID товара
            match = re.search(r'/product/(\d+)', href)
            if not match:
                continue
            
            product_id = match.group(1)
            if product_id in seen:
                continue
            seen.add(product_id)
            
            # Получаем текст карточки
            # Поднимаемся к родительскому контейнеру
            card = link
            for _ in range(5):
                parent = card.find_element(By.XPATH, "..")
                if parent.text and len(parent.text) > len(card.text):
                    card = parent
                else:
                    break
            
            card_text = card.text.strip()
            if not card_text:
                continue
            
            # Парсим название и цену
            lines = card_text.split('\n')
            name = ""
            price = 0
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Ищем цену
                price_match = re.search(r'(\d+(?:[,\.]\d+)?)\s*₽', line)
                if price_match:
                    price = float(price_match.group(1).replace(',', '.'))
                    continue
                
                # Название - самая информативная строка
                if len(line) > 5 and not line.isdigit():
                    if '₽' not in line and 'руб' not in line.lower():
                        if not name or len(line) > len(name):
                            # Фильтруем служебные строки
                            skip_words = ['корзин', 'добавить', 'купить', 'акция', 'скидка']
                            if not any(w in line.lower() for w in skip_words):
                                name = line
            
            if name and len(name) > 3:
                products.append({
                    "id": product_id,
                    "name": name[:100],
                    "price": price,
                    "category": category_name
                })
                
        except Exception:
            continue
    
    return products


if __name__ == "__main__":
    main()



