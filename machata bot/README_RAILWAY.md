# 🚂 Быстрый старт: Деплой на Railway

## 🎯 За 5 минут до запуска

### 1. Закоммитьте файлы в GitHub
```bash
git add requirements.txt Procfile .gitignore runtime.txt machata_bot.py RAILWAY_ДЕПЛОЙ.md
git commit -m "Готово для Railway"
git push origin main
```

### 2. Создайте проект на Railway
1. Зайдите на [railway.com](https://railway.com/)
2. **New Project** → **Deploy from GitHub repo**
3. Выберите `lutifer/machata-bot`
4. Railway автоматически начнет деплой

### 3. Добавьте переменные окружения
В Railway → **Variables**:
```
API_TOKEN=7334437140:AAG8GYbJFcwFFj4YfpGsFKrLYBO6VlbWkRE
YOOKASSA_SHOP_ID=1231094
YOOKASSA_SECRET_KEY=live_G7u2yfiQfxt-YSwsPwG3iJsAyBz4sVENqfqvGQVosME
PORT=10000
```

### 4. Создайте публичный домен
Railway → **Networking** → **Generate Domain**

### 5. Настройте Webhook ЮKassa
В ЛК ЮKassa добавьте: `https://ваш-домен-railway.app/payment`

## ✅ Готово!

Подробная инструкция: см. `RAILWAY_ДЕПЛОЙ.md`

