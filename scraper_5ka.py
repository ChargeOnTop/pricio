# -*- coding: utf-8 -*-
"""
Веб-скраппер для сайта 5ka.ru (Пятёрочка)
Извлекает все продукты и их цены из каталога
Использует Selenium для обхода защиты от ботов

ИСПОЛЬЗОВАНИЕ:
    python scraper_5ka.py                           # Интерактивный режим
    python scraper_5ka.py --mode 1                  # Полный скраппинг
    python scraper_5ka.py --mode 2                  # Только акции (без Selenium)
    python scraper_5ka.py --proxy host:port         # С прокси
    python scraper_5ka.py --no-headless             # Показать браузер
    
ЕСЛИ САЙТ БЛОКИРУЕТ:
    Сайт 5ka.ru имеет защиту от ботов и может заблокировать IP при частых запросах.
    Решения:
    1. Подождите 1-2 часа и попробуйте снова
    2. Используйте VPN (например, Windscribe, ProtonVPN - бесплатные)
    3. Используйте прокси: python scraper_5ka.py --proxy ip:port
    4. Установите переменную окружения: set HTTP_PROXY=http://ip:port
"""

import json
import time
import csv
import sys
import re
from datetime import datetime
from typing import Optional, List, Dict

# Настройка кодировки для Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')


