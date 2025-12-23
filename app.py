# -*- coding: utf-8 -*-
"""
Веб-приложение для просмотра товаров Пятёрочки и Магнита
С улучшенным сравнением цен и поиском похожих товаров
"""

import sqlite3
import os
import re
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from datetime import datetime

# Импорт модуля авторизации
from auth import (
    init_users_db, register_user, login_user, get_current_user, login_required,
    add_to_favorites, remove_from_favorites, get_favorites, is_favorite,
    add_price_alert, remove_price_alert, get_price_alerts, has_price_alert,
    link_telegram_with_code, unlink_telegram, get_user_stats
)

# Импорт конфигурации
try:
    from config import TELEGRAM_BOT_USERNAME
except ImportError:
    TELEGRAM_BOT_USERNAME = 'PricioNotifyBot'

app = Flask(__name__)
app.secret_key = 'pricio-secret-key-change-in-production-2024'  # Для сессий

# Базы данных
DATABASES = {
    '5ka': {'file': 'products.db', 'name': 'Пятёрочка', 'color': '#E30613'},
    'magnit': {'file': 'products_magnit.db', 'name': 'Магнит', 'color': '#E31E24'}
}


# ============================================================================
# УЛУЧШЕННЫЙ ПОИСК
# ============================================================================

def normalize_text(text: str) -> str:
    """Нормализация текста для поиска (Python-сторона)"""
    if not text:
        return ""
    # Приводим к нижнему регистру (работает с кириллицей!)
    text = text.lower()
    # Заменяем ё на е
    text = text.replace('ё', 'е')
    # Убираем лишние пробелы
    text = ' '.join(text.split())
    return text


def tokenize_query(query: str) -> List[str]:
    """Разбиваем запрос на токены (слова)"""
    query = normalize_text(query)
    # Разбиваем по пробелам и знакам препинания
    tokens = re.split(r'[\s,.\-_/\\()]+', query)
    # Фильтруем пустые и короткие токены
    tokens = [t for t in tokens if len(t) >= 2]
    return tokens


def smart_search_products(conn, search_query: str, category: str = None, limit: int = 500) -> Tuple[List, int]:
    """
    Улучшенный поиск товаров с ранжированием
    
    SQLite LOWER() не работает с кириллицей, поэтому:
    1. Загружаем все товары (или по категории)
    2. Фильтруем и ранжируем на Python
    """
    if not search_query or not search_query.strip():
        return [], 0
    
    tokens = tokenize_query(search_query)
    if not tokens:
        return [], 0
    
    normalized_query = normalize_text(search_query)
    
    # Загружаем товары из базы
    if category:
        query = "SELECT * FROM products WHERE category = ?"
        all_products = conn.execute(query, (category,)).fetchall()
    else:
        query = "SELECT * FROM products"
        all_products = conn.execute(query).fetchall()
    
    results = []
    
    for row in all_products:
        product = dict(row)
        name = product.get('name', '')
        name_normalized = normalize_text(name)
        cat_normalized = normalize_text(product.get('category', '') or '')
        
        # Подсчитываем релевантность
        relevance = 0
        
        # Точное совпадение всей фразы
        if normalized_query in name_normalized:
            relevance = 100
            # Бонус если название начинается с запроса
            if name_normalized.startswith(normalized_query):
                relevance = 110
            # Бонус за точное совпадение слова
            if normalized_query == name_normalized or f" {normalized_query} " in f" {name_normalized} ":
                relevance = 120
        else:
            # Проверяем сколько токенов найдено
            matches = sum(1 for t in tokens if t in name_normalized)
            
            if matches == len(tokens):
                # Все токены найдены
                relevance = 80
            elif matches > 0:
                # Часть токенов найдена
                relevance = 30 + matches * 15
            elif normalized_query in cat_normalized:
                # Совпадение с категорией
                relevance = 20
        
        if relevance > 0:
            product['relevance'] = relevance
            results.append(product)
    
    # Сортируем по релевантности, затем по длине названия (короткие выше)
    results.sort(key=lambda x: (
        -x.get('relevance', 0),
        len(x.get('name', ''))
    ))
    
    total = len(results)
    return results[:limit], total


def count_search_results(conn, search_query: str, category: str = None) -> int:
    """Подсчёт результатов поиска"""
    results, total = smart_search_products(conn, search_query, category, limit=10000)
    return total


# ============================================================================
# ПАРСИНГ АТРИБУТОВ ТОВАРА
# ============================================================================

