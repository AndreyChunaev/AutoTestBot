## Установить

- Python 3.10+

## Настройка

1. Задать адрес страницы:
   - Скопировать `.env.example` в `.env`
   - В `.env` указать: `EB_BASE_URL=https://...` (полный URL страницы для входа) и директорию загрузок браузера `BROWSER_DOWNLOADS_DIR`
   - Либо задать переменную окружения `EB_BASE_URL` в системе/терминале


## Запуск

python eb_robot.py

(предварительно: `pip install -r requirements.txt` или активировать venv и установить зависимости)


## Папки с файлами

- `BROWSER_DOWNLOADS_DIR` — папка, где браузер сохраняет файлы
- Excel outputs — сохранённые Excel-файлы
- TXT Outputs — распакованные TXT из ZIP
- Correct Outputs — корректные TXT файлы
- Incorrect outputs — некорректные TXT файлы

## Запуск контроля документов

python controls.py

(предварительно: `pip install -r requirements.txt` или активировать venv и установить зависимости)

