# 🚂 Railway Deployment Guide (Step-by-Step)

## Что такое Railway?
Railway — это облачный хостинг который даёт:
- ✅ Бесплатный HTTPS домен (вида `yourapp.up.railway.app`)
- ✅ Автодеплой из GitHub
- ✅ Бесплатная PostgreSQL база данных
- ✅ Простой интерфейс

---

## 📋 Пошаговая инструкция

### Шаг 1: Подготовка (5 минут)

**1.1** Зайди на https://railway.app и нажми **"Get Started"**

**1.2** Выбери способ входа:
- Нажми **"Continue with GitHub"** (рекомендую)
- Или "Continue with Google"

**1.3** Дай Railway доступ к GitHub:
- Нажми **"Authorize railwayapp"**
- Введи пароль GitHub если спросит

---

### Шаг 2: Создание проекта (3 минуты)

**2.1** На dashboard нажми зелёную кнопку **"+ New"**

**2.2** Выбери **"Deploy from GitHub repo"**

**2.3** Найди свой репозиторий:
- В поле поиска начни печатать имя: `PokerHubs`
- Кликни на него когда появится
- Нажми **"Add Variables"** (переменные окружения)

---

### Шаг 3: Добавление переменных (ВАЖНО!)

Нажми **"New Variable"** и добавляй по очереди:

| Переменная | Значение | Пояснение |
|------------|----------|-----------|
| `POKER_BOT_TOKEN` | `123456789:ABC...` | Токен от @BotFather |
| `POKER_ADMIN_IDS` | `123456789` | Твой Telegram ID |
| `KASPI_PHONE_NUMBER` | `+77071234567` | Номер для платежей |
| `USE_WEBHOOK` | `true` | Включаем webhook |
| `WEBHOOK_URL` | `https://yourproject.up.railway.app/webhook` | URL будет после деплоя |
| `WEBHOOK_PORT` | `8080` | Порт внутри Railway |
| `POKER_SUPPORT_USERNAME` | `yourusername` | Твой юзернейм (без @) |

**Как узнать WEBHOOK_URL?**
1. Пока оставь пустым или напиши любой
2. После первого деплоя Railway даст домен
3. Верись и исправь на правильный

---

### Шаг 4: Деплой (2 минуты)

**4.1** Нажми **"Deploy"** внизу страницы

**4.2** Жди пока появится зелёная галочка (✅ Deployed)

**4.3** Кликни на вкладку **"Deployments"** сверху

**4.4** Найди твой деплой и кликни на него

**4.5** Вверху увидешь URL типа:
```
https://pokerhubs-production.up.railway.app
```

**4.6** Скопируй этот URL и добавь `/webhook`:
```
https://pokerhubs-production.up.railway.app/webhook
```

---

### Шаг 5: Исправление WEBHOOK_URL

**5.1** Верись на вкладку **"Variables"**

**5.2** Найди `WEBHOOK_URL`

**5.3** Нажми на него → **"Edit"**

**5.4** Вставь правильный URL:
```
https://pokerhubs-production.up.railway.app/webhook
```

**5.5** Нажми **"Save"**

**5.6** Railway автоматически перезапустит бота

---

### Шаг 6: Проверка (1 минута)

**6.1** Открой URL в браузере:
```
https://pokerhubs-production.up.railway.app
```

Должно показать:
```json
{
  "name": "PokerHubs Bot",
  "status": "running"
}
```

**6.2** Проверь health endpoint:
```
https://pokerhubs-production.up.railway.app/health
```

**6.3** Напиши боту в Telegram → он должен ответить!

---

### Шаг 7: Логи (если что-то не работает)

**7.1** На dashboard кликни на деплой

**7.2** Нажми вкладку **"Logs"**

**7.3** Ищи ошибки (красным)

**7.4** Если видишь:
```
Webhook URL must be HTTPS
```
→ Проверь что WEBHOOK_URL начинается с `https://`

---

## 🔄 Обновление бота (после изменений)

Просто сделай push в GitHub:
```bash
git add .
git commit -m "Обновление"
git push
```

Railway автоматически увидит изменения и перезапустит бота (约30 секунд)

---

## 💰 Бесплатный лимит Railway

| Лимит | Значение |
|-------|----------|
| Execution time | 500 часов/месяц |
| RAM | 512 MB |
| Disk | 1 GB |
| Трафик | Бесплатно |

**Для покерного бота:** 500 часов = ~20 дней работы

**Что делать когда закончится:**
- Railway предложит подписку ($5/месяц)
- Или создай новый аккаунт
- Или переходи на VPS (DigitalOcean, Hetzner)

---

## 🆘 Частые ошибки

### "Invalid Webhook URL"
- Проверь что URL начинается с `https://`
- Проверь что заканчивается на `/webhook`
- Не используй `http://` (только HTTPS)

### "Conflict: can't use getUpdates method while webhook is active"
- Это значит webhook уже установлен
- Используй `/admin restart` или подожди минуту

### Бот не отвечает
1. Проверь логи (вкладка Logs)
2. Убедись что `POKER_BOT_TOKEN` правильный
3. Проверь что webhook URL правильный

---

## 📱 Горячие клавиши Railway

| Действие | Где найти |
|----------|-----------|
| Перезапуск | Deployments → ⋮ → "Redeploy" |
| Логи | Deployments → клик на деплой → Logs |
| Переменные | Variables → "New Variable" |
| База данных | New → Database → Add PostgreSQL |

---

## ✅ Чеклист перед запуском

- [ ] Зарегистрировался на Railway
- [ ] Подключил GitHub
- [ ] Создал проект из репозитория
- [ ] Добавил POKER_BOT_TOKEN
- [ ] Добавил USE_WEBHOOK=true
- [ ] Сделал первый деплой
- [ ] Получил домен .up.railway.app
- [ ] Обновил WEBHOOK_URL
- [ ] Проверил что бот отвечает