@dataclass
class ProductAttributes:
    """Структурированные атрибуты товара"""
    product_type: Optional[str] = None   # молоко, сыр, колбаса
    brand: Optional[str] = None          # Простоквашино, Mucho Mas
    volume_ml: Optional[float] = None    # объём в мл
    weight_g: Optional[float] = None     # вес в граммах
    fat_percent: Optional[float] = None  # жирность
    quantity: Optional[int] = None       # количество в упаковке


# Словарь типов продуктов для нормализации
PRODUCT_TYPES = {
    'молоко': ['молоко', 'молочко'],
    'кефир': ['кефир'],
    'йогурт': ['йогурт', 'йогу|рт'],
    'творог': ['творог', 'творожок', 'творожный', 'творожная', 'творожное'],
    'сметана': ['сметана'],
    'сливки': ['сливки'],
    'сыр': ['сыр', 'сырок', 'сырный', 'сырная'],
    'масло': ['масло'],
    'колбаса': ['колбаса', 'колбасный', 'колбасная', 'колбаски'],
    'сосиски': ['сосиски', 'сосиска', 'сардельки', 'сарделька'],
    'ветчина': ['ветчина'],
    'бекон': ['бекон'],
    'курица': ['курица', 'куриный', 'куриная', 'куриное', 'цыплёнок', 'цыпленок'],
    'индейка': ['индейка', 'индюшиный', 'индюшиная'],
    'свинина': ['свинина', 'свиной', 'свиная', 'свиное'],
    'говядина': ['говядина', 'говяжий', 'говяжья', 'говяжье'],
    'фарш': ['фарш'],
    'рыба': ['рыба', 'рыбный', 'рыбная', 'рыбное'],
    'лосось': ['лосось', 'сёмга', 'семга', 'форель'],
    'креветки': ['креветки', 'креветка'],
    'хлеб': ['хлеб', 'хлебец', 'хлебцы'],
    'батон': ['батон', 'багет'],
    'булка': ['булка', 'булочка', 'булочки'],
    'вино': ['вино'],
    'пиво': ['пиво'],
    'водка': ['водка'],
    'виски': ['виски'],
    'коньяк': ['коньяк'],
    'сок': ['сок', 'нектар'],
    'вода': ['вода', 'минералка', 'минеральная'],
    'лимонад': ['лимонад', 'газировка'],
    'чай': ['чай'],
    'кофе': ['кофе'],
    'шоколад': ['шоколад', 'шоколадка', 'шоколадный', 'шоколадная'],
    'конфеты': ['конфеты', 'конфета'],
    'печенье': ['печенье'],
    'торт': ['торт'],
    'мороженое': ['мороженое', 'пломбир', 'эскимо'],
    'чипсы': ['чипсы'],
    'орехи': ['орехи', 'орех', 'арахис', 'миндаль', 'фундук', 'кешью', 'фисташки'],
    'яйца': ['яйца', 'яйцо'],
    'макароны': ['макароны', 'паста', 'спагетти', 'лапша'],
    'рис': ['рис'],
    'гречка': ['гречка', 'гречневая'],
    'овсянка': ['овсянка', 'овсяная', 'овсяные'],
    'мука': ['мука'],
    'сахар': ['сахар'],
    'соль': ['соль'],
    'бананы': ['бананы', 'банан'],
    'яблоки': ['яблоки', 'яблоко'],
    'апельсины': ['апельсины', 'апельсин'],
    'мандарины': ['мандарины', 'мандарин'],
    'лимоны': ['лимоны', 'лимон'],
    'виноград': ['виноград'],
    'помидоры': ['помидоры', 'помидор', 'томаты', 'томат'],
    'огурцы': ['огурцы', 'огурец'],
    'картофель': ['картофель', 'картошка'],
    'морковь': ['морковь', 'морковка'],
    'лук': ['лук'],
    'капуста': ['капуста'],
}

# Известные бренды (русские)
RUSSIAN_BRANDS = {
    'простоквашино', 'домик в деревне', 'вкуснотеево', 'савушкин', 'брест-литовск',
    'черкизово', 'мираторг', 'останкино', 'велком', 'папа может',
    'добрый', 'любимый', 'фруктовый сад', 'моя семья', 'j7', 'rich',
    'макфа', 'барилла', 'щебекинские',
    'lay\'s', 'lays', 'pringles', 'cheetos',
    'аленка', 'бабаевский', 'красный октябрь', 'коркунов', 'merci',
    'bonduelle', 'heinz', 'calve',
}

