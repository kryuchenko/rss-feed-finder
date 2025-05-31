import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from urllib.parse import urljoin, urlparse
import warnings
import time
import concurrent.futures
import queue
import threading
import csv
import os
import signal

# ======= Параметры конфигурации =======
START_URL = "https://www.lne.es"  # Задайте здесь нужный URL
MAX_DEPTH = 2                     # Глубина обхода сайта (можете изменить по необходимости)
MAX_FEEDS = 200                   # Максимальное количество RSS-ссылок
BLOCKED_WORDS = ["tag"]          # Список запрещенных слов в URL (например, ["tag", "category"])
WORKERS = 6                      # Количество параллельных обработчиков
CSV_FILE = "rss_feeds.csv"       # Имя файла для сохранения результатов
# =======================================

# Отключаем предупреждения по использованию HTML-парсера для XML, если возникнут
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

GREEN = "\033[92m"
RESET = "\033[0m"
CHECK_MARK = "\u2714"

# Глобальные переменные для многопоточной работы
FOUND_FEEDS = []  # Список найденных фидов: [(title, url), ...]
url_queue = queue.Queue()   # Очередь URL для обработки
visited = set()             # Множество посещенных URL
found_feed_urls = set()     # Множество URL найденных фидов для проверки дубликатов
skipped_duplicates = 0      # Счетчик пропущенных дубликатов
found_feeds_lock = threading.Lock()  # Блокировка для безопасного обновления FOUND_FEEDS
visited_lock = threading.Lock()      # Блокировка для безопасного обновления visited
print_lock = threading.Lock()        # Блокировка для безопасного вывода в консоль
exit_flag = threading.Event()        # Флаг для сигнала о завершении работы всем потокам

def is_url_blocked(url):
    """
    Проверяет, содержит ли URL запрещенные слова из списка BLOCKED_WORDS
    """
    if not BLOCKED_WORDS:  # Если список пуст, ничего не блокируем
        return False
    
    for word in BLOCKED_WORDS:
        if word.lower() in url.lower():
            print(f"URL проигнорирован (содержит '{word}'): {url}")
            return True
    return False

def is_rss_content(content):
    """
    Простейшая проверка: если контент начинается с XML-пролога и содержит тег <rss>.
    """
    return content.strip().startswith("<?xml") and "<rss" in content

def extract_feed_title(content):
    """
    Извлекает название фида из RSS-содержимого.
    """
    try:
        soup = BeautifulSoup(content, "xml")
        # Пробуем получить название из тега <title> внутри <channel>
        channel_title = soup.find("channel").find("title")
        if channel_title:
            return channel_title.text.strip()
        return "Без названия"
    except Exception:
        # Если не удалось извлечь название, возвращаем заглушку
        return "Без названия"

def check_rss(url):
    """
    Пытается получить контент по URL и определить, является ли он RSS-фидом.
    Если да – извлекает название и добавляет в список найденных фидов.
    Пропускает дубликаты URL.
    """
    global skipped_duplicates
    
    # Проверяем, не содержит ли URL запрещенных слов
    if is_url_blocked(url):
        return False
    
    # Проверяем, нужно ли завершать работу
    if exit_flag.is_set():
        return False
    
    # Проверяем, не обрабатывали ли мы уже этот URL фида
    with found_feeds_lock:
        if url in found_feed_urls:
            # Увеличиваем счетчик пропущенных дубликатов
            skipped_duplicates += 1
            return False
        
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        content = response.text.strip()
        if is_rss_content(content):
            # Извлекаем название фида
            title = extract_feed_title(content)
            
            with found_feeds_lock:
                # Еще раз проверяем, нет ли уже такого URL (на случай гонки условий)
                if url in found_feed_urls:
                    # Увеличиваем счетчик пропущенных дубликатов
                    skipped_duplicates += 1
                    return False
                    
                if len(FOUND_FEEDS) >= MAX_FEEDS:
                    with print_lock:
                        print(f"{GREEN}Достигнуто ограничение в {MAX_FEEDS} RSS-фидов. Завершаем.{RESET}")
                    # Устанавливаем флаг выхода, чтобы остальные потоки знали, что надо завершаться
                    exit_flag.set()
                    return True
                
                # Добавляем URL в множество найденных фидов
                found_feed_urls.add(url)
                # Добавляем пару (название, URL) в список результатов
                FOUND_FEEDS.append((title, url))
                
            with print_lock:
                print(f"{GREEN}{CHECK_MARK} RSS фид найден: {title} - {url}{RESET}")
            return True
    except Exception as e:
        # Можно раскомментировать следующую строку для отладки ошибок
        # with print_lock:
        #     print(f"Ошибка при проверке {url}: {e}")
        pass
    return False

