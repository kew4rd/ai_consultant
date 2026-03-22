# AI-консультант — Django + LoRA-адаптеры

Чат-приложение с тремя специализированными AI-экспертами на базе модели **Qwen3.5-4B** с LoRA-адаптерами. Пользователь может общаться с одним экспертом или включить нескольких одновременно — модель автоматически объединяет их в гибридный режим.

---

## Эксперты

| Эксперт | Специализация |
|---|---|
| 💼 **Бизнес-консультант** | Стратегия, масштабирование, юнит-экономика, управление |
| ⚖️ **Юридический консультант** | Договоры, риски, нормы права, защита интересов |
| 🧠 **Предпринимательский психолог** | Стресс, выгорание, мотивация, командная динамика |

Любую комбинацию из трёх адаптеров можно активировать одновременно. В гибридном режиме модель даёт единый согласованный ответ с учётом всех выбранных ролей.

---

## Архитектура

```
Браузер → Django (порт 8000) → Flask LLM-сервер (порт 5000)
                                    ↓
                             Qwen3.5-4B + LoRA-адаптеры
```

- **Django** — веб-интерфейс, авторизация, хранение диалогов, учёт токенов
- **Flask** (`colab_server.ipynb`) — загрузка модели, генерация, стриминг ответов
- **SSE-стриминг** — ответ отображается посимвольно в реальном времени
- **SQLite** — хранение пользователей, диалогов и сообщений

---

## Требования

### Django-приложение
- Python 3.10+
- Зависимости: `Django`, `requests`, `python-dotenv` (см. `requirements.txt`)

### LLM-сервер (ноутбук)
- GPU с 8+ ГБ VRAM (рекомендуется RTX 3070 и выше)
- Google Colab / Kaggle (с GPU) **или** локальный запуск через Jupyter
- Модель загружается автоматически с HuggingFace (~8 ГБ)

---

## Быстрый старт

### Шаг 1 — Клонирование репозитория

```bash
git clone https://github.com/Zhuzhik365/chat_bot_3adapters_dynamic_hybrid
cd chat_bot_3adapters_dynamic_hybrid
```

### Шаг 2 — Настройка окружения Django

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

**Linux / macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Шаг 3 — Создание `.env`

Скопируй шаблон и заполни:

```bash
cp .env.example .env   # Linux / macOS
copy .env.example .env  # Windows
```

Минимальная конфигурация:

```env
DJANGO_SECRET_KEY=your-secret-key
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
MODEL_API_URL=https://your-ngrok-url/generate
MODEL_API_TOKEN=
```

Сгенерировать `DJANGO_SECRET_KEY`:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Описание переменных:

| Переменная | Назначение |
|---|---|
| `DJANGO_SECRET_KEY` | Секретный ключ Django (обязательно) |
| `DJANGO_DEBUG` | Режим отладки (`True` / `False`) |
| `DJANGO_ALLOWED_HOSTS` | Разрешённые хосты через запятую |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Нужен при работе через внешний домен |
| `MODEL_API_URL` | URL Flask-сервера с `/generate` на конце |
| `MODEL_API_TOKEN` | Общий секрет между Django и ноутбуком (необязательно) |

### Шаг 4 — Запуск LLM-сервера

Открой `colab_server.ipynb` и выполни все ячейки по порядку.

#### Вариант A: Google Colab / Kaggle (рекомендуется)

1. Загрузи ноутбук в Colab или Kaggle
2. Включи GPU-ускоритель
3. Добавь секреты через встроенный менеджер:
   - Colab: панель слева → иконка ключа 🔑 → **Secrets**
   - Kaggle: **Add-ons → Secrets**

   | Секрет | Описание |
   |---|---|
   | `NGROK_AUTH_TOKEN` | Токен с [dashboard.ngrok.com](https://dashboard.ngrok.com) |
   | `MODEL_API_TOKEN` | Тот же токен что в `.env` (необязательно) |
   | `HUGGINGFACE_TOKEN` | Нужен только для приватных моделей |

4. Запусти все ячейки — в конце появится ngrok URL вида `https://xxxx.ngrok-free.app`
5. Скопируй URL и вставь в `.env` как `MODEL_API_URL=https://xxxx.ngrok-free.app/generate`

#### Вариант B: Локальный запуск (RTX 8+ ГБ)

Замени последнюю ячейку ноутбука на:

```python
app.run(host="0.0.0.0", port=5000, threaded=False)
```

Установи зависимости ноутбука и запусти:

```bash
pip install jupyter transformers peft accelerate flask pyngrok sentencepiece
jupyter notebook colab_server.ipynb
```

В `.env` укажи:

```env
MODEL_API_URL=http://127.0.0.1:5000/generate
```

### Шаг 5 — Запуск Django

```bash
python manage.py migrate
python manage.py runserver
```

Открывай **http://127.0.0.1:8000**, регистрируйся и начинай общение.

> **Важно:** LLM-сервер должен быть запущен до первого сообщения в чате.

---

## Лимиты токенов

| План | Токенов в день | Токенов на ответ |
|---|---|---|
| Free | 10 000 | 1 000 |
| Premium | 100 000 | 1 000 |

Счётчик обнуляется каждый день в полночь. Если ответ модели был обрезан из-за лимита длины — под сообщением появится предупреждение.

---

## Структура проекта

```
chat_bot_3adapters_dynamic_hybrid/
├── adapters/
│   ├── business_adapter/   # LoRA-веса для бизнес-консультанта
│   ├── laws_adapter/       # LoRA-веса для юридического консультанта
│   └── psych_adapter/      # LoRA-веса для психолога
├── chat/
│   ├── migrations/
│   ├── static/chat/
│   │   ├── css/style.css
│   │   └── js/chat.js      # Логика чата и SSE-стриминг
│   ├── templates/chat/     # HTML-шаблоны
│   ├── models.py           # UserProfile, Conversation, Message
│   ├── views.py            # Django-вью, включая /stream/ эндпоинт
│   └── urls.py
├── chatbot_project/
│   ├── settings.py
│   └── urls.py
├── colab_server.ipynb      # Flask LLM-сервер с /generate и /generate_stream
├── requirements.txt        # Зависимости Django-приложения
├── .env.example
└── manage.py
```

---

## API Flask-сервера

| Метод | Эндпоинт | Описание |
|---|---|---|
| POST | `/generate` | Синхронная генерация (весь ответ одним JSON) |
| POST | `/generate_stream` | Стриминг токенов через SSE |
| GET | `/health` | Статус сервера и список адаптеров |
| GET | `/` | Базовая информация об API |

Формат запроса к `/generate` и `/generate_stream`:

```json
{
  "message": "Как открыть ООО?",
  "history": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}],
  "consultant": "legal",
  "adapters": ["legal"]
}
```

Опциональная авторизация: заголовок `X-Model-Api-Key: <MODEL_API_TOKEN>`.
