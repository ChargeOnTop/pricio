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
from flask import Flask, render_template, request, jsonify
from datetime import datetime

app = Flask(__name__)

# Базы данных
DATABASES = {
    '5ka': {'file': 'products.db', 'name': 'Пятёрочка', 'color': '#E30613'},
    'magnit': {'file': 'products_magnit.db', 'name': 'Магнит', 'color': '#E31E24'}
}


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
    
    # 1. Тип продукта (обязательно должен совпадать)
    if not attrs1.product_type or not attrs2.product_type:
        return 0
    
    if attrs1.product_type == attrs2.product_type:
        score += 30
    elif stem_russian(attrs1.product_type) == stem_russian(attrs2.product_type):
        score += 25  # Частичное совпадение через стемминг
    else:
        return 0  # Разные типы - не похожие товары
    
    # 2. Бренд (очень важно для сравнения цен!)
    if attrs1.brand and attrs2.brand:
        if attrs1.brand.lower() == attrs2.brand.lower():
            score += 40  # Тот же бренд - большой бонус
        else:
            score += 5   # Разные бренды - минимальный бонус
    elif attrs1.brand or attrs2.brand:
        score += 3  # У одного есть бренд, у другого нет
    
    # 3. Объём/вес (важно для корректного сравнения)
    if attrs1.volume_ml and attrs2.volume_ml:
        ratio = min(attrs1.volume_ml, attrs2.volume_ml) / max(attrs1.volume_ml, attrs2.volume_ml)
        if ratio > 0.95:  # Почти одинаковый объём (±5%)
            score += 15
        elif ratio > 0.8:  # Близкий объём
            score += 10
        elif ratio > 0.5:
            score += 5
    elif attrs1.weight_g and attrs2.weight_g:
        ratio = min(attrs1.weight_g, attrs2.weight_g) / max(attrs1.weight_g, attrs2.weight_g)
        if ratio > 0.95:
            score += 15
        elif ratio > 0.8:
            score += 10
        elif ratio > 0.5:
            score += 5
    
    # 4. Жирность (для молочки)
    if attrs1.fat_percent and attrs2.fat_percent:
        if abs(attrs1.fat_percent - attrs2.fat_percent) < 0.5:
            score += 10
        elif abs(attrs1.fat_percent - attrs2.fat_percent) < 1.5:
            score += 5
    
    # 5. Пересечение слов в названии (fuzzy matching)
    words1 = set(re.findall(r'[а-яёa-z]{3,}', name1.lower()))
    words2 = set(re.findall(r'[а-яёa-z]{3,}', name2.lower()))
    
    words1 -= STOP_WORDS
    words2 -= STOP_WORDS
    
    if words1 and words2:
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        if union > 0:
            jaccard = intersection / union
            score += int(jaccard * 10)  # До 10 баллов за совпадение слов
    
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
    
    if not source_attrs.product_type:
        conn.close()
        return []
    
    # Формируем поисковые запросы
    search_terms = []
    
    # 1. По типу продукта
    if source_attrs.product_type:
        stemmed = stem_russian(source_attrs.product_type)
        search_terms.append(f"%{stemmed}%")
        search_terms.append(f"%{source_attrs.product_type}%")
    
    # 2. По бренду
    if source_attrs.brand:
        search_terms.append(f"%{source_attrs.brand.lower()}%")
    
    # Собираем кандидатов
    candidates = []
    seen_ids = {product_id}  # Исключаем текущий товар
    
    for term in search_terms:
        query = '''
            SELECT * FROM products 
            WHERE LOWER(name) LIKE ? AND product_id NOT IN ({})
            LIMIT 50
        '''.format(','.join(['?'] * len(seen_ids)))
        
        params = [term] + list(seen_ids)
        rows = conn.execute(query, params).fetchall()
        
        for row in rows:
            if row['product_id'] not in seen_ids:
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
    return render_template('home.html', stores=stats)


@app.route('/store/<store_id>')
def store_products(store_id):
    """Страница товаров магазина"""
    if store_id not in DATABASES:
        return "Магазин не найден", 404
    
    conn = get_db(store_id)
    if not conn:
        return render_template('index.html',
                               products=[],
                               categories=[],
                               search='',
                               current_category='',
                               sort='last_updated',
                               order='desc',
                               page=1,
                               total_pages=0,
                               total=0,
                               store=DATABASES[store_id],
                               store_id=store_id)
    
    # Параметры
    search = request.args.get('search', '')
    category = request.args.get('category', '')
    sort = request.args.get('sort', 'last_updated')
    order = request.args.get('order', 'desc')
    page = int(request.args.get('page', 1))
    per_page = 50
    
    # Запрос
    query = "SELECT * FROM products WHERE 1=1"
    params = []
    
    if search:
        query += " AND name LIKE ?"
        params.append(f"%{search}%")
    
    if category:
        query += " AND category = ?"
        params.append(category)
    
    valid_sorts = ['name', 'current_price', 'last_updated', 'category', 'min_price', 'max_price', 'rating']
    if sort in valid_sorts:
        query += f" ORDER BY {sort} {'DESC' if order == 'desc' else 'ASC'}"
    
    query += f" LIMIT {per_page} OFFSET {(page - 1) * per_page}"
    
    products = conn.execute(query, params).fetchall()
    
    categories = conn.execute(
        "SELECT DISTINCT category FROM products WHERE category IS NOT NULL AND category != '' ORDER BY category"
    ).fetchall()
    
    count_query = "SELECT COUNT(*) FROM products WHERE 1=1"
    count_params = []
    if search:
        count_query += " AND name LIKE ?"
        count_params.append(f"%{search}%")
    if category:
        count_query += " AND category = ?"
        count_params.append(category)
    
    total = conn.execute(count_query, count_params).fetchone()[0]
    total_pages = (total + per_page - 1) // per_page
    
    conn.close()
    
    return render_template('index.html',
                           products=products,
                           categories=categories,
                           search=search,
                           current_category=category,
                           sort=sort,
                           order=order,
                           page=page,
                           total_pages=total_pages,
                           total=total,
                           store=DATABASES[store_id],
                           store_id=store_id)


@app.route('/store/<store_id>/product/<product_id>')
def product_detail(store_id, product_id):
    """Страница товара с историей цен и похожими товарами"""
    if store_id not in DATABASES:
        return "Магазин не найден", 404
    
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
    
    # Лучший аналог в другом магазине
    best_match = None
    if similar_other_store:
        best = similar_other_store[0]
        if best.get('is_exact_match') or best.get('similarity_score', 0) >= 50:
            best_match = {
                'product': best,
                'savings': current_price - (best.get('current_price', 0) or 0),
                'savings_percent': ((current_price - (best.get('current_price', 0) or 0)) / current_price * 100) if current_price else 0
            }
    
    return render_template('product.html', 
                           product=product, 
                           history=history,
                           store=DATABASES[store_id],
                           store_id=store_id,
                           similar_same_store=similar_same_store,
                           similar_other_store=similar_other_store,
                           other_store=DATABASES.get(other_store_id),
                           other_store_id=other_store_id,
                           product_attrs=product_attrs,
                           price_per_unit=price_per_unit,
                           best_match=best_match)


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


if __name__ == '__main__':
    for store_id in DATABASES:
        init_db(store_id)
    
    print("\n" + "="*50)
    print("  Сервер запущен: http://localhost:5000")
    print("="*50 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5000)
