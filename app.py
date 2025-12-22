# -*- coding: utf-8 -*-
"""
Веб-приложение для просмотра товаров Пятёрочки и Магнита
"""

import sqlite3
import os
from flask import Flask, render_template, request, jsonify
from datetime import datetime

app = Flask(__name__)

# Базы данных
DATABASES = {
    '5ka': {'file': 'products.db', 'name': 'Пятёрочка', 'color': '#E30613'},
    'magnit': {'file': 'products_magnit.db', 'name': 'Магнит', 'color': '#E31E24'}
}


def get_db(store: str = '5ka'):
    """Получение соединения с БД"""
    db_file = DATABASES.get(store, DATABASES['5ka'])['file']
    if not os.path.exists(db_file):
        return None
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    return conn


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


def stem_russian(word: str) -> str:
    """Простой стемминг для русских слов - убираем окончания"""
    if len(word) < 4:
        return word
    # Убираем типичные окончания
    endings = ['ами', 'ями', 'ах', 'ях', 'ов', 'ев', 'ей', 'ий', 'ый', 'ая', 'яя', 'ое', 'ее',
               'ы', 'и', 'а', 'я', 'у', 'ю', 'е', 'о']
    for ending in endings:
        if word.endswith(ending) and len(word) - len(ending) >= 3:
            return word[:-len(ending)]
    return word

def get_similar_products(store_id: str, product_name: str, product_id: str, category: str = None, limit: int = 6):
    """Поиск похожих товаров по первому слову названия (типу продукта)"""
    conn = get_db(store_id)
    if not conn:
        return []
    
    import re
    
    # Стоп-слова (слишком общие, не определяют тип продукта)
    stop_words = {
        # Магазины и общие слова
        'магнит', 'пятёрочка', 'пятерочка', 'для', 'без', 'или', 'the', 'штук',
        'упаковка', 'пакет', 'бзмж', 'premium', 'extra', 'new', 'global', 'village',
        
        # Общие типы (слишком широкие)
        'напиток', 'продукт', 'изделие', 'товар', 'набор', 'ассорти', 'микс',
        'паста', 'крем', 'соус', 'масло',  # Общие типы - ищем по бренду
        
        # Прилагательные
        'добавлением', 'натуральный', 'свежий', 'вкусный', 'домашний', 'классический',
        'молочный', 'молочная', 'молочное', 'детский', 'детская', 'взрослый',
        'гавайский', 'тропический', 'летняя', 'летний', 'садовая', 'садовый',
        'лесная', 'лесной', 'красное', 'красный', 'белое', 'белый', 'зеленый', 'зелёный',
        'фасованное', 'фасованный', 'отборные', 'отборный', 'сокосодержащий',
        'восстановленный', 'протеиновый', 'протеиновое', 'высокобелковый',
        'энергетический', 'газированный', 'негазированный', 'безалкогольный'
    }
    
    # Извлекаем первое русское слово (тип продукта: бананы, молоко, колбаса)
    words = re.findall(r'[а-яА-ЯёЁ]{3,}', product_name.lower())
    words = [w for w in words if w not in stop_words]
    
    # Извлекаем бренды (латиница)
    brands = re.findall(r'\b[A-Za-z]{3,}\b', product_name)
    brands = [b.lower() for b in brands if b.lower() not in stop_words]
    
    # Ключевое слово для поиска
    # Приоритет: первое русское слово (продукт), потом бренд
    primary_word = words[0] if words else (brands[0] if brands else None)
    
    if not primary_word:
        conn.close()
        return []
    
    # Применяем стемминг для русских слов (лимоны -> лимон, мандарины -> мандарин)
    if re.match(r'^[а-яёА-ЯЁ]+$', primary_word):
        primary_word = stem_russian(primary_word)
    
    # Дополнительные слова для ранжирования
    extra_words = (words[1:3] if len(words) > 1 else []) + brands[:2]
    
    # Ранжируем по совпадению дополнительных слов
    relevance_parts = []
    relevance_params = []
    
    for word in extra_words:
        relevance_parts.append("(CASE WHEN LOWER(name) LIKE ? THEN 5 ELSE 0 END)")
        relevance_params.append(f"%{word}%")
    
    # Бонус за ту же категорию (если категория не акционная)
    if category and not category.startswith('«'):
        relevance_parts.append("(CASE WHEN category = ? THEN 3 ELSE 0 END)")
        relevance_params.append(category)
    
    relevance_sql = " + ".join(relevance_parts) if relevance_parts else "0"
    
    # Ищем товары с тем же первым словом
    query = f'''
        SELECT *, ({relevance_sql}) as relevance
        FROM products 
        WHERE LOWER(name) LIKE ? AND product_id != ?
        ORDER BY relevance DESC, current_price ASC
        LIMIT {limit}
    '''
    
    params = relevance_params + [f"%{primary_word}%", product_id]
    similar = conn.execute(query, params).fetchall()
    
    conn.close()
    return similar


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
    
    # Похожие товары из этого магазина (с учётом категории)
    product_category = product['category'] if product['category'] else None
    similar_same_store = get_similar_products(store_id, product['name'], product_id, product_category, limit=6)
    
    # Похожие товары из другого магазина
    other_store_id = 'magnit' if store_id == '5ka' else '5ka'
    similar_other_store = get_similar_products(other_store_id, product['name'], product_id, None, limit=6)
    
    return render_template('product.html', 
                           product=product, 
                           history=history,
                           store=DATABASES[store_id],
                           store_id=store_id,
                           similar_same_store=similar_same_store,
                           similar_other_store=similar_other_store,
                           other_store=DATABASES.get(other_store_id),
                           other_store_id=other_store_id)


@app.route('/api/stats')
def stats():
    """API для статистики"""
    return jsonify(get_all_stats())


if __name__ == '__main__':
    for store_id in DATABASES:
        init_db(store_id)
    
    print("\n" + "="*50)
    print("  Сервер запущен: http://localhost:5000")
    print("="*50 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5000)
