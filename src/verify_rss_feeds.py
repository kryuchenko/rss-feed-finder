#!/usr/bin/env python
# -*- coding: utf-8 -*-

import requests
import feedparser
from datetime import datetime, timedelta
import csv
import time
from tqdm import tqdm
import concurrent.futures
import threading
import pytz

# ======= Параметры конфигурации =======
INPUT_CSV_FILE = "rss_feeds.csv"          # Файл с исходными RSS-фидами
OUTPUT_CSV_FILE = "verified_feeds.csv"    # Файл для сохранения проверенных фидов
HOURS_THRESHOLD = 48                      # Проверять новости за последние X часов
MAX_WORKERS = 6                           # Количество параллельных обработчиков
# =======================================

# Глобальные переменные для многопоточной работы
verified_feeds = []              # Список проверенных фидов: [(title, url, count), ...]
failed_feeds = []                # Список фидов, которые не удалось проверить
verified_feeds_lock = threading.Lock()    # Блокировка для безопасного обновления списков

# Цвета для вывода в консоль
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"
CHECK_MARK = "\u2714"
CROSS_MARK = "\u2718"

def check_feed_freshness(title, url):
    """
    Проверяет, содержит ли RSS-фид новости за последние HOURS_THRESHOLD часов.
    Возвращает кортеж (is_fresh, fresh_count, total_count, percent), где:
    - is_fresh: булево значение, True если есть свежие новости
    - fresh_count: количество свежих новостей
    - total_count: общее количество новостей в фиде
    - percent: процент свежих новостей от общего количества
    """
    try:
        # Получаем содержимое фида
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        
        # Используем feedparser для парсинга фида
        feed = feedparser.parse(response.content)
        
        # Определяем порог времени (текущее время минус HOURS_THRESHOLD часов)
        now = datetime.now(pytz.UTC)
        threshold = now - timedelta(hours=HOURS_THRESHOLD)
        
        # Счетчик свежих новостей
        fresh_news_count = 0
        total_entries = len(feed.entries)
        
        # Если фид пустой, возвращаем 0%
        if total_entries == 0:
            return (False, 0, 0, 0.0)
        
        # Проверяем каждую запись в фиде
        for entry in feed.entries:
            # Пытаемся получить дату публикации
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                # Преобразуем в datetime и добавляем часовой пояс UTC
                pub_date = datetime.fromtimestamp(time.mktime(entry.published_parsed), pytz.UTC)
            elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                pub_date = datetime.fromtimestamp(time.mktime(entry.updated_parsed), pytz.UTC)
            else:
                # Если дата не найдена, пропускаем запись
                continue
                
            # Если дата публикации новее порога, увеличиваем счетчик
            if pub_date > threshold:
                fresh_news_count += 1
        
        # Вычисляем процент свежих новостей
        if total_entries > 0:
            freshness_percent = (fresh_news_count / total_entries) * 100
        else:
            freshness_percent = 0.0
            
        return (fresh_news_count > 0, fresh_news_count, total_entries, freshness_percent)
    
    except Exception as e:
        # Если произошла ошибка, возвращаем (False, 0, 0, 0.0, error)
        return (False, 0, 0, 0.0, str(e))

def process_feed(feed_data):
    """
    Обрабатывает отдельный RSS-фид.
    """
    title, url = feed_data
    
    try:
        # Проверяем фид на свежесть
        result = check_feed_freshness(title, url)
        
        if len(result) == 4:
            is_fresh, fresh_count, total_count, percent = result
            error_msg = None
        else:
            is_fresh, fresh_count, total_count, percent, error_msg = result
        
        with verified_feeds_lock:
            if is_fresh:
                # Если фид содержит свежие новости, добавляем его в список проверенных
                verified_feeds.append((title, url, fresh_count, total_count, percent))
                print(f"{GREEN}{CHECK_MARK} {title} - {fresh_count}/{total_count} ({percent:.1f}%) свежих новостей{RESET}")
            else:
                if error_msg:
                    # Если произошла ошибка, добавляем фид в список неудачных
                    failed_feeds.append((title, url, error_msg))
                    print(f"{RED}{CROSS_MARK} {title} - ошибка: {error_msg}{RESET}")
                else:
                    # Если фид не содержит свежих новостей, добавляем его в список неудачных
                    failed_feeds.append((title, url, f"Нет свежих новостей (всего: {total_count})"))
                    print(f"{YELLOW}{CROSS_MARK} {title} - нет свежих новостей (всего: {total_count}){RESET}")
        
    except Exception as e:
        with verified_feeds_lock:
            failed_feeds.append((title, url, str(e)))
            print(f"{RED}{CROSS_MARK} {title} - ошибка: {str(e)}{RESET}")