def process_url(url_depth_pair):
    """
    Обрабатывает URL, извлекает ссылки и проверяет на RSS.
    Эта функция будет запускаться в отдельных воркерах.
    """
    # Проверяем, не нужно ли завершаться
    if exit_flag.is_set():
        return
        
    url, depth, domain = url_depth_pair
    
    # Проверяем глубину и количество найденных фидов
    with found_feeds_lock:
        if len(FOUND_FEEDS) >= MAX_FEEDS:
            exit_flag.set()
            return
    
    if depth < 0:
        return
        
    # Проверяем был ли URL уже посещен
    with visited_lock:
        if url in visited:
            return
        visited.add(url)
    
    # Проверяем, не содержит ли URL запрещенных слов
    if is_url_blocked(url):
        return
    
    with print_lock:
        print(f"Обход: {url} (глубина: {depth})")
    
    try:
        # Еще раз проверяем флаг выхода перед запросом
        if exit_flag.is_set():
            return
            
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        content = response.text
        content_type = response.headers.get("Content-Type", "")
    except Exception as e:
        # Если страницу получить не удалось, пропускаем её
        # with print_lock:
        #     print(f"Ошибка получения {url}: {e}")
        return

    # Если нужно завершаться, не продолжаем обработку
    if exit_flag.is_set():
        return
        
    # Если страница сама выглядит как RSS
    if "application/rss+xml" in content_type or "application/xml" in content_type or is_rss_content(content):
        check_rss(url)
        return

    # Если страница является HTML, ищем в ней потенциальные ссылки на фид
    if "text/html" in content_type and not exit_flag.is_set():
        soup = BeautifulSoup(content, "html.parser")

        # 1. Проверяем <link> теги в <head>
        link_tags = soup.find_all("link", {"type": "application/rss+xml"})
        for tag in link_tags:
            if exit_flag.is_set():
                return
                
            href = tag.get("href")
            if href:
                rss_url = urljoin(url, href)
                check_rss(rss_url)

        # 2. Ищем все ссылки <a> и добавляем их в очередь для обработки
        a_tags = soup.find_all("a")
        for a in a_tags:
            if exit_flag.is_set():
                return
                
            href = a.get("href")
            if not href:
                continue
            full_url = urljoin(url, href)
            parsed = urlparse(full_url)
            # Ограничиваемся ссылками внутри того же домена
            if domain not in parsed.netloc:
                continue

            # Если в URL присутствуют ключевые слова "feed" или "rss", проверяем сразу
            if "feed" in full_url.lower() or "rss" in full_url.lower():
                check_rss(full_url)

            # Добавляем URL в очередь для дальнейшей обработки, если не надо завершаться
            if not exit_flag.is_set():
                url_queue.put((full_url, depth - 1, domain))

def worker():
    """
    Функция воркера, которая обрабатывает URL из очереди.
    """
    while not exit_flag.is_set():
        try:
            # Получаем URL из очереди с таймаутом
            url_depth_pair = url_queue.get(timeout=1)
            
            # Проверяем, не установлен ли флаг выхода
            if exit_flag.is_set():
                url_queue.task_done()
                break
                
            process_url(url_depth_pair)
            url_queue.task_done()
            
            # Небольшая задержка, чтобы не перегружать сервер
            time.sleep(0.1)
            
        except queue.Empty:
            # Проверяем, не пуста ли очередь и не установлен ли флаг выхода
            if url_queue.empty() or exit_flag.is_set():
                break
        except Exception as e:
            with print_lock:
                print(f"Ошибка в воркере: {e}")
            url_queue.task_done()

