# -*- coding: utf-8 -*-

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

# Тест
test_words = ['лимоны', 'мандарины', 'бананы', 'яблоки', 'апельсины', 'колбаса', 'молоко']
print("Тест стемминга:")
for word in test_words:
    print(f"  {word} -> {stem_russian(word)}")



