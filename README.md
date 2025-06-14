# Поисковик RSS-фидов

Инструмент для автоматического поиска и проверки RSS-фидов на веб-сайтах.

## Описание

Этот проект представляет собой набор Python-скриптов для:
- Автоматического обхода веб-сайтов и поиска RSS-фидов
- Проверки актуальности найденных фидов
- Сохранения результатов в CSV-файлы

## Основные возможности

- 🔍 **Поиск RSS-фидов**: Автоматический обход сайта с заданной глубиной
- ✅ **Проверка актуальности**: Проверка наличия свежих новостей в фидах
- 🚀 **Многопоточность**: Параллельная обработка для ускорения работы
- 🛡️ **Фильтрация**: Блокировка нежелательных URL по ключевым словам
- 📊 **CSV-экспорт**: Сохранение результатов в удобном формате

## Структура проекта

```
rss_feed_finder/
├── src/
│   ├── rss_crawler.py      # Основной скрипт для поиска RSS-фидов
│   ├── verify_rss_feeds.py # Скрипт для проверки актуальности фидов
│   └── requirements.txt    # Зависимости Python
└── README.md
```

## Установка

1. Клонируйте репозиторий:
```bash
git clone https://github.com/ваш-username/rss-feed-finder.git
cd rss-feed-finder
```

2. Установите зависимости:
```bash
pip install -r src/requirements.txt
```

## Использование

### Поиск RSS-фидов

```bash
cd src
python rss_crawler.py
```

Настройки в начале файла `rss_crawler.py`:
- `START_URL` - начальный URL для обхода
- `MAX_DEPTH` - глубина обхода сайта
- `MAX_FEEDS` - максимальное количество RSS-ссылок
- `BLOCKED_WORDS` - список запрещенных слов в URL
- `WORKERS` - количество параллельных потоков

### Проверка актуальности фидов

```bash
cd src
python verify_rss_feeds.py
```

Настройки в начале файла `verify_rss_feeds.py`:
- `INPUT_CSV_FILE` - файл с исходными RSS-фидами
- `OUTPUT_CSV_FILE` - файл для сохранения проверенных фидов
- `HOURS_THRESHOLD` - проверять новости за последние X часов
- `MAX_WORKERS` - количество параллельных потоков

## Результаты

Скрипты создают CSV-файлы:
- `rss_feeds.csv` - все найденные RSS-фиды
- `verified_feeds.csv` - проверенные активные фиды
- `failed_verified_feeds.csv` - фиды, которые не прошли проверку

## Требования

- Python 3.6+
- Библиотеки из requirements.txt

## Лицензия

MIT