class Pyaterochka5kaScraper:
    """Скраппер для сайта Пятёрочка (5ka.ru) с использованием Selenium"""
    
    def __init__(self, headless: bool = True, proxy: str = None):
        """
        Инициализация скраппера
        
        Args:
            headless: Запускать браузер в фоновом режиме
            proxy: Прокси сервер в формате "host:port" или "http://host:port"
        """
        self.headless = headless
        self.proxy = proxy
        self.driver = None
        self.all_products = []
        self.categories = []
        self.max_retries = 3
        self.retry_delay = 30  # секунд между попытками
        
    def _init_driver(self):
        """Инициализирует Selenium WebDriver с обходом защиты"""
        try:
            # Пробуем undetected-chromedriver для обхода защиты от ботов
            import undetected_chromedriver as uc
            
            chrome_options = uc.ChromeOptions()
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            
            if self.headless:
                chrome_options.add_argument("--headless=new")
            
            # Добавляем прокси если указан
            if self.proxy:
                chrome_options.add_argument(f"--proxy-server={self.proxy}")
                print(f"[*] Используется прокси: {self.proxy}")
            
            self.driver = uc.Chrome(options=chrome_options, use_subprocess=True)
            print("[OK] WebDriver инициализирован (undetected-chromedriver)")
            
        except ImportError:
            # Fallback к обычному Selenium
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager
            
            chrome_options = Options()
            
            if self.headless:
                chrome_options.add_argument("--headless=new")
            
            # Добавляем прокси если указан
            if self.proxy:
                chrome_options.add_argument(f"--proxy-server={self.proxy}")
                print(f"[*] Используется прокси: {self.proxy}")
            
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option("useAutomationExtension", False)
            
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    })
                """
            })
            
            print("[OK] WebDriver инициализирован (selenium)")
    
    def _safe_get(self, url: str, max_retries: int = None) -> bool:
        """
        Безопасный переход по URL с повторными попытками
        
        Args:
            url: URL для загрузки
            max_retries: Максимальное количество попыток
            
        Returns:
            True если загрузка успешна
        """
        if max_retries is None:
            max_retries = self.max_retries
        
        for attempt in range(max_retries):
            try:
                self.driver.get(url)
                return True
            except Exception as e:
                error_msg = str(e)
                if "ERR_CONNECTION_TIMED_OUT" in error_msg or "timeout" in error_msg.lower():
                    print(f"\n    [!] Таймаут соединения (попытка {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        print(f"    [*] Ожидание {self.retry_delay} секунд...")
                        time.sleep(self.retry_delay)
                    else:
                        print("    [!] Сайт недоступен. Возможно IP заблокирован.")
                        print("    [*] Рекомендации:")
                        print("        - Подождите 1-2 часа и попробуйте снова")
                        print("        - Используйте VPN или прокси")
                        return False
                else:
                    raise
        return False
        
    def _close_driver(self):
        """Закрывает WebDriver"""
        if self.driver:
            self.driver.quit()
            self.driver = None
            
    def _extract_api_data(self) -> dict:
        """
        Извлекает данные из Next.js __NEXT_DATA__
        
        Returns:
            Данные страницы
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        
        try:
            # Ждём загрузки страницы
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.ID, "__NEXT_DATA__"))
            )
            script = self.driver.find_element(By.ID, "__NEXT_DATA__")
            data = json.loads(script.get_attribute("innerHTML"))
            return data
        except Exception as e:
            print(f"[!] __NEXT_DATA__ не найден, пробуем альтернативный метод...")
            return self._extract_from_page()
    
    def _parse_next_data_from_html(self) -> dict:
        """
        Парсит __NEXT_DATA__ напрямую из HTML страницы
        
        Returns:
            Данные из __NEXT_DATA__
        """
        try:
            html = self.driver.page_source
            
            # Ищем JSON в script теге __NEXT_DATA__
            start_marker = '<script id="__NEXT_DATA__" type="application/json">'
            end_marker = '</script>'
            
            start_idx = html.find(start_marker)
            if start_idx == -1:
                print("[!] Не найден тег __NEXT_DATA__")
                return {}
            
            start_idx += len(start_marker)
            end_idx = html.find(end_marker, start_idx)
            
            if end_idx == -1:
                print("[!] Не найден закрывающий тег")
                return {}
            
            json_str = html[start_idx:end_idx]
            data = json.loads(json_str)
            print(f"[OK] __NEXT_DATA__ успешно извлечён ({len(json_str)} bytes)")
            return data
            
        except json.JSONDecodeError as e:
            print(f"[!] Ошибка парсинга JSON: {e}")
            return {}
        except Exception as e:
            print(f"[!] Ошибка: {e}")
            return {}
    
    def _extract_from_page(self) -> dict:
        """
        Извлекает данные напрямую из DOM страницы
        
        Returns:
            Словарь с данными
        """
        from selenium.webdriver.common.by import By
        
        result = {"props": {"pageProps": {"catalogData": {"categories": []}}}}
        
        try:
            # Ищем ссылки на категории
            links = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='/catalog/']")
            categories = []
            seen = set()
            
            for link in links:
                href = link.get_attribute("href")
                text = link.text.strip()
                
                if href and text and '/catalog/' in href and text not in seen:
                    # Извлекаем ID из URL
                    match = re.search(r'/catalog/([^/]+)--([A-Z0-9]+)', href)
                    if match:
                        slug, cat_id = match.groups()
                        categories.append({
                            "id": cat_id,
                            "name": text,
                            "slug": slug
                        })
                        seen.add(text)
                    else:
                        match2 = re.search(r'/catalog/([A-Z0-9]+)', href)
                        if match2:
                            cat_id = match2.group(1)
                            if len(cat_id) > 3:  # Фильтруем короткие ID
                                categories.append({
                                    "id": cat_id,
                                    "name": text,
                                    "slug": text.lower().replace(' ', '-')
                                })
                                seen.add(text)
            
            result["props"]["pageProps"]["catalogData"]["categories"] = categories
            print(f"[*] Извлечено {len(categories)} категорий из DOM")
            
        except Exception as e:
            print(f"[!] Ошибка извлечения из DOM: {e}")
        
        return result
    
    def _set_location(self):
        """
        Устанавливает локацию/магазин для получения товаров
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        
        print("[*] Установка локации...")
        
        # Заходим на главную
        if not self._safe_get("https://5ka.ru/"):
            return
        time.sleep(3)
        
        try:
            # Ищем кнопку "Уточните адрес доставки" или похожую
            address_btn = None
            selectors = [
                "[class*='address']",
                "[class*='location']",
                "button[class*='delivery']",
                "[data-testid*='address']",
                "[class*='DeliveryAddress']",
            ]
            
            for selector in selectors:
                try:
                    address_btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if address_btn.is_displayed():
                        break
                except:
                    continue
            
            if address_btn:
                address_btn.click()
                time.sleep(2)
                
                # Ищем поле ввода адреса и вводим "Москва"
                try:
                    input_field = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text'], input[placeholder*='адрес'], input[placeholder*='улица']"))
                    )
                    input_field.clear()
                    input_field.send_keys("Москва, Тверская улица 1")
                    time.sleep(2)
                    
                    # Ищем и кликаем первую подсказку
                    suggestions = self.driver.find_elements(By.CSS_SELECTOR, "[class*='suggestion'], [class*='dropdown'] li, [class*='autocomplete'] div")
                    if suggestions:
                        suggestions[0].click()
                        time.sleep(2)
                    
                    # Ищем кнопку подтверждения
                    confirm_btns = self.driver.find_elements(By.CSS_SELECTOR, "button[type='submit'], [class*='confirm'], [class*='apply'], [class*='save']")
                    for btn in confirm_btns:
                        if btn.is_displayed():
                            btn.click()
                            break
                    
                    time.sleep(2)
                    print("[OK] Локация установлена")
                    
                except Exception as e:
                    print(f"[!] Не удалось ввести адрес: {e}")
            else:
                print("[*] Кнопка адреса не найдена, пробуем установить cookie...")
                
        except Exception as e:
            print(f"[!] Ошибка установки локации: {e}")
        
        # Альтернативный метод - установка cookies для Москвы
        try:
            # Устанавливаем cookies для store_id (типичный магазин в Москве)
            self.driver.add_cookie({
                "name": "STORE_ID",
                "value": "35XY",
                "domain": "5ka.ru",
                "path": "/"
            })
            self.driver.add_cookie({
                "name": "SELECTED_CITY",
                "value": "Москва",
                "domain": "5ka.ru",
                "path": "/"
            })
            self.driver.add_cookie({
                "name": "city_id",
                "value": "1",  # Москва
                "domain": "5ka.ru",
                "path": "/"
            })
            print("[*] Cookies для локации установлены")
        except Exception as e:
            print(f"[!] Ошибка установки cookies: {e}")
        
        # Перезагружаем страницу для применения cookies
        try:
            self.driver.refresh()
        except:
            pass
        time.sleep(3)
    
    def get_categories(self) -> List[Dict]:
        """
        Получает список категорий
        
        Returns:
            Список категорий
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        
        print("\n[1] Загрузка страницы каталога...")
        
        # Сначала устанавливаем локацию
        self._set_location()
        
        # Теперь переходим на каталог
        if not self._safe_get("https://5ka.ru/catalog/"):
            return []
        
        # Ждём загрузки элементов
        try:
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/catalog/']"))
            )
            print("[*] Элементы каталога найдены")
        except Exception as e:
            print(f"[!] Таймаут ожидания: {e}")
            # Сохраняем скриншот для диагностики
            self.driver.save_screenshot("debug_screenshot.png")
            print("[*] Скриншот сохранён в debug_screenshot.png")
        
        time.sleep(5)  # Дополнительное ожидание для динамического контента
        
        # Парсим __NEXT_DATA__ напрямую из HTML
        print("[*] Парсим __NEXT_DATA__...")
        data = self._parse_next_data_from_html()
        
        # Если не сработало, пробуем через DOM
        if not data or not data.get("props"):
            print("[*] Пробуем извлечь через DOM...")
            data = self._extract_api_data()
        
        if not data:
            print("[!] Не удалось получить данные страницы")
            return []
        
        # Навигация по структуре Next.js
        props = data.get("props", {})
        page_props = props.get("pageProps", {})
        
        # Проверяем вложенный props (специфика Next.js)
        if "props" in page_props:
            page_props = page_props.get("props", {})
        
        # Получаем catalogStore
        catalog_store = page_props.get("catalogStore", {})
        
        # Если catalogStore - строка (сериализованный JSON), парсим её
        if isinstance(catalog_store, str):
            try:
                catalog_store = json.loads(catalog_store)
                print(f"[DEBUG] catalogStore десериализован")
            except:
                print(f"[DEBUG] catalogStore - строка длиной {len(catalog_store)}")
                catalog_store = {}
        
        if isinstance(catalog_store, dict):
            print(f"[DEBUG] Ключи catalogStore: {list(catalog_store.keys())[:15]}")
        else:
            print(f"[DEBUG] catalogStore тип: {type(catalog_store)}")
        
        # Ищем категории в разных местах
        categories_data = []
        
        # Путь 1: catalogStore.categories
        if "categories" in catalog_store:
            categories_data = catalog_store.get("categories", [])
            print(f"[DEBUG] Найдено в categories: {len(categories_data)} элементов")
        
        # Путь 2: catalogStore.catalogData
        if not categories_data and "catalogData" in catalog_store:
            catalog_data = catalog_store.get("catalogData", {})
            if isinstance(catalog_data, dict):
                categories_data = catalog_data.get("categories", [])
                print(f"[DEBUG] Найдено в catalogData.categories: {len(categories_data)} элементов")
        
        # Путь 3: Поиск во всех ключах catalogStore
        if not categories_data:
            for key, val in catalog_store.items():
                if isinstance(val, list) and len(val) > 0:
                    first_item = val[0] if val else {}
                    if isinstance(first_item, dict) and ('id' in first_item or 'name' in first_item):
                        print(f"[DEBUG] Найдены данные в '{key}': {len(val)} элементов")
                        if len(val) > len(categories_data):
                            categories_data = val
        
        categories = []
        
        def extract_categories(items, parent_name=""):
            """Рекурсивно извлекает все категории"""
            for item in items:
                cat_id = item.get("id", "")
                cat_name = item.get("name", "")
                cat_slug = item.get("slug", "")
                
                categories.append({
                    "id": cat_id,
                    "name": cat_name,
                    "slug": cat_slug,
                    "full_path": f"{parent_name} > {cat_name}" if parent_name else cat_name,
                    "url": f"/catalog/{cat_slug}--{cat_id}/" if cat_slug else f"/catalog/{cat_id}/"
                })
                
                # Рекурсивно обрабатываем подкатегории
                children = item.get("children", [])
                if children:
                    extract_categories(children, cat_name)
        
        extract_categories(categories_data)
        
        self.categories = categories
        print(f"[OK] Найдено {len(categories)} категорий")
        
        # Пробуем извлечь товары прямо из главной страницы каталога
        self._extract_products_from_main_page(catalog_store)
        
        return categories
    
    def _extract_products_from_main_page(self, catalog_store: dict):
        """
        Извлекает товары из данных главной страницы каталога
        
        Args:
            catalog_store: Данные catalogStore
        """
        products_found = 0
        
        # Проверяем promotions - там могут быть товары в акции
        promotions = catalog_store.get("promotions", [])
        for promo in promotions:
            if isinstance(promo, dict):
                promo_products = promo.get("products", [])
                for prod in promo_products:
                    parsed = self._parse_product(prod, promo.get("name", "Акции"))
                    if parsed.get("id") and parsed.get("name"):
                        self.all_products.append(parsed)
                        products_found += 1
        
        # Проверяем products напрямую
        direct_products = catalog_store.get("products", [])
        for prod in direct_products:
            parsed = self._parse_product(prod, "Каталог")
            if parsed.get("id") and parsed.get("name"):
                self.all_products.append(parsed)
                products_found += 1
        
        # Проверяем productsList
        products_list = catalog_store.get("productsList", {})
        if isinstance(products_list, dict):
            list_products = products_list.get("products", [])
            for prod in list_products:
                parsed = self._parse_product(prod, "Каталог")
                if parsed.get("id") and parsed.get("name"):
                    self.all_products.append(parsed)
                    products_found += 1
        
        if products_found > 0:
            print(f"[*] Извлечено {products_found} товаров с главной страницы каталога")
    
    def get_products_from_category(self, category: dict, max_products: int = 100) -> List[Dict]:
        """
        Получает товары из категории
        
        Args:
            category: Данные категории
            max_products: Максимальное количество товаров
            
        Returns:
            Список товаров
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        
        cat_url = f"https://5ka.ru{category['url']}"
        print(f"\n    URL: {cat_url}")
        
        if not self._safe_get(cat_url, max_retries=2):
            return []
        time.sleep(3)
        
        # Проверяем наличие ошибки "Что-то пошло не так"
        page_text = self.driver.page_source
        if "Что-то пошло не так" in page_text or "Повторить" in page_text:
            print("    [!] Обнаружена ошибка страницы, пробуем перезагрузить...")
            # Кликаем кнопку "Повторить" если есть
            try:
                retry_btn = self.driver.find_element(By.XPATH, "//button[contains(text(), 'Повторить')]")
                retry_btn.click()
                time.sleep(3)
            except:
                # Или просто обновляем страницу
                try:
                    self.driver.refresh()
                except:
                    pass
                time.sleep(3)
        
        # Ждём появления карточек товаров
        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/product/'], [class*='product-card'], [class*='ProductCard']"))
            )
            print("    [*] Карточки товаров найдены")
        except:
            print("    [!] Карточки товаров не найдены")
        
        products = []
        
        # Парсим __NEXT_DATA__ напрямую из HTML
        data = self._parse_next_data_from_html()
        
        if data:
            # Навигация по структуре
            props = data.get("props", {})
            page_props = props.get("pageProps", {})
            
            if "props" in page_props:
                page_props = page_props.get("props", {})
            
            # Получаем catalogStore
            catalog_store = page_props.get("catalogStore", {})
            if isinstance(catalog_store, str):
                try:
                    catalog_store = json.loads(catalog_store)
                except:
                    catalog_store = {}
            
            # Ищем товары в разных местах
            products_data = []
            
            if isinstance(catalog_store, dict):
                # Путь 1: products
                products_data = catalog_store.get("products", [])
                
                # Путь 2: productsList
                if not products_data:
                    products_data = catalog_store.get("productsList", [])
                
                # Путь 3: specificCategory.products
                if not products_data:
                    specific = catalog_store.get("specificCategory", {})
                    if isinstance(specific, dict):
                        products_data = specific.get("products", [])
            
            for prod in products_data[:max_products]:
                parsed = self._parse_product(prod, category["name"])
                if parsed.get("id") and parsed.get("name"):
                    products.append(parsed)
        
        # Товары загружаются динамически - извлекаем из DOM
        if len(products) == 0:
            print("    [*] Извлекаем товары из DOM...")
            dom_products = self._extract_products_from_dom(category["name"], max_products)
            products.extend(dom_products)
        
        # Если ещё мало товаров - пробуем прокрутку для подгрузки
        if len(products) < max_products // 2:
            scroll_products = self._scroll_and_collect(category["name"], max_products - len(products))
            products.extend(scroll_products)
        
        return products
    
    def _extract_products_from_dom(self, category_name: str, max_items: int) -> List[Dict]:
        """
        Извлекает товары напрямую из DOM страницы
        
        Args:
            category_name: Название категории
            max_items: Максимальное количество товаров
            
        Returns:
            Список товаров
        """
        from selenium.webdriver.common.by import By
        
        products = []
        seen_names = set()
        
        try:
            # Ищем все карточки товаров по разным селекторам
            selectors = [
                "[class*='ProductCard']",
                "[class*='product-card']",
                "[data-qa*='product']",
                "a[href*='/product/']",
            ]
            
            cards = []
            for selector in selectors:
                try:
                    found = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if found:
                        cards = found
                        break
                except:
                    continue
            
            if not cards:
                return products
            
            for card in cards[:max_items * 2]:  # Берём с запасом
                if len(products) >= max_items:
                    break
                
                try:
                    card_text = card.text.strip()
                    if not card_text:
                        continue
                    
                    lines = card_text.split('\n')
                    
                    # Парсим данные из текста карточки
                    name = ""
                    prices = []
                    
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                        
                        # Ищем цены (формат: 123.45 ₽ или 123,45 или просто числа)
                        import re
                        price_matches = re.findall(r'(\d+(?:[.,]\d+)?)\s*[₽руб]?', line)
                        for pm in price_matches:
                            try:
                                price = float(pm.replace(',', '.'))
                                if 1 < price < 100000:  # Разумный диапазон цен
                                    prices.append(price)
                            except:
                                pass
                        
                        # Название - строка без цен, достаточно длинная
                        if not re.search(r'^\d+[.,]?\d*\s*[₽руб]?$', line) and len(line) > 3:
                            if not name or (len(line) > len(name) and '₽' not in line and 'руб' not in line.lower()):
                                # Проверяем что это не служебный текст
                                if not any(skip in line.lower() for skip in ['в корзину', 'добавить', 'акция', 'скидка', 'кг', 'шт', 'л', 'мл', 'г']):
                                    name = line
                    
                    # Если название не найдено в тексте, берём первую длинную строку
                    if not name:
                        for line in lines:
                            if len(line) > 5 and '₽' not in line:
                                name = line
                                break
                    
                    if name and name not in seen_names:
                        seen_names.add(name)
                        
                        # Определяем цены
                        regular_price = max(prices) if prices else 0
                        discount_price = min(prices) if prices else regular_price
                        
                        # Получаем ID из ссылки
                        product_id = ""
                        try:
                            link = card.find_element(By.CSS_SELECTOR, "a[href*='/product/']")
                            href = link.get_attribute("href") or ""
                            match = re.search(r'/product/(\d+)', href)
                            if match:
                                product_id = match.group(1)
                        except:
                            product_id = str(hash(name))[:8]
                        
                        products.append({
                            "id": product_id,
                            "name": name[:100],
                            "regular_price": regular_price,
                            "discount_price": discount_price,
                            "category_name": category_name
                        })
                        
                except Exception as e:
                    continue
            
        except Exception as e:
            print(f"    [!] Ошибка извлечения из DOM: {e}")
        
        return products
    
    def _scroll_and_collect(self, category_name: str, max_items: int) -> List[Dict]:
        """
        Прокручивает страницу и собирает товары из DOM
        
        Args:
            category_name: Название категории
            max_items: Максимальное количество товаров
            
        Returns:
            Список товаров
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        
        products = []
        seen_ids = set()
        
        # Ждём появления карточек товаров
        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/product/']"))
            )
        except:
            pass
        
        time.sleep(2)
        
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        scroll_count = 0
        max_scrolls = 3
        
        while scroll_count < max_scrolls and len(products) < max_items:
            # Собираем товары через ссылки на продукты
            try:
                # Находим все ссылки на товары
                product_links = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='/product/']")
                
                for link in product_links:
                    if len(products) >= max_items:
                        break
                        
                    try:
                        href = link.get_attribute("href")
                        
                        # Извлекаем ID из URL
                        match = re.search(r'/product/(\d+)', href)
                        if not match:
                            continue
                            
                        product_id = match.group(1)
                        
                        if product_id in seen_ids:
                            continue
                        seen_ids.add(product_id)
                        
                        # Получаем родительский контейнер карточки
                        card = link
                        for _ in range(5):  # Поднимаемся на 5 уровней
                            parent = card.find_element(By.XPATH, "..")
                            if parent:
                                card = parent
                            else:
                                break
                        
                        # Извлекаем текст карточки
                        card_text = card.text if card else link.text
                        
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
                            # Название обычно самая длинная строка
                            elif len(line) > len(name) and not line.isdigit():
                                name = line
                        
                        if name:
                            products.append({
                                "id": product_id,
                                "name": name[:100],  # Ограничиваем длину
                                "regular_price": price,
                                "discount_price": price,
                                "category_name": category_name
                            })
                    except:
                        continue
                        
            except Exception as e:
                pass
            
            # Прокрутка вниз
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.5)
            
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
            scroll_count += 1
        
        return products
    
    def _extract_product_from_card(self, card, category_name: str) -> Dict:
        """
        Извлекает данные товара из DOM-элемента карточки
        
        Args:
            card: WebElement карточки товара
            category_name: Название категории
            
        Returns:
            Данные товара
        """
        from selenium.webdriver.common.by import By
        
        product = {
            "id": "",
            "name": "",
            "regular_price": 0,
            "discount_price": 0,
            "category_name": category_name
        }
        
        try:
            # Пробуем извлечь название
            for sel in ["h3", "h4", "[class*='name']", "[class*='title']"]:
                try:
                    name_el = card.find_element(By.CSS_SELECTOR, sel)
                    product["name"] = name_el.text.strip()
                    break
                except:
                    pass
            
            # Пробуем извлечь цену
            price_text = card.text
            prices = re.findall(r'(\d+(?:[.,]\d+)?)\s*₽', price_text)
            if prices:
                prices = [float(p.replace(',', '.')) for p in prices]
                product["regular_price"] = max(prices) if prices else 0
                product["discount_price"] = min(prices) if prices else product["regular_price"]
            
            # ID из ссылки
            try:
                link = card.find_element(By.TAG_NAME, "a")
                href = link.get_attribute("href")
                if href:
                    match = re.search(r'/product/(\d+)', href)
                    if match:
                        product["id"] = match.group(1)
            except:
                product["id"] = str(hash(product["name"]))[:8]
                
        except Exception as e:
            pass
        
        return product
    
    def _parse_product(self, product: dict, category_name: str = "") -> Dict:
        """
        Парсит данные товара из API
        
        Args:
            product: Сырые данные товара
            category_name: Название категории
            
        Returns:
            Отформатированные данные товара
        """
        # Извлекаем цены
        price_data = product.get("price", {})
        
        if isinstance(price_data, dict):
            regular_price = price_data.get("regular", 0) or price_data.get("value", 0)
            discount_price = price_data.get("discount", 0) or price_data.get("promo", 0)
        else:
            regular_price = product.get("regular_price", 0) or product.get("price", 0)
            discount_price = product.get("discount_price", 0) or product.get("promo_price", 0)
        
        # Нормализуем цены (могут быть в копейках)
        if regular_price > 100000:
            regular_price = regular_price / 100
        if discount_price > 100000:
            discount_price = discount_price / 100
        
        return {
            "id": str(product.get("plu") or product.get("id") or product.get("sku", "")),
            "name": product.get("name") or product.get("title", ""),
            "regular_price": float(regular_price) if regular_price else 0,
            "discount_price": float(discount_price) if discount_price else float(regular_price) if regular_price else 0,
            "unit": product.get("unit") or product.get("measure_unit", "шт"),
            "weight": str(product.get("weight", "") or product.get("measure_value", "")),
            "brand": self._extract_brand(product),
            "category_name": category_name,
            "image_url": product.get("image_url") or product.get("img") or product.get("image", ""),
            "in_stock": product.get("in_stock", True)
        }
    
    def _extract_brand(self, product: dict) -> str:
        """Извлекает бренд из данных товара"""
        brand = product.get("brand", "")
        if isinstance(brand, dict):
            return brand.get("name", "")
        return str(brand) if brand else ""
    
    def scrape_all_products(self, max_categories: int = None, max_products_per_category: int = 50) -> List[Dict]:
        """
        Скрапит все товары из всех категорий
        
        Args:
            max_categories: Максимальное количество категорий (None = все)
            max_products_per_category: Максимум товаров на категорию
            
        Returns:
            Список всех товаров
        """
        print("\n" + "="*60)
        print("  СКРАППЕР ПЯТЁРОЧКА (5ka.ru)")
        print("="*60)
        
        try:
            # Инициализируем драйвер
            print("\n[0] Инициализация браузера...")
            self._init_driver()
            
            # Получаем категории
            categories = self.get_categories()
            
            if not categories:
                print("[!] Категории не найдены!")
                return []
            
            # Ограничиваем количество категорий
            if max_categories:
                categories = categories[:max_categories]
            
            # Скрапим товары
            print(f"\n[2] Получение товаров из {len(categories)} категорий...")
            
            all_products = []
            seen_ids = set()
            
            for i, category in enumerate(categories, 1):
                cat_name = category.get("name", "Unknown")
                print(f"\n  [{i}/{len(categories)}] {cat_name}...", end=" ", flush=True)
                
                try:
                    products = self.get_products_from_category(category, max_products_per_category)
                    
                    new_products = 0
                    for product in products:
                        prod_id = product.get("id")
                        if prod_id and prod_id not in seen_ids:
                            all_products.append(product)
                            seen_ids.add(prod_id)
                            new_products += 1
                    
                    print(f"найдено {new_products} товаров")
                    
                except Exception as e:
                    print(f"ошибка: {e}")
                
                # Увеличенная пауза для избежания блокировки
                time.sleep(5)
            
            self.all_products = all_products
            print(f"\n[OK] Итого уникальных товаров: {len(all_products)}")
            
        finally:
            self._close_driver()
        
        return all_products
    
    def save_to_json(self, filename: str = None) -> str:
        """
        Сохраняет данные в JSON файл
        
        Args:
            filename: Имя файла
            
        Returns:
            Путь к сохранённому файлу
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"products_5ka_{timestamp}.json"
        
        with open(filename, "w", encoding="utf-8") as f:
            json.dump({
                "metadata": {
                    "source": "5ka.ru",
                    "scraped_at": datetime.now().isoformat(),
                    "total_products": len(self.all_products),
                    "total_categories": len(self.categories)
                },
                "categories": self.categories,
                "products": self.all_products
            }, f, ensure_ascii=False, indent=2)
        
        print(f"[OK] Сохранено в {filename}")
        return filename
    
    def save_to_csv(self, filename: str = None) -> str:
        """
        Сохраняет данные в CSV файл
        
        Args:
            filename: Имя файла
            
        Returns:
            Путь к сохранённому файлу
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"products_5ka_{timestamp}.csv"
        
        if not self.all_products:
            print("[!] Нет данных для сохранения")
            return ""
        
        fieldnames = ["id", "name", "regular_price", "discount_price", "unit", 
                      "weight", "brand", "category_name", "in_stock"]
        
        with open(filename, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(self.all_products)
        
        print(f"[OK] Сохранено в {filename}")
        return filename
    
    def print_summary(self):
        """Выводит сводку по собранным данным"""
        if not self.all_products:
            print("Нет данных для отображения")
            return
        
        print("\n" + "="*60)
        print("  СВОДКА")
        print("="*60)
        print(f"Всего товаров: {len(self.all_products)}")
        print(f"Всего категорий: {len(self.categories)}")
        
        # Статистика по ценам
        prices = [p["regular_price"] for p in self.all_products if p.get("regular_price", 0) > 0]
        if prices:
            print(f"\nЦены (руб.):")
            print(f"  Минимальная: {min(prices):.2f}")
            print(f"  Максимальная: {max(prices):.2f}")
            print(f"  Средняя: {sum(prices)/len(prices):.2f}")
        
        # Пример товаров
        print("\nПримеры товаров:")
        for i, product in enumerate(self.all_products[:5], 1):
            name = product['name'][:40] + "..." if len(product['name']) > 40 else product['name']
            print(f"  {i}. {name} - {product.get('regular_price', 0):.2f} руб.")


# ============================================================================
# АЛЬТЕРНАТИВНЫЙ ПРОСТОЙ СКРАППЕР (без Selenium)
# ============================================================================

class SimpleScraper:
    """Простой скраппер на requests (работает если API доступен)"""
    
    def __init__(self):
        import requests
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Accept-Language": "ru-RU,ru;q=0.9",
        })
        self.all_products = []
        self.categories = []
    
    def scrape(self, max_items: int = 100) -> List[Dict]:
        """Пробует получить данные через различные API endpoints"""
        import requests
        
        print("\n[Простой скраппер] Попытка получить данные...")
        
        # Список публичных API endpoints для попытки
        endpoints = [
            "https://5ka.ru/api/v2/special_offers/",
            "https://api.5ka.ru/api/public/v1/promo-offers/?limit=100",
        ]
        
        for url in endpoints:
            try:
                print(f"  Пробую: {url[:50]}...")
                resp = self.session.get(url, timeout=10)
                
                if resp.status_code == 200:
                    data = resp.json()
                    products = data if isinstance(data, list) else data.get("results", data.get("products", []))
                    
                    if products:
                        for p in products[:max_items]:
                            self.all_products.append({
                                "id": str(p.get("id", p.get("plu", ""))),
                                "name": p.get("name", p.get("title", "")),
                                "regular_price": p.get("current_prices", {}).get("price_reg__min", 0) / 100 if p.get("current_prices") else 0,
                                "discount_price": p.get("current_prices", {}).get("price_promo__min", 0) / 100 if p.get("current_prices") else 0,
                                "category_name": "Акции",
                            })
                        
                        print(f"  [OK] Получено {len(self.all_products)} товаров")
                        return self.all_products
            except Exception as e:
                print(f"  [!] Ошибка: {e}")
        
        print("  [!] Не удалось получить данные через API")
        return []
    
    def save_to_json(self, filename: str = "products_5ka_simple.json"):
        if self.all_products:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(self.all_products, f, ensure_ascii=False, indent=2)
            print(f"[OK] Сохранено в {filename}")


