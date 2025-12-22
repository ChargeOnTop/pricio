# -*- coding: utf-8 -*-
"""
Скрапер Пятёрочка v3 - прокрутка до конца (как у Магнита)
"""

import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

import json
import time
import csv
import re
import sqlite3
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class Scraper5ka:
    def __init__(self):
        self.driver = None
        self.all_products = []
        self.categories = []
        self.seen_product_ids = set()
    
    def start(self):
        """Запуск браузера"""
        print("[*] Запуск браузера...")
        
        options = Options()
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        print("[OK] Браузер запущен")
    
    def stop(self):
        """Остановка браузера"""
        if self.driver:
            self.driver.quit()
            print("[OK] Браузер закрыт")
    
    def check_captcha(self):
        """Проверка и обработка капчи"""
        if "Разверните картинку" in self.driver.page_source or "captcha" in self.driver.page_source.lower():
            print("\n    [!] Обнаружена капча! Пройдите её в браузере...")
            input("    >>> Нажмите ENTER после прохождения... ")
            time.sleep(2)
            return True
        return False
    
    def wait_for_catalog(self):
        """Ожидание загрузки каталога"""
        print("\n[*] Загрузка каталога...")
        self.driver.get("https://5ka.ru/catalog/")
        
        print("\n>>> Если появилась капча - пройдите её в браузере")
        input(">>> Нажмите ENTER когда каталог загрузится... ")
        
        return True
    
    def get_categories(self):
        """Получение списка категорий"""
        print("\n[*] Получение категорий...")
        
        try:
            script = self.driver.find_element(By.ID, "__NEXT_DATA__")
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
                    self.categories.append({
                        "id": cat_id,
                        "name": cat_name
                    })
            
            print(f"[OK] Найдено {len(self.categories)} категорий")
            return self.categories
            
        except Exception as e:
            print(f"[!] Ошибка: {e}")
            return []
    
    def scroll_to_load_all(self, max_scrolls: int = 200, scroll_pause: float = 0.8):
        """
        Прокручиваем страницу вниз пока появляются новые товары.
        Возвращает количество прокруток.
        """
        scroll_count = 0
        no_change_count = 0
        last_product_count = 0
        
        while scroll_count < max_scrolls and no_change_count < 5:
            # Прокручиваем вниз
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(scroll_pause)
            
            # Считаем текущее количество товаров на странице
            current_count = self.driver.execute_script('''
                var items = document.querySelectorAll('div[itemprop="itemListElement"], a[href*="/product/"]');
                return items.length;
            ''')
            
            if current_count == last_product_count:
                no_change_count += 1
            else:
                no_change_count = 0
                last_product_count = current_count
            
            scroll_count += 1
            
            # Каждые 10 прокруток проверяем капчу
            if scroll_count % 10 == 0:
                if self.check_captcha():
                    no_change_count = 0
        
        return scroll_count
    
    def scrape_category(self, category):
        """Скрапинг всех товаров из категории через прокрутку"""
        cat_id = category["id"]
        cat_name = category["name"]
        
        # Переходим на категорию
        url = f"https://5ka.ru/catalog/{cat_id}/"
        self.driver.get(url)
        time.sleep(3)
        
        # Проверяем капчу
        self.check_captcha()
        
        # Ждём загрузки товаров
        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'div[itemtype="https://schema.org/ItemList"], a[href*="/product/"]'))
            )
        except:
            print("    [!] Товары не найдены, пропускаем категорию")
            return []
        
        # Прокручиваем страницу до загрузки всех товаров
        print("    Прокрутка...", end=" ", flush=True)
        scrolls = self.scroll_to_load_all(max_scrolls=200, scroll_pause=0.6)
        print(f"({scrolls} раз)")
        
        # Небольшая пауза для догрузки
        time.sleep(1)
        
        # Извлекаем товары
        print("    Извлечение товаров...", end=" ", flush=True)
        products = self._extract_products_js(cat_name)
        print(f"найдено {len(products)}")
        
        return products
    
    def _extract_products_js(self, category_name):
        """Извлечение товаров через JavaScript"""
        try:
            products_data = self.driver.execute_script('''
                var products = [];
                var seenIds = new Set();
                
                // Способ 1: через schema.org ItemList
                var items = document.querySelectorAll('div[itemprop="itemListElement"]');
                
                items.forEach(function(item) {
                    try {
                        var product = {};
                        var html = item.outerHTML || '';
                        
                        // Ссылка и ID
                        var link = item.querySelector('a[href*="/product/"]');
                        if (link) {
                            product.url = link.href || '';
                            var match = product.url.match(/--(\d+)\/?$/);
                            if (match) {
                                product.id = match[1];
                            }
                        }
                        
                        if (!product.id || seenIds.has(product.id)) return;
                        seenIds.add(product.id);
                        
                        // Название
                        var nameMeta = item.querySelector('meta[itemprop="name"]');
                        if (nameMeta) {
                            product.name = nameMeta.getAttribute('content') || '';
                        }
                        if (!product.name && link) {
                            product.name = link.title || link.textContent.trim() || '';
                        }
                        
                        // Цена - ищем в блоке offers
                        var offersPos = html.indexOf('itemprop="offers"');
                        if (offersPos > 0) {
                            var afterOffers = html.substring(offersPos);
                            var priceMatches = afterOffers.match(/itemprop="price"[^>]*content="([\d.]+)"/g) || [];
                            var prices = [];
                            priceMatches.forEach(function(m) {
                                var p = m.match(/content="([\d.]+)"/);
                                if (p) prices.push(parseFloat(p[1]));
                            });
                            
                            if (prices.length > 0) {
                                product.price = Math.min.apply(null, prices);
                                product.old_price = Math.max.apply(null, prices);
                            }
                        }
                        
                        // Fallback для цены
                        if (!product.price) {
                            var allPrices = html.match(/itemprop="price"[^>]*content="([\d.]+)"/g) || [];
                            var validPrices = [];
                            allPrices.forEach(function(m) {
                                var p = m.match(/content="([\d.]+)"/);
                                if (p && parseFloat(p[1]) > 10) validPrices.push(parseFloat(p[1]));
                            });
                            if (validPrices.length > 0) {
                                product.price = Math.min.apply(null, validPrices);
                                product.old_price = Math.max.apply(null, validPrices);
                            }
                        }
                        
                        if (product.id && product.name) {
                            products.push(product);
                        }
                    } catch(e) {}
                });
                
                // Способ 2: если ItemList пустой, ищем через ссылки на товары
                if (products.length === 0) {
                    var links = document.querySelectorAll('a[href*="/product/"]');
                    
                    links.forEach(function(link) {
                        try {
                            var href = link.href || '';
                            var match = href.match(/--(\d+)\/?$/);
                            if (!match) return;
                            
                            var productId = match[1];
                            if (seenIds.has(productId)) return;
                            seenIds.add(productId);
                            
                            // Поднимаемся к карточке товара
                            var card = link;
                            for (var i = 0; i < 7; i++) {
                                if (card.parentElement) {
                                    var parent = card.parentElement;
                                    if (parent.textContent && parent.textContent.includes('₽')) {
                                        card = parent;
                                        break;
                                    }
                                    if (parent.textContent && parent.textContent.length > card.textContent.length) {
                                        card = parent;
                                    }
                                }
                            }
                            
                            var cardHtml = card.outerHTML || '';
                            var product = {
                                id: productId,
                                url: href,
                                name: '',
                                price: 0,
                                old_price: 0
                            };
                            
                            // Название
                            var nameMeta = card.querySelector('meta[itemprop="name"]');
                            if (nameMeta) {
                                product.name = nameMeta.getAttribute('content') || '';
                            }
                            if (!product.name) {
                                product.name = link.title || '';
                            }
                            if (!product.name) {
                                var text = card.textContent || '';
                                var lines = text.split('\\n');
                                for (var j = 0; j < lines.length; j++) {
                                    var line = lines[j].trim();
                                    if (line.length > 15 && !line.includes('₽') && /[а-яА-Я]{3,}/.test(line)) {
                                        var skip = ['в корзину', 'добавить', 'подробнее'];
                                        var shouldSkip = false;
                                        for (var k = 0; k < skip.length; k++) {
                                            if (line.toLowerCase().includes(skip[k])) {
                                                shouldSkip = true;
                                                break;
                                            }
                                        }
                                        if (!shouldSkip) {
                                            product.name = line;
                                            break;
                                        }
                                    }
                                }
                            }
                            
                            // Цена из HTML
                            var priceMatches = cardHtml.match(/content="([\d.]+)"/g) || [];
                            var prices = [];
                            priceMatches.forEach(function(m) {
                                var p = m.match(/"([\d.]+)"/);
                                if (p) {
                                    var val = parseFloat(p[1]);
                                    if (val > 1 && val < 100000) prices.push(val);
                                }
                            });
                            
                            if (prices.length > 0) {
                                product.price = Math.min.apply(null, prices);
                                product.old_price = Math.max.apply(null, prices);
                            }
                            
                            if (product.name) {
                                products.push(product);
                            }
                        } catch(e) {}
                    });
                }
                
                return products;
            ''')
            
            # Добавляем категорию
            for p in products_data:
                p['category'] = category_name
            
            return products_data
            
        except Exception as e:
            print(f"    [!] Ошибка JS извлечения: {e}")
            return []
    
    def save_results(self):
        """Сохранение результатов в БД и файлы"""
        if not self.all_products:
            print("[!] Нет данных для сохранения")
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        scraped_at = datetime.now().isoformat()
        
        # Сохраняем в SQLite
        self._save_to_database(scraped_at)
        
        # JSON
        json_file = f"products_5ka_{timestamp}.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump({
                "metadata": {
                    "source": "5ka.ru",
                    "scraped_at": scraped_at,
                    "total": len(self.all_products)
                },
                "products": self.all_products
            }, f, ensure_ascii=False, indent=2)
        print(f"[OK] {json_file}")
    
    def _save_to_database(self, scraped_at):
        """Сохранение в SQLite с поддержкой истории цен"""
        conn = sqlite3.connect('products.db')
        cursor = conn.cursor()
        
        # Создаём таблицы если не существуют
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                category TEXT,
                current_price REAL DEFAULT 0,
                min_price REAL DEFAULT 0,
                max_price REAL DEFAULT 0,
                first_seen TIMESTAMP,
                last_updated TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT NOT NULL,
                price REAL NOT NULL,
                old_price REAL,
                recorded_at TIMESTAMP
            )
        ''')
        
        new_count = 0
        updated_count = 0
        price_changed_count = 0
        
        for product in self.all_products:
            product_id = product.get('id', '')
            if not product_id:
                continue
            
            name = product.get('name', '')
            price = product.get('price', 0)
            old_price = product.get('old_price', 0)
            category = product.get('category', '')
            
            # Проверяем существует ли товар
            cursor.execute('SELECT current_price, min_price, max_price FROM products WHERE product_id = ?', (product_id,))
            existing = cursor.fetchone()
            
            if existing:
                # Товар существует - обновляем
                old_db_price, min_price, max_price = existing
                
                # Обновляем min/max цены
                new_min = min(min_price, price) if min_price > 0 else price
                new_max = max(max_price, price)
                
                cursor.execute('''
                    UPDATE products 
                    SET name = ?, category = ?, current_price = ?, 
                        min_price = ?, max_price = ?, last_updated = ?
                    WHERE product_id = ?
                ''', (name, category, price, new_min, new_max, scraped_at, product_id))
                
                updated_count += 1
                
                # Если цена изменилась - записываем в историю
                if abs(old_db_price - price) > 0.01:
                    cursor.execute('''
                        INSERT INTO price_history (product_id, price, old_price, recorded_at)
                        VALUES (?, ?, ?, ?)
                    ''', (product_id, price, old_price, scraped_at))
                    price_changed_count += 1
            else:
                # Новый товар
                cursor.execute('''
                    INSERT INTO products (product_id, name, category, current_price, min_price, max_price, first_seen, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (product_id, name, category, price, price, price, scraped_at, scraped_at))
                
                # Первая запись в историю цен
                cursor.execute('''
                    INSERT INTO price_history (product_id, price, old_price, recorded_at)
                    VALUES (?, ?, ?, ?)
                ''', (product_id, price, old_price, scraped_at))
                
                new_count += 1
        
        conn.commit()
        conn.close()
        
        print(f"[OK] Сохранено в products.db:")
        print(f"     Новых товаров: {new_count}")
        print(f"     Обновлено: {updated_count}")
        print(f"     Цена изменилась: {price_changed_count}")