# Стоп-слова (не определяют тип продукта)
STOP_WORDS = {
    'магнит', 'пятёрочка', 'пятерочка', 'для', 'без', 'или', 'the', 'штук', 'шт',
    'упаковка', 'пакет', 'бзмж', 'premium', 'extra', 'new', 'global', 'village',
    'напиток', 'продукт', 'изделие', 'товар', 'набор', 'ассорти', 'микс',
    'добавлением', 'натуральный', 'свежий', 'вкусный', 'домашний', 'классический',
    'молочный', 'молочная', 'молочное', 'детский', 'детская', 'взрослый',
    'гавайский', 'тропический', 'летняя', 'летний', 'садовая', 'садовый',
    'лесная', 'лесной', 'красное', 'красный', 'белое', 'белый', 'зеленый', 'зелёный',
    'фасованное', 'фасованный', 'отборные', 'отборный', 'сокосодержащий',
    'восстановленный', 'протеиновый', 'протеиновое', 'высокобелковый',
    'энергетический', 'газированный', 'негазированный', 'безалкогольный',
    'с', 'и', 'в', 'на', 'из', 'по', 'со'
}


def parse_product_attributes(name: str) -> ProductAttributes:
    """Извлечение структурированных атрибутов из названия товара"""
    name_lower = name.lower()
    attrs = ProductAttributes()
    
    # Извлекаем объём: 750мл, 1л, 1.5л, 0.5 л
    volume_match = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:мл|ml)\b', name_lower)
    if volume_match:
        attrs.volume_ml = float(volume_match.group(1).replace(',', '.'))
    else:
        volume_match = re.search(r'(\d+(?:[.,]\d+)?)\s*л(?:итр|\b)', name_lower)
        if volume_match:
            attrs.volume_ml = float(volume_match.group(1).replace(',', '.')) * 1000
    
    # Извлекаем вес: 500г, 1кг, 1.2кг
    weight_match = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:г|гр|грамм)(?!\w)', name_lower)
    if weight_match:
        attrs.weight_g = float(weight_match.group(1).replace(',', '.'))
    else:
        weight_match = re.search(r'(\d+(?:[.,]\d+)?)\s*кг\b', name_lower)
        if weight_match:
            attrs.weight_g = float(weight_match.group(1).replace(',', '.')) * 1000
    
    # Извлекаем жирность: 3.2%, 2,5%
    fat_match = re.search(r'(\d+(?:[.,]\d+)?)\s*%', name_lower)
    if fat_match:
        attrs.fat_percent = float(fat_match.group(1).replace(',', '.'))
    
    # Извлекаем количество: 6шт, x12
    qty_match = re.search(r'(\d+)\s*(?:шт|штук)|x(\d+)', name_lower)
    if qty_match:
        attrs.quantity = int(qty_match.group(1) or qty_match.group(2))
    
    # Извлекаем бренд (латиница - приоритет)
    latin_brands = re.findall(r'\b([A-Z][a-zA-Z\']+(?:\s+[A-Z][a-zA-Z\']+)?)\b', name)
    if latin_brands:
        # Берём самый длинный бренд из латиницы
        attrs.brand = max(latin_brands, key=len)
    
    # Проверяем известные русские бренды
    if not attrs.brand:
        for brand in RUSSIAN_BRANDS:
            if brand in name_lower:
                attrs.brand = brand.title()
                break
    
    # Определяем тип продукта
    for product_type, keywords in PRODUCT_TYPES.items():
        for keyword in keywords:
            if keyword in name_lower:
                attrs.product_type = product_type
                break
        if attrs.product_type:
            break
    
    # Если тип не найден - берём первое русское слово
    if not attrs.product_type:
        words = re.findall(r'[а-яёА-ЯЁ]{4,}', name_lower)
        words = [w for w in words if w not in STOP_WORDS]
        if words:
            attrs.product_type = words[0]
    
    return attrs


def stem_russian(word: str) -> str:
    """Простой стемминг для русских слов - убираем окончания"""
    if len(word) < 4:
        return word
    endings = ['ами', 'ями', 'ах', 'ях', 'ов', 'ев', 'ей', 'ий', 'ый', 'ая', 'яя', 'ое', 'ее',
               'ы', 'и', 'а', 'я', 'у', 'ю', 'е', 'о']
    for ending in endings:
        if word.endswith(ending) and len(word) - len(ending) >= 3:
            return word[:-len(ending)]
    return word


# ============================================================================
# СКОРИНГ ПОХОЖЕСТИ
# ============================================================================