def read_feeds_from_csv(file_path):
    """
    Читает RSS-фиды из CSV-файла.
    Возвращает список кортежей (title, url).
    """
    feeds = []
    try:
        with open(file_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)  # Пропускаем заголовок
            for row in reader:
                if len(row) >= 2:
                    title, url = row[0], row[1]
                    feeds.append((title, url))
    except Exception as e:
        print(f"Ошибка при чтении файла {file_path}: {e}")
    return feeds

def save_verified_feeds_to_csv(file_path, feeds):
    """
    Сохраняет проверенные RSS-фиды в CSV-файл.
    """
    try:
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Название', 'URL', 'Свежих новостей', 'Всего новостей', 'Процент свежих'])
            for title, url, fresh_count, total_count, percent in feeds:
                writer.writerow([title, url, fresh_count, total_count, f"{percent:.1f}%"])
        print(f"Проверенные фиды сохранены в файл: {file_path}")
    except Exception as e:
        print(f"Ошибка при сохранении файла {file_path}: {e}")

def save_failed_feeds_to_csv(file_path, feeds):
    """
    Сохраняет не прошедшие проверку RSS-фиды в CSV-файл.
    """
    try:
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Название', 'URL', 'Причина'])
            for title, url, reason in feeds:
                writer.writerow([title, url, reason])
        print(f"Неудачные фиды сохранены в файл: {file_path}")
    except Exception as e:
        print(f"Ошибка при сохранении файла {file_path}: {e}")

def main():
    print(f"Проверка RSS-фидов на наличие новостей за последние {HOURS_THRESHOLD} часов...")
    
    # Читаем фиды из CSV-файла
    feeds = read_feeds_from_csv(INPUT_CSV_FILE)
    if not feeds:
        print(f"Не удалось прочитать фиды из файла {INPUT_CSV_FILE}")
        return
    
    print(f"Загружено {len(feeds)} RSS-фидов из {INPUT_CSV_FILE}")
    print(f"Начинаем проверку с использованием {MAX_WORKERS} параллельных обработчиков...")
    
    start_time = time.time()
    
    # Используем ThreadPoolExecutor для параллельной обработки
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Показываем прогресс-бар
        list(tqdm(executor.map(process_feed, feeds), total=len(feeds), desc="Проверка фидов"))
    
    end_time = time.time()
    total_time = end_time - start_time
    
    # Сортируем проверенные фиды сначала по проценту свежих новостей, затем по количеству
    verified_feeds.sort(key=lambda x: (x[4], x[2]), reverse=True)
    
    # Сохраняем результаты в CSV-файлы
    save_verified_feeds_to_csv(OUTPUT_CSV_FILE, verified_feeds)
    save_failed_feeds_to_csv("failed_" + OUTPUT_CSV_FILE, failed_feeds)
    
    print(f"\nПроверка завершена за {total_time:.2f} секунд.")
    print(f"Проверено фидов: {len(feeds)}")
    print(f"Прошли проверку: {len(verified_feeds)} фидов")
    print(f"Не прошли проверку: {len(failed_feeds)} фидов")
    print(f"Результаты сохранены в:")
    print(f"  - {OUTPUT_CSV_FILE} (проверенные фиды)")
    print(f"  - failed_{OUTPUT_CSV_FILE} (неудачные фиды)")

if __name__ == "__main__":
    main()