def save_to_csv(feeds, csv_file):
    """
    Сохраняет найденные RSS-фиды в CSV файл с двумя колонками: название и URL.
    """
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Название', 'URL'])
        for title, url in feeds:
            writer.writerow([title, url])
    
    with print_lock:
        print(f"Результаты сохранены в файл: {csv_file}")
        print(f"Всего уникальных RSS-фидов: {len(feeds)}")

def crawl_for_rss(start_url, domain, max_depth):
    """
    Запускает обход сайта с использованием пула воркеров.
    """
    # Сбрасываем флаг выхода перед началом работы
    exit_flag.clear()
    
    # Добавляем начальный URL в очередь
    url_queue.put((start_url, max_depth, domain))
    
    # Создаем и запускаем воркеры
    workers = []
    for _ in range(WORKERS):
        t = threading.Thread(target=worker)
        t.daemon = True  # Потоки будут автоматически завершены при выходе из основной программы
        t.start()
        workers.append(t)
    
    try:
        # Ждем завершения обработки очереди или прерывания
        while not exit_flag.is_set():
            # Если очередь пуста и все задачи выполнены, выходим из цикла
            if url_queue.empty() and url_queue.unfinished_tasks == 0:
                break
            time.sleep(0.5)
        
        # Если дошли сюда, значит либо достигли лимита, либо обработали все URL
        # В любом случае устанавливаем флаг выхода, чтобы все потоки завершились
        exit_flag.set()
        
        # Короткая задержка, чтобы потоки успели заметить флаг выхода
        time.sleep(1)
        
    except KeyboardInterrupt:
        with print_lock:
            print("\nПрерывание выполнения пользователем.")
        exit_flag.set()
        
    finally:
        # Ожидаем завершения всех рабочих потоков (с таймаутом)
        for t in workers:
            t.join(1)
        
        # Если были найдены фиды, сохраняем их в CSV
        if FOUND_FEEDS:
            save_to_csv(FOUND_FEEDS, CSV_FILE)

if __name__ == '__main__':
    # Обработчик сигнала SIGINT (Ctrl+C)
    def signal_handler(sig, frame):
        print("\nПолучен сигнал прерывания. Завершение работы...")
        exit_flag.set()
        time.sleep(2)  # Даем время на корректное завершение
    
    # Установка обработчика сигнала
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        print(f"Запуск обхода сайта с {WORKERS} параллельными воркерами...")
        print(f"Максимальное количество RSS-фидов: {MAX_FEEDS}")
        print(f"Результаты будут сохранены в файл: {CSV_FILE}")
        
        if BLOCKED_WORDS:
            print(f"Игнорируются URL, содержащие: {', '.join(BLOCKED_WORDS)}")
        
        parsed_start = urlparse(START_URL)
        domain = parsed_start.netloc
        
        # Запускаем обход с пулом воркеров
        start_time = time.time()
        crawl_for_rss(START_URL, domain, MAX_DEPTH)
        end_time = time.time()
        
        total_time = end_time - start_time
        with print_lock:
            print(f"\nОбход завершен за {total_time:.2f} секунд.")
            print(f"Проверено URL: {len(visited)}")
            print(f"Найдено уникальных RSS-фидов: {len(FOUND_FEEDS)}")
            print(f"Пропущено дубликатов RSS-фидов: {skipped_duplicates}")
            print(f"Результаты сохранены в {CSV_FILE}")
        
    except Exception as e:
        print(f"Ошибка: {e}")
        # В случае ошибки всё равно пытаемся сохранить то, что нашли
        if FOUND_FEEDS:
            save_to_csv(FOUND_FEEDS, CSV_FILE)