def calculate_similarity_score(attrs1: ProductAttributes, attrs2: ProductAttributes,
                                name1: str, name2: str) -> int:
    """
    Вычисляет оценку похожести товаров от 0 до 100.
    Чем выше - тем более похожие товары.
    """
    score = 0
    
    # Нормализуем названия
    name1_norm = normalize_text(name1)
    name2_norm = normalize_text(name2)
    
    # Извлекаем слова (минимум 3 буквы)
    words1 = set(re.findall(r'[а-яёa-z]{3,}', name1_norm))
    words2 = set(re.findall(r'[а-яёa-z]{3,}', name2_norm))
    words1 -= STOP_WORDS
    words2 -= STOP_WORDS
    
    # Получаем первое значимое слово (обычно это тип продукта)
    first_word1 = name1_norm.split()[0] if name1_norm else ""
    first_word2 = name2_norm.split()[0] if name2_norm else ""
    
    # 1. Первое слово (тип продукта) - самый важный критерий
    first_word_match = False
    if first_word1 and first_word2:
        if first_word1 == first_word2:
            score += 35
            first_word_match = True
        elif stem_russian(first_word1) == stem_russian(first_word2):
            score += 30
            first_word_match = True
        elif first_word1 in first_word2 or first_word2 in first_word1:
            score += 25  # Одно слово содержит другое
            first_word_match = True
    
    # Если первые слова совсем не совпадают, проверяем product_type
    if not first_word_match and attrs1.product_type and attrs2.product_type:
        if attrs1.product_type == attrs2.product_type:
            score += 30
            first_word_match = True
        elif stem_russian(attrs1.product_type) == stem_russian(attrs2.product_type):
            score += 25
            first_word_match = True
    
    # Если нет совпадения по типу/первому слову - товары не похожи
    if not first_word_match:
        # Но даём шанс если много общих слов
        common_words = words1 & words2
        if len(common_words) >= 2:
            score += 20  # Бонус за общие слова
        else:
            return 0
    
    # 2. Бренд (очень важно для сравнения цен!)
    if attrs1.brand and attrs2.brand:
        if attrs1.brand.lower() == attrs2.brand.lower():
            score += 35  # Тот же бренд - большой бонус
        else:
            score += 5   # Разные бренды - минимальный бонус
    elif attrs1.brand or attrs2.brand:
        score += 3  # У одного есть бренд, у другого нет
    else:
        score += 10  # Оба без бренда - возможно базовые продукты
    
    # 3. Объём/вес (важно для корректного сравнения)
    if attrs1.volume_ml and attrs2.volume_ml:
        ratio = min(attrs1.volume_ml, attrs2.volume_ml) / max(attrs1.volume_ml, attrs2.volume_ml)
        if ratio > 0.95:
            score += 12
        elif ratio > 0.8:
            score += 8
        elif ratio > 0.5:
            score += 4
    elif attrs1.weight_g and attrs2.weight_g:
        ratio = min(attrs1.weight_g, attrs2.weight_g) / max(attrs1.weight_g, attrs2.weight_g)
        if ratio > 0.95:
            score += 12
        elif ratio > 0.8:
            score += 8
        elif ratio > 0.5:
            score += 4
    
    # 4. Жирность (для молочки)
    if attrs1.fat_percent and attrs2.fat_percent:
        if abs(attrs1.fat_percent - attrs2.fat_percent) < 0.5:
            score += 8
        elif abs(attrs1.fat_percent - attrs2.fat_percent) < 1.5:
            score += 4
    
    # 5. Пересечение слов в названии (fuzzy matching)
    if words1 and words2:
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        if union > 0:
            jaccard = intersection / union
            score += int(jaccard * 15)  # До 15 баллов за совпадение слов
    
    return min(score, 100)


# ============================================================================
# ПОИСК ПОХОЖИХ ТОВАРОВ
# ============================================================================

def get_db(store: str = '5ka'):
    """Получение соединения с БД"""
    db_file = DATABASES.get(store, DATABASES['5ka'])['file']
    if not os.path.exists(db_file):
        return None
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    return conn


