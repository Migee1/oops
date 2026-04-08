import asyncio
import logging
from typing import Dict, Optional
from datetime import datetime

from config import FUNPAY_ACCOUNTS
from db import Database
from steam_utils import SteamUtils
from funpay_client import FunPayClient_e

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class FunPaySteamBot:
    def __init__(self):
        self.db = Database()
        self.clients: Dict[str, FunPayClient] = {}
        self.steam_utils = SteamUtils()

    async def start(self):
        """Запуск бота"""
        # Подключаем БД
        await self.db.connect()
        logger.info("✅ База данных подключена")
        
        # Создаем клиентов для каждого FunPay аккаунта
        for suffix, credentials in FUNPAY_ACCOUNTS.items():
            client = FunPayClient(
                suffix=suffix,
                phpsessid=credentials['phpsessid'],
                golden_key=credentials['golden_key'],
                csrf_token=credentials['csrf_token']
            )
            self.clients[suffix] = client

            asyncio.create_task(client.connect(self.handle_message))

            logger.info(f"Бот запущен с {len(self.clients)} аккаунтами FunPay")

            await asyncio.Event().wait()

    async def handle_message(self, suffix: str, data: Dict):
        """Обработка входящего сообщения"""
        try:
            chat_id = data.get('chatId') or data.get('chat_id')
            message_text = data.get('text', '').lower()
            message_id = data.get('id') or data.get('messageId')

            if not all([chat_id, message_id]):
                logger.warning(f"{suffix}: Неполные данные: {data}")
                return

            async with self.db.pool.acquire() as conn:
                exists = await conn.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM processed_messages WHERE message_id = $1)",
                    message_id
                )
                
            if exists:
                logger.debug(f"⏭️ {suffix}: Сообщение {message_id} уже обработано")
                return

            # Логируем входящее сообщение
            await self.db.log_event(suffix, "incoming", f"From {chat_id}: {message_text[:100]}")
            logger.info(f"💬 {suffix}: {chat_id}: {message_text[:50]}")

            # Генерируем ответ
            response = await self.generate_response(suffix, chat_id, message_text)
            
            if response:
                client = self.clients.get(suffix)
                if client:
                    await client.send_message(chat_id, response)
                    await self.db.log_event(suffix, "outgoing", f"To {chat_id}: {response[:100]}")
                    
                    # Отмечаем сообщение как обработанное
                    async with self.db.pool.acquire() as conn:
                        await conn.execute(
                            "INSERT INTO processed_messages (message_id, funpay_suffix) VALUES ($1, $2)",
                            message_id, suffix
                        )
                        
        except Exception as e:
            logger.error(f"❌ Ошибка в handle_message: {e}")

    async def generate_response(self, suffix: str, chat_id: str, message: str) -> Optional[str]:
        """Генерация ответа на сообщение"""

        if any (word in message for word in ['привет', 'здравствуй', 'hello', 'hi']):
            return f"""Приветствую! 🎉🎉

Можете смело оплачивать: ваш заказ мгновенно выдаст наш бот, который работает 24/7.
✔️ А подтверждаете вы оплату — только после получения аккаунта.
✖️ Если вы видите лот, значит аренда аккаунта доступна и есть в наличии!
🔗 По количеству доступных аккаунтов можете уточнить у админа.
📅 Хотите купить несколько аккаунтов? — Оплачивайте их разными лотами.

👥 !админ — Вызвать администратора для помощи, если бот не справляется с вашим вопросом.
🟢 (На связи с 10:00 до 00:00 по МСК)."""
        
        if message in ['!админ', '!admin']:
            # Aiogram
            return "👥 Ваш запрос передан администратору. Ожидайте ответа (10:00-19:00 МСК)."
        
        return None
    
    async def get_available_count(self) -> int:
        """Получить количество доступных аккаунтов"""
        accounts = await self.db.get_available_steam_accounts()
        return len(accounts)
    
    async def check_expired_rentals(self):
        """Проверка просроченных аренд"""
        while True:
            await asyncio.sleep(60)

            async with self.db.pool.acquire() as conn:
                expired = await conn.fetch("""
                    SELECT * FROM steam_accounts 
                    WHERE is_available = false 
                    AND rent_expires < NOW()
                """)
                for account in expired:
                    logger.info(f"⏰ Просрочена аренда {account['login']}")
                    await self.db.force_close_rental(account['id'])

                    client = self.clients.get(account['funpay_suffix'])
                    if client and account['rented_by']:
                        await client.send_message(
                            account['rented_by'],
                            f"⏰ Ваша аренда аккаунта {account['login']} истекла. Доступ закрыт.\n\nДля продления обратитесь к администратору."
                        )
                    await self.db.log_event(
                        account['funpay_suffix'], 
                        "expired", 
                        f"Аккаунт {account['login']} освобожден"
                    )

async def main():
    bot = FunPaySteamBot()
    await bot.start()

if __name__ == "__main__":
    asyncio.run(main())