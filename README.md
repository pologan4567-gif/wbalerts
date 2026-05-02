# 📊 WB Analytics

Автоматическая выгрузка отчётов Wildberries с отправкой в Telegram.  
Работает через GitHub Actions — **полностью бесплатно**, сервер не нужен.

---

## 🗂 Структура проекта

```
wb-analytics/
├── wb_weekly_puller.py          ← основной скрипт выгрузки
├── notifier.py                  ← отправка отчёта в Telegram
├── .env.example                 ← шаблон переменных окружения
├── .gitignore
├── README.md
└── .github/
    └── workflows/
        ├── weekly.yml           ← автозапуск каждый понедельник 09:00 МСК
        └── custom_period.yml    ← ручной запуск за любой период
```

---

## ⚙️ Установка

### 1. Клонировать репозиторий

```bash
git clone https://github.com/ВАШ_ЛОГИН/wb-analytics.git
cd wb-analytics
pip install requests pandas openpyxl python-dotenv
```

### 2. Создать .env файл

```bash
cp .env.example .env
# Открыть .env и вставить свои токены
```

Содержимое `.env`:
```
WB_API_TOKEN=токен_статистики_WB
WB_ADV_TOKEN=токен_рекламного_API_WB
TG_BOT_TOKEN=токен_от_BotFather
TG_CHAT_ID=ваш_chat_id
```

> **Как получить TG_CHAT_ID:** напишите боту [@userinfobot](https://t.me/userinfobot) — он ответит вашим chat_id.

### 3. Запустить локально

```bash
python wb_weekly_puller.py              # прошлая неделя
python wb_weekly_puller.py --compare    # с сравнением
python wb_weekly_puller.py --month      # текущий месяц
python wb_weekly_puller.py --from 2026-04-01 --to 2026-04-20
```

---

## 🤖 Автозапуск через GitHub Actions

### Добавить секреты в репозиторий

**Settings → Secrets and variables → Actions → New repository secret**

| Название секрета | Значение |
|---|---|
| `WB_API_TOKEN` | Токен статистики WB |
| `WB_ADV_TOKEN` | Токен рекламного API WB |
| `TG_BOT_TOKEN` | Токен Telegram-бота от @BotFather |
| `TG_CHAT_ID`   | Ваш Telegram chat_id |

### Расписание

- `weekly.yml` — **каждый понедельник в 09:00 МСК** (06:00 UTC)
- Ручной запуск: **Actions → WB Weekly Report → Run workflow**
- Запуск за кастомный период: **Actions → WB Custom Period Report → Run workflow**

---

## 📱 Пример Telegram-сообщения

```
📊 WB Неделя · 25.04 → 01.05

💰 Финансы
  Выручка:       84 300.00 ₽ (+12%) 📈
  Продано:       47 шт (+8%) 📈
  К выплате WB:  31 200.00 ₽

📉 Расходы
  Логистика:     4 100.00 ₽
  Хранение:      890.00 ₽
  Налог УСН 6%:  5 058.00 ₽
  Реклама WB:    6 200.00 ₽
  ДРР:           7.4% 🟢

✅ Итог
  Чистая прибыль:  21 500.00 ₽ (+5%) 📈
  После рекламы:   15 300.00 ₽

📦 По артикулам
  🟢 т1    — 35 шт · 16 200.00 ₽
  🟢 131с  — 12 шт · 5 300.00 ₽
```

---

## 💡 Подключение Telegram в скрипт

В конце функции `main()` в `wb_weekly_puller.py` добавить:

```python
from notifier import notify
notify(current_meta, prev_meta if compare else None, mode)
```

---

## 📈 Дальнейшее развитие (Фаза 2+)

- [ ] Ежедневная проверка остатков (`wb_stocks.py`)
- [ ] Детальная аналитика рекламы (`wb_adv.py`)
- [ ] SQLite-история всех отчётов (`db.py`)
- [ ] Интерактивный бот с командами `/week`, `/month`, `/stocks`