def main():
    """Основная функция"""
    import os
    import argparse
    
    # Парсим аргументы командной строки
    parser = argparse.ArgumentParser(description="Скраппер Пятёрочка (5ka.ru)")
    parser.add_argument("--proxy", help="Прокси сервер (host:port)")
    parser.add_argument("--no-headless", action="store_true", help="Показать браузер")
    parser.add_argument("--categories", type=int, default=10, help="Количество категорий")
    parser.add_argument("--products", type=int, default=30, help="Товаров на категорию")
    parser.add_argument("--mode", choices=["1", "2", "3"], help="Режим (1=полный, 2=простой, 3=авто)")
    
    args, unknown = parser.parse_known_args()
    
    # Прокси из переменной окружения или аргумента
    proxy = args.proxy or os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY")
    
    print("="*60)
    print("  СКРАППЕР ПЯТЁРОЧКА (5ka.ru)")
    print("="*60)
    
    if proxy:
        print(f"\n[*] Будет использован прокси: {proxy}")
    
    print("\nВыберите режим:")
    print("  1 - Полный скраппинг (требует Selenium + Chrome)")
    print("  2 - Простой скраппинг (только акционные товары)")
    print("  3 - Автоматический выбор")
    
    choice = args.mode or input("\nВаш выбор (1/2/3): ").strip() or "3"
    
    if choice == "1":
        try:
            scraper = Pyaterochka5kaScraper(
                headless=not args.no_headless,
                proxy=proxy
            )
            products = scraper.scrape_all_products(
                max_categories=args.categories,
                max_products_per_category=args.products
            )
            
            if products:
                scraper.save_to_json()
                scraper.save_to_csv()
                scraper.print_summary()
        except ImportError:
            print("\n[!] Selenium не установлен!")
            print("    Установите: pip install selenium")
            print("    И скачайте ChromeDriver")
            
    elif choice == "2":
        scraper = SimpleScraper()
        scraper.scrape(100)
        scraper.save_to_json()
        
    else:  # Авто
        # Сначала пробуем простой метод
        simple = SimpleScraper()
        products = simple.scrape(100)
        
        if products:
            simple.save_to_json()
        else:
            print("\n[!] Простой метод не сработал.")
            print("    Для полного скраппинга нужен Selenium:")
            print("    pip install selenium")


if __name__ == "__main__":
    main()
