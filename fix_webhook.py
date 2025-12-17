import os
import requests

# Получаем токен из переменной окружения
BOT_TOKEN = os.getenv('BOT_TOKEN')

if not BOT_TOKEN:
    print('ERROR: BOT_TOKEN not found in environment variables')
    exit(1)

print('Checking webhook status...')

# Проверяем текущий статус webhook
response = requests.get(f'https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo')
webhook_info = response.json()
print(f'Current webhook info: {webhook_info}')

if webhook_info.get('result', {}).get('url'):
    print(f"\nWebhook is SET: {webhook_info['result']['url']}")
    print('Deleting webhook...')
    
    # Удаляем webhook
    delete_response = requests.post(
        f'https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook',
        params={'drop_pending_updates': True}
    )
    print(f'Delete webhook response: {delete_response.json()}')
    
    # Проверяем снова
    check_response = requests.get(f'https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo')
    print(f'Webhook after delete: {check_response.json()}')
    print('\n✅ Webhook deleted successfully!')
else:
    print('\nWebhook is NOT set. Bot should work with polling.')

print('\nDone!')
