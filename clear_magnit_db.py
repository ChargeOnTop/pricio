# -*- coding: utf-8 -*-
import os

db_file = 'products_magnit.db'
if os.path.exists(db_file):
    os.remove(db_file)
    print(f"[OK] БД Магнита удалена: {db_file}")
else:
    print(f"[OK] БД Магнита не существует (уже чистая)")