def main(demo_mode: bool = False):
    """
    Основная функция скрапера.
    
    Args:
        demo_mode: если True - обрабатывает только первую категорию
    """
    print("="*60)
    if demo_mode:
        print("  СКРАПЕР ПЯТЁРОЧКА v3 - ДЕМО (только 1 категория)")
    else:
        print("  СКРАПЕР ПЯТЁРОЧКА v3 - ВСЕ КАТЕГОРИИ")
    print("="*60)
    
    scraper = Scraper5ka()
    
    try:
        scraper.start()
        scraper.wait_for_catalog()
        
        categories = scraper.get_categories()
        if not categories:
            print("[!] Категории не найдены")
            return
        
        # В демо-режиме берём только первую категорию
        if demo_mode:
            categories = categories[:1]
            print(f"\n[ДЕМО] Обрабатываем только: {categories[0]['name']}")
        
        total_categories = len(categories)
        print(f"\n[*] Категорий к обработке: {total_categories}")
        print("-"*60)
        
        for i, category in enumerate(categories, 1):
            print(f"\n[{i}/{total_categories}] {category['name']}...")
            
            products = scraper.scrape_category(category)
            
            # Фильтруем дубликаты
            new_products = 0
            for product in products:
                product_id = product.get('id', '')
                if product_id and product_id not in scraper.seen_product_ids:
                    scraper.seen_product_ids.add(product_id)
                    scraper.all_products.append(product)
                    new_products += 1
            
            print(f"    Найдено: {len(products)} | Новых: {new_products} | Всего: {len(scraper.all_products)}")
            
            if not demo_mode:
                time.sleep(1)
        
        print("\n" + "="*60)
        print(f"[OK] Всего уникальных товаров: {len(scraper.all_products)}")
        print("="*60)
        
        # Показываем примеры
        if scraper.all_products:
            print("\nПримеры:")
            for p in scraper.all_products[:5]:
                name = p.get('name', '')[:50]
                price = p.get('price', 0)
                print(f"  - {name}... {price} руб.")
        
        # Сохраняем
        print("\n[*] Сохранение в базу данных...")
        scraper.save_results()
        
    finally:
        scraper.stop()
    
    print("\n[OK] Готово!")


if __name__ == "__main__":
    # Полный режим - все категории
    main(demo_mode=False)
