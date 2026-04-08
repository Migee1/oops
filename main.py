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