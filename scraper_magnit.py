# -*- coding: utf-8 -*-
"""
Скрапер для сайта Магнит (magnit.ru)
Проходит по всем категориям и загружает ВСЕ товары
"""

import json
import time
import re
import sqlite3
from datetime import datetime
from typing import List, Dict

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class MagnitScraper:
    """Скрапер для сайта Магнит"""
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.driver = None
        self.base_url = "https://magnit.ru"
        self.all_products = []
        self.seen_product_ids = set()
    
    def start(self):
        """Запуск браузера"""
        print("[*] Запуск браузера...")
        
        options = Options()
        if self.headless:
            options.add_argument("--headless=new")
        
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
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
    
    def close_popups(self):
        """Закрытие всплывающих окон"""
        try:
            cookie_btn = self.driver.find_element(By.XPATH, "//*[contains(text(), 'Хорошо, закрыть')]")
            cookie_btn.click()
            time.sleep(0.5)
        except:
            pass
        
        try:
            not_now = self.driver.find_element(By.XPATH, "//*[contains(text(), 'Не сейчас')]")
            not_now.click()
            time.sleep(0.5)
        except:
            pass
    
    def get_categories(self) -> List[Dict]:
        """Получение списка категорий"""
        print("[*] Загрузка каталога для получения категорий...")
        
        self.driver.get(f"{self.base_url}/catalog/")
        time.sleep(3)
        self.close_popups()
        
        categories = []
        
        try:
            links = self.driver.find_elements(By.CSS_SELECTOR, 'a[href*="/catalog/"]')
            
            seen_urls = set()
            for link in links:
                try:
                    href = link.get_attribute("href") or ""
                    text = link.text.strip()
                    
                    if not href or href.endswith('/catalog/') or href.endswith('/catalog') or not text:
                        continue
                    
                    if href.startswith(self.base_url):
                        href = href[len(self.base_url):]
                    
                    # Пропускаем промо-категории
                    if 'promokod' in href.lower():
                        continue
                    
                    if href not in seen_urls and len(text) > 2:
                        seen_urls.add(href)
                        categories.append({
                            "name": text[:50],
                            "url": href
                        })
                except:
                    continue
            
            print(f"[OK] Найдено {len(categories)} категорий")
            
        except Exception as e:
            print(f"[!] Ошибка получения категорий: {e}")
        
        return categories
    
    def load_all_products_in_category(self, max_clicks: int = 100):
        """Загрузка всех товаров в категории кликая 'Показать ещё'"""
        
        # Ждём загрузки товаров
        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'article[data-test-id="v-product-preview"]'))
            )
        except:
            return 0
        
        clicks = 0
        fails = 0
        
        while clicks < max_clicks and fails < 3:
            try:
                # Прокручиваем вниз
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(0.8)
                
                # Ищем и кликаем кнопку через JavaScript
                clicked = self.driver.execute_script('''
                    var btn = document.querySelector('button[data-test-id="v-pagination-show-more-button"]');
                    if (btn && btn.offsetParent !== null) {
                        btn.scrollIntoView({behavior: 'instant', block: 'center'});
                        btn.click();
                        return true;
                    }
                    return false;
                ''')
                
                if clicked:
                    clicks += 1
                    fails = 0
                    time.sleep(1.2)
                else:
                    fails += 1
                    time.sleep(0.5)
                    
            except:
                fails += 1
                time.sleep(0.5)
        
        return clicks
    
    def scrape_category(self, category: Dict) -> List[Dict]:
        """Скрапинг всех товаров из категории"""
        products = []
        url = f"{self.base_url}{category['url']}"
        category_name = category['name']
        
        self.driver.get(url)
        time.sleep(2)
        self.close_popups()
        
        # Загружаем все товары
        clicks = self.load_all_products_in_category(max_clicks=100)
        
        if clicks > 0:
            print(f"    [+] Нажато 'Показать ещё': {clicks} раз")
        
        # Извлекаем товары через JavaScript (быстрее)
        print(f"    [*] Извлекаю товары...")
        
        try:
            products_data = self.driver.execute_script('''
                var products = [];
                var articles = document.querySelectorAll('article[data-test-id="v-product-preview"]');
                
                articles.forEach(function(article) {
                    try {
                        var product = {};
                        
                        // Ссылка и ID
                        var link = article.querySelector('a[href*="/product/"]');
                        if (link) {
                            product.url = link.href || '';
                            product.name = link.title || '';
                            var match = product.url.match(/\\/product\\/(\\d+)/);
                            if (match) product.id = match[1];
                        }
                        
                        // Название (альт)
                        if (!product.name) {
                            var titleEl = article.querySelector('.unit-catalog-product-preview-title');
                            if (titleEl) product.name = titleEl.textContent.trim();
                        }
                        
                        // Цена
                        var priceEl = article.querySelector('.unit-catalog-product-preview-prices__regular');
                        if (priceEl) {
                            var priceText = priceEl.textContent.replace('₽', '').replace(/\\s/g, '').replace(',', '.');
                            product.price = parseFloat(priceText) || 0;
                        }
                        
                        // Старая цена
                        var oldPriceEl = article.querySelector('.unit-catalog-product-preview-prices__sale');
                        if (oldPriceEl) {
                            var oldPriceText = oldPriceEl.textContent.replace('₽', '').replace(/\\s/g, '').replace(',', '.');
                            product.old_price = parseFloat(oldPriceText) || product.price || 0;
                        } else {
                            product.old_price = product.price || 0;
                        }
                        
                        // Рейтинг
                        var ratingEl = article.querySelector('.unit-catalog-product-preview-rating-score');
                        if (ratingEl) product.rating = parseFloat(ratingEl.textContent) || 0;
                        
                        // Изображение
                        var img = article.querySelector('img');
                        if (img) product.image_url = img.src || '';
                        
                        if (product.id && product.name) {
                            products.push(product);
                        }
                    } catch(e) {}
                });
                
                return products;
            ''')
            
            # Добавляем категорию к каждому товару
            for p in products_data:
                p['category'] = category_name
                products.append(p)
                    
        except Exception as e:
            print(f"    [!] Ошибка: {e}")
        
        return products
    
    def _parse_product(self, article, category_name: str) -> Dict:
        """Парсинг данных товара"""
        product = {
            "id": "",
            "name": "",
            "price": 0,
            "old_price": 0,
            "discount": "",
            "rating": 0,
            "reviews": 0,
            "category": category_name,
            "url": "",
            "image_url": ""
        }
        
        try:
            # Ссылка и название
            try:
                link = article.find_element(By.CSS_SELECTOR, 'a[href*="/product/"]')
                href = link.get_attribute("href") or ""
                product["url"] = href
                product["name"] = link.get_attribute("title") or ""
                
                match = re.search(r'/product/(\d+)', href)
                if match:
                    product["id"] = match.group(1)
            except:
                pass
            
            if not product["name"]:
                try:
                    title_el = article.find_element(By.CSS_SELECTOR, '.unit-catalog-product-preview-title')
                    product["name"] = title_el.text.strip()
                except:
                    pass
            
            # Цена
            try:
                price_el = article.find_element(By.CSS_SELECTOR, '.unit-catalog-product-preview-prices__regular')
                price_text = price_el.text.replace('₽', '').replace(' ', '').replace(',', '.').strip()
                product["price"] = float(price_text)
            except:
                pass
            
            # Старая цена
            try:
                old_price_el = article.find_element(By.CSS_SELECTOR, '.unit-catalog-product-preview-prices__sale')
                old_price_text = old_price_el.text.replace('₽', '').replace(' ', '').replace(',', '.').strip()
                product["old_price"] = float(old_price_text)
            except:
                product["old_price"] = product["price"]
            
            # Скидка
            try:
                discount_el = article.find_element(By.CSS_SELECTOR, '[data-test-id="v-catalog-badge"]')
                product["discount"] = discount_el.text.strip()
            except:
                pass
            
            # Рейтинг
            try:
                rating_el = article.find_element(By.CSS_SELECTOR, '.unit-catalog-product-preview-rating-score')
                product["rating"] = float(rating_el.text.strip())
            except:
                pass
            
            # Отзывы
            try:
                reviews_el = article.find_element(By.CSS_SELECTOR, '.unit-catalog-product-preview-rating-comments')
                match = re.search(r'(\d+)', reviews_el.text)
                if match:
                    product["reviews"] = int(match.group(1))
            except:
                pass
            
            # Изображение
            try:
                img = article.find_element(By.CSS_SELECTOR, 'img')
                product["image_url"] = img.get_attribute("src") or ""
            except:
                pass
                
        except:
            pass
        
        return product
    
    def save_to_database(self):
        """Сохранение в базу данных"""
        if not self.all_products:
            print("[!] Нет данных для сохранения")
            return
        
        scraped_at = datetime.now().isoformat()
        
        conn = sqlite3.connect('products_magnit.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                category TEXT,
                current_price REAL DEFAULT 0,
                min_price REAL DEFAULT 0,
                max_price REAL DEFAULT 0,
                rating REAL DEFAULT 0,
                reviews INTEGER DEFAULT 0,
                image_url TEXT,
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
            rating = product.get('rating', 0)
            reviews = product.get('reviews', 0)
            image_url = product.get('image_url', '')
            
            cursor.execute('SELECT current_price, min_price, max_price FROM products WHERE product_id = ?', (product_id,))
            existing = cursor.fetchone()
            
            if existing:
                old_db_price, min_price, max_price = existing
                
                new_min = min(min_price, price) if min_price > 0 else price
                new_max = max(max_price, price)
                
                cursor.execute('''
                    UPDATE products 
                    SET name = ?, category = ?, current_price = ?, 
                        min_price = ?, max_price = ?, rating = ?, reviews = ?,
                        image_url = ?, last_updated = ?
                    WHERE product_id = ?
                ''', (name, category, price, new_min, new_max, rating, reviews, image_url, scraped_at, product_id))
                
                updated_count += 1
                
                if abs(old_db_price - price) > 0.01:
                    cursor.execute('''
                        INSERT INTO price_history (product_id, price, old_price, recorded_at)
                        VALUES (?, ?, ?, ?)
                    ''', (product_id, price, old_price, scraped_at))
                    price_changed_count += 1
            else:
                cursor.execute('''
                    INSERT INTO products (product_id, name, category, current_price, min_price, max_price, 
                                         rating, reviews, image_url, first_seen, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (product_id, name, category, price, price, price, rating, reviews, image_url, scraped_at, scraped_at))
                
                cursor.execute('''
                    INSERT INTO price_history (product_id, price, old_price, recorded_at)
                    VALUES (?, ?, ?, ?)
                ''', (product_id, price, old_price, scraped_at))
                
                new_count += 1
        
        conn.commit()
        conn.close()
        
        print(f"[OK] Сохранено в products_magnit.db:")
        print(f"     Новых товаров: {new_count}")
        print(f"     Обновлено: {updated_count}")
        print(f"     Цена изменилась: {price_changed_count}")
    
    def save_to_json(self):
        """Сохранение в JSON"""
        if not self.all_products:
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"products_magnit_{timestamp}.json"
        
        with open(filename, "w", encoding="utf-8") as f:
            json.dump({
                "metadata": {
                    "source": "magnit.ru",
                    "scraped_at": datetime.now().isoformat(),
                    "total": len(self.all_products)
                },
                "products": self.all_products
            }, f, ensure_ascii=False, indent=2)
        
        print(f"[OK] Сохранено: {filename}")


def main():
    print("="*60)
    print("  СКРАПЕР МАГНИТ - ВСЕ КАТЕГОРИИ + ВСЕ ТОВАРЫ")
    print("="*60)
    
    scraper = MagnitScraper(headless=False)  # Видимый режим
    
    try:
        scraper.start()
        
        # Получаем категории
        categories = scraper.get_categories()
        if not categories:
            print("[!] Категории не найдены")
            return
        
        total = len(categories)
        print(f"\n[*] Скрапинг {total} категорий (все товары в каждой)...")
        print("-"*60)
        
        for i, category in enumerate(categories, 1):
            print(f"\n[{i}/{total}] {category['name']}...")
            
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
            time.sleep(1)
        
        print("\n" + "="*60)
        print(f"[OK] Всего уникальных товаров: {len(scraper.all_products)}")
        print("="*60)
        
        if scraper.all_products:
            print("\nПримеры:")
            for p in scraper.all_products[:5]:
                print(f"  - {p['name'][:40]}... | {p['category'][:15]} | {p['price']} руб.")
            
            print("\n[*] Сохранение...")
            scraper.save_to_database()
            scraper.save_to_json()
        
    finally:
        scraper.stop()
    
    print("\n[OK] Готово!")


if __name__ == "__main__":
    main()