def get_similar_products_v2(store_id: str, product_name: str, product_id: str, 
                            current_price: float, category: str = None, limit: int = 6) -> List[Dict]:
    """
    Улучшенный поиск похожих товаров с многоуровневым скорингом.
    Возвращает список товаров с дополнительными полями:
    - similarity_score: оценка похожести (0-100)
    - price_diff: разница в цене
    - is_cheaper: дешевле ли этот товар
    """
    conn = get_db(store_id)
    if not conn:
        return []
    
    # Парсим атрибуты исходного товара
    source_attrs = parse_product_attributes(product_name)
    
    # Нормализуем название для поиска
    source_name_normalized = normalize_text(product_name)
    source_words = set(tokenize_query(product_name))
    
    # Формируем поисковые термы
    search_terms = set()
    
    # 1. Все слова из названия (минимум 3 буквы)
    for word in source_words:
        if len(word) >= 3:
            search_terms.add(word)
            # Добавляем стемм
            stemmed = stem_russian(word)
            if len(stemmed) >= 3:
                search_terms.add(stemmed)
    
    # 2. Тип продукта
    if source_attrs.product_type:
        search_terms.add(source_attrs.product_type.lower())
        stemmed = stem_russian(source_attrs.product_type.lower())
        if len(stemmed) >= 3:
            search_terms.add(stemmed)
    
    # 3. Бренд
    if source_attrs.brand:
        search_terms.add(source_attrs.brand.lower())
    
    # Если нет терминов для поиска - берём первое слово названия
    if not search_terms:
        first_word = source_name_normalized.split()[0] if source_name_normalized else ""
        if len(first_word) >= 3:
            search_terms.add(first_word)
    
    # Загружаем все товары и фильтруем на Python (SQLite LOWER не работает с кириллицей)
    all_products = conn.execute("SELECT * FROM products").fetchall()
    
    candidates = []
    seen_ids = {product_id}  # Исключаем текущий товар
    
    for row in all_products:
        if row['product_id'] in seen_ids:
            continue
        
        name_normalized = normalize_text(row['name'])
        
        # Проверяем совпадение с любым поисковым термом
        match_found = False
        for term in search_terms:
            if term in name_normalized:
                match_found = True
                break
        
        if match_found:
            seen_ids.add(row['product_id'])
            candidates.append(dict(row))
    
    conn.close()
    
    # Скорим всех кандидатов
    scored_candidates = []
    for candidate in candidates:
        cand_attrs = parse_product_attributes(candidate['name'])
        score = calculate_similarity_score(source_attrs, cand_attrs, product_name, candidate['name'])
        
        if score > 20:  # Минимальный порог релевантности
            cand_price = candidate.get('current_price', 0) or 0
            price_diff = cand_price - current_price if current_price else 0
            
            scored_candidates.append({
                **candidate,
                'similarity_score': score,
                'price_diff': price_diff,
                'is_cheaper': price_diff < -0.01,
                'is_exact_match': score >= 70,  # Высокий скор = точный аналог
                # Нормализованная цена за единицу
                'price_per_unit': calculate_price_per_unit(candidate),
            })
    
    # Сортируем: сначала по скору, потом по цене
    scored_candidates.sort(key=lambda x: (-x['similarity_score'], x.get('current_price', 0) or 0))
    
    return scored_candidates[:limit]


def calculate_price_per_unit(product: Dict) -> Optional[Dict]:
    """Вычисляет цену за единицу (литр или кг)"""
    attrs = parse_product_attributes(product.get('name', ''))
    price = product.get('current_price', 0) or 0
    
    if not price:
        return None
    
    if attrs.volume_ml and attrs.volume_ml > 0:
        price_per_liter = price / attrs.volume_ml * 1000
        return {'value': price_per_liter, 'unit': 'л', 'display': f"{price_per_liter:.2f} ₽/л"}
    
    if attrs.weight_g and attrs.weight_g > 0:
        price_per_kg = price / attrs.weight_g * 1000
        return {'value': price_per_kg, 'unit': 'кг', 'display': f"{price_per_kg:.2f} ₽/кг"}
    
    return None


def find_exact_match_cross_store(product_name: str, product_id: str, 
                                  source_store: str, current_price: float) -> Optional[Dict]:
    """
    Поиск точного аналога товара в другом магазине.
    Возвращает лучшее совпадение или None.
    """
    target_store = 'magnit' if source_store == '5ka' else '5ka'
    
    similar = get_similar_products_v2(
        target_store, product_name, product_id, 
        current_price, limit=1
    )
    
    if similar and similar[0].get('is_exact_match'):
        return {
            'product': similar[0],
            'store_id': target_store,
            'store': DATABASES[target_store]
        }
    
    return None


# ============================================================================
# СТАНДАРТНЫЕ ФУНКЦИИ
# ============================================================================

def init_db(store: str):
    """Инициализация базы данных"""
    conn = get_db(store)
    if not conn:
        return
    
    conn.execute('''
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
    
    conn.execute('''
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            price REAL NOT NULL,
            old_price REAL,
            recorded_at TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()


def get_all_stats():
    """Получение статистики по всем магазинам"""
    stats = {}
    for store_id, store_info in DATABASES.items():
        conn = get_db(store_id)
        if conn:
            try:
                count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
                stats[store_id] = {
                    'name': store_info['name'],
                    'color': store_info['color'],
                    'count': count
                }
            except:
                stats[store_id] = {'name': store_info['name'], 'color': store_info['color'], 'count': 0}
            conn.close()
        else:
            stats[store_id] = {'name': store_info['name'], 'color': store_info['color'], 'count': 0}
    return stats


# ============================================================================
# МАРШРУТЫ
# ============================================================================

@app.route('/')
def index():
    """Главная страница - выбор магазина"""
    stats = get_all_stats()
    user = get_current_user()
    return render_template('home.html', stores=stats, user=user, active_store=None)


@app.route('/store/<store_id>')
def store_products(store_id):
    """Страница товаров магазина"""
    if store_id not in DATABASES:
        return "Магазин не найден", 404
    
    user = get_current_user()
    store_name = DATABASES[store_id]['name']
    
    conn = get_db(store_id)
    if not conn:
        return render_template('index.html',
                               products=[],
                               categories=[],
                               search_query='',
                               current_category='',
                               page=1,
                               total_pages=0,
                               total_products=0,
                               store_name=store_name,
                               store_id=store_id,
                               user=user,
                               active_store=store_id)
    
    # Параметры
    search = request.args.get('search', '').strip()
    category = request.args.get('category', '')
    sort = request.args.get('sort', 'relevance' if search else 'last_updated')
    order = request.args.get('order', 'desc')
    page = int(request.args.get('page', 1))
    per_page = 50
    
    # Получаем категории
    categories_rows = conn.execute(
        "SELECT DISTINCT category FROM products WHERE category IS NOT NULL AND category != '' ORDER BY category"
    ).fetchall()
    categories = [row['category'] for row in categories_rows]
    
    # Если есть поисковый запрос - используем умный поиск
    if search:
        all_results, total = smart_search_products(conn, search, category, limit=500)
        
        # Пагинация результатов
        start = (page - 1) * per_page
        end = start + per_page
        products = all_results[start:end]
        total_pages = (total + per_page - 1) // per_page
    else:
        # Обычный запрос без поиска
        query = "SELECT * FROM products WHERE 1=1"
        params = []
        
        if category:
            query += " AND category = ?"
            params.append(category)
        
        valid_sorts = ['name', 'current_price', 'last_updated', 'category', 'min_price', 'max_price', 'rating']
        if sort in valid_sorts:
            query += f" ORDER BY {sort} {'DESC' if order == 'desc' else 'ASC'}"
        else:
            query += " ORDER BY last_updated DESC"
        
        query += f" LIMIT {per_page} OFFSET {(page - 1) * per_page}"
        
        products = [dict(row) for row in conn.execute(query, params).fetchall()]
        
        # Подсчёт общего количества
        count_query = "SELECT COUNT(*) FROM products WHERE 1=1"
        count_params = []
        if category:
            count_query += " AND category = ?"
            count_params.append(category)
        
        total = conn.execute(count_query, count_params).fetchone()[0]
        total_pages = (total + per_page - 1) // per_page
    
    conn.close()
    
    return render_template('index.html',
                           products=products,
                           categories=categories,
                           search_query=search,
                           current_category=category,
                           page=page,
                           total_pages=total_pages,
                           total_products=total,
                           store_name=store_name,
                           store_id=store_id,
                           user=user,
                           active_store=store_id)


@app.route('/store/<store_id>/product/<product_id>')
def product_detail(store_id, product_id):
    """Страница товара с историей цен и похожими товарами"""
    if store_id not in DATABASES:
        return "Магазин не найден", 404
    
    user = get_current_user()
    store_name = DATABASES[store_id]['name']
    
    conn = get_db(store_id)
    if not conn:
        return "База данных не найдена", 404
    
    product = conn.execute(
        "SELECT * FROM products WHERE product_id = ?", (product_id,)
    ).fetchone()
    
    if not product:
        conn.close()
        return "Товар не найден", 404
    
    history = conn.execute('''
        SELECT price, old_price, recorded_at 
        FROM price_history 
        WHERE product_id = ? 
        ORDER BY recorded_at ASC
    ''', (product_id,)).fetchall()
    
    conn.close()
    
    product_dict = dict(product)
    current_price = product_dict.get('current_price', 0) or 0
    
    # Парсим атрибуты текущего товара
    product_attrs = parse_product_attributes(product_dict['name'])
    price_per_unit = calculate_price_per_unit(product_dict)
    
    # Похожие товары из этого магазина
    similar_same_store = get_similar_products_v2(
        store_id, product_dict['name'], product_id, 
        current_price, product_dict.get('category'), limit=6
    )
    
    # Похожие товары из другого магазина
    other_store_id = 'magnit' if store_id == '5ka' else '5ka'
    similar_other_store = get_similar_products_v2(
        other_store_id, product_dict['name'], product_id,
        current_price, limit=6
    )
    
    # Лучший аналог в другом магазине (для сравнения)
    comparison = None
    if similar_other_store:
        best = similar_other_store[0]
        if best.get('is_exact_match') or best.get('similarity_score', 0) >= 40:
            comparison = dict(best)
            comparison['store_id'] = other_store_id
            comparison['store_name'] = DATABASES[other_store_id]['name']
    
    # История цен для графика (JSON)
    import json
    price_history_json = json.dumps([
        {'date': h['recorded_at'][:10] if h['recorded_at'] else '', 'price': h['price']}
        for h in history
    ]) if history else '[]'
    
    # Проверяем избранное и уведомления
    user_is_favorite = False
    user_has_alert = False
    if user:
        user_is_favorite = is_favorite(user['id'], store_id, product_id)
        user_has_alert = has_price_alert(user['id'], store_id, product_id)
    
    return render_template('product.html', 
                           product=product_dict, 
                           price_history=history,
                           price_history_json=price_history_json,
                           store_name=store_name,
                           store_id=store_id,
                           similar_products=similar_same_store,
                           comparison=comparison,
                           user=user,
                           active_store=store_id,
                           is_favorite=user_is_favorite,
                           has_alert=user_has_alert)


@app.route('/api/stats')
def stats():
    """API для статистики"""
    return jsonify(get_all_stats())


@app.route('/api/compare/<product_id>')
def api_compare(product_id):
    """API для сравнения цен товара между магазинами"""
    store_id = request.args.get('store', '5ka')
    
    conn = get_db(store_id)
    if not conn:
        return jsonify({'error': 'Store not found'}), 404
    
    product = conn.execute(
        "SELECT * FROM products WHERE product_id = ?", (product_id,)
    ).fetchone()
    
    if not product:
        conn.close()
        return jsonify({'error': 'Product not found'}), 404
    
    conn.close()
    
    product_dict = dict(product)
    other_store_id = 'magnit' if store_id == '5ka' else '5ka'
    
    similar = get_similar_products_v2(
        other_store_id, product_dict['name'], product_id,
        product_dict.get('current_price', 0), limit=5
    )
    
    return jsonify({
        'source_product': product_dict,
        'source_store': store_id,
        'similar_in_other_store': similar,
        'other_store': other_store_id
    })


# ============================================================================
# АВТОРИЗАЦИЯ И ПОЛЬЗОВАТЕЛИ
# ============================================================================

@app.context_processor
def inject_user():
    """Добавляет текущего пользователя во все шаблоны"""
    return {'current_user': get_current_user()}


@app.route('/register', methods=['GET', 'POST'])
def register_page():
    """Страница регистрации"""
    if 'user_id' in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')
        
        if password != password_confirm:
            flash('Пароли не совпадают', 'error')
            return render_template('register.html', user=None, active_store=None)
        
        result = register_user(username, email, password)
        
        if result['success']:
            flash('Регистрация успешна! Теперь войдите в систему', 'success')
            return redirect(url_for('login_page'))
        else:
            flash(result['message'], 'error')
    
    return render_template('register.html', user=None, active_store=None)


@app.route('/login', methods=['GET', 'POST'])
def login_page():
    """Страница входа"""
    if 'user_id' in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        login = request.form.get('login', '').strip()
        password = request.form.get('password', '')
        
        result = login_user(login, password)
        
        if result['success']:
            session['user_id'] = result['user']['id']
            session['username'] = result['user']['username']
            flash(f'Добро пожаловать, {result["user"]["username"]}!', 'success')
            
            next_url = request.args.get('next')
            if next_url:
                return redirect(next_url)
            return redirect(url_for('index'))
        else:
            flash(result['message'], 'error')
    
    return render_template('login.html', user=None, active_store=None)


@app.route('/logout')
def logout():
    """Выход из системы"""
    session.clear()
    flash('Вы вышли из системы', 'success')
    return redirect(url_for('index'))


# ============================================================================
# ИЗБРАННОЕ
# ============================================================================

@app.route('/favorites')
@login_required
def favorites_page():
    """Страница избранного"""
    user = get_current_user()
    favorites_list = get_favorites(user['id'])
    alerts_list = get_price_alerts(user['id'])
    
    # Обогащаем данные избранного информацией о товарах
    enriched_favorites = []
    for fav in favorites_list:
        conn = get_db(fav['store_id'])
        if conn:
            product = conn.execute(
                "SELECT * FROM products WHERE product_id = ?", 
                (fav['product_id'],)
            ).fetchone()
            conn.close()
            
            if product:
                item = dict(fav)
                item.update(dict(product))
                item['has_alert'] = has_price_alert(user['id'], fav['store_id'], fav['product_id'])
                enriched_favorites.append(item)
    
    # Обогащаем данные уведомлений
    enriched_alerts = []
    for alert in alerts_list:
        conn = get_db(alert['store_id'])
        if conn:
            product = conn.execute(
                "SELECT name, current_price FROM products WHERE product_id = ?", 
                (alert['product_id'],)
            ).fetchone()
            conn.close()
            
            item = dict(alert)
            if product:
                item['product_name'] = product['name']
                item['last_price'] = product['current_price']
            enriched_alerts.append(item)
    
    return render_template('favorites.html', 
                           user=user, 
                           favorites=enriched_favorites,
                           alerts=enriched_alerts,
                           active_store=None)


# ============================================================================
# ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ
# ============================================================================

@app.route('/profile')
@login_required
def profile_page():
    """Страница профиля пользователя"""
    user = get_current_user()
    stats = get_user_stats(user['id'])
    
    return render_template('profile.html',
                           user=user,
                           stats=stats,
                           telegram_bot_username=TELEGRAM_BOT_USERNAME,
                           active_store=None)


@app.route('/profile/link-telegram', methods=['POST'])
@login_required
def link_telegram():
    """Привязка Telegram через код"""
    user = get_current_user()
    code = request.form.get('code', '').strip().upper()
    
    if not code or len(code) != 8:
        flash('Введите корректный 8-символьный код', 'error')
        return redirect(url_for('profile_page'))
    
    result = link_telegram_with_code(user['id'], code)
    
    if result['success']:
        flash(result['message'], 'success')
    else:
        flash(result['message'], 'error')
    
    return redirect(url_for('profile_page'))


@app.route('/profile/unlink-telegram', methods=['POST'])
@login_required
def unlink_telegram_route():
    """Отвязка Telegram"""
    user = get_current_user()
    result = unlink_telegram(user['id'])
    
    if result['success']:
        flash('Telegram успешно отвязан', 'success')
    else:
        flash('Ошибка при отвязке Telegram', 'error')
    
    return redirect(url_for('profile_page'))


@app.route('/api/favorites/<store_id>/<product_id>', methods=['POST', 'DELETE'])
def api_favorites(store_id, product_id):
    """API для управления избранным"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    
    if request.method == 'POST':
        result = add_to_favorites(user['id'], store_id, product_id)
        return jsonify(result)
    else:  # DELETE
        result = remove_from_favorites(user['id'], store_id, product_id)
        return jsonify(result)


@app.route('/api/favorites/check/<store_id>/<product_id>')
def api_check_favorite(store_id, product_id):
    """Проверить, в избранном ли товар"""
    user = get_current_user()
    if not user:
        return jsonify({'is_favorite': False, 'logged_in': False})
    
    return jsonify({
        'is_favorite': is_favorite(user['id'], store_id, product_id),
        'logged_in': True
    })


# ============================================================================
# УВЕДОМЛЕНИЯ О ЦЕНАХ
# ============================================================================

@app.route('/api/alerts/<store_id>/<product_id>', methods=['POST', 'DELETE'])
def api_alerts(store_id, product_id):
    """API для управления уведомлениями о ценах"""
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    
    if request.method == 'POST':
        target_price = request.json.get('target_price') if request.is_json else None
        result = add_price_alert(user['id'], store_id, product_id, target_price)
        return jsonify(result)
    else:  # DELETE
        result = remove_price_alert(user['id'], store_id, product_id)
        return jsonify(result)


@app.route('/api/alerts/check/<store_id>/<product_id>')
def api_check_alert(store_id, product_id):
    """Проверить, есть ли подписка на товар"""
    user = get_current_user()
    if not user:
        return jsonify({'has_alert': False, 'logged_in': False})
    
    return jsonify({
        'has_alert': has_price_alert(user['id'], store_id, product_id),
        'logged_in': True
    })


if __name__ == '__main__':
    for store_id in DATABASES:
        init_db(store_id)
    
    print("\n" + "="*50)
    print("  Сервер запущен: http://localhost:5000")
    print("="*50 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5000)
