import asyncio
import websockets
import json
import aiohttp
from datetime import datetime
from typing import Optional, Dict, Callable
import logging
from config import 

logger = logging.getLogger(__name__)

class FunPayClient_e:
    """Клиент аккаунта Егора"""

    def __init__(self, suffix: str, phpsessid: str, golden_key: str, csrf_token: str):
        self.suffix = suffix
        self.phpsessid = phpsessid
        self.golden_key = golden_key
        self.csrf_token = csrf_token
        self.ws = None
        self.connected = False
        self.message_handler: Optional[Callable] = None

    @property
    def name(self):
        return f"FunPay-{self.suffix}"
    
    def get_headers(self):
        return {
            'x-csrf-token': self.csrf_token,
            'cookie': f'PHPSESSID={self.phpsessid}',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    
    async def connect(self, message_handler: Callable):
        """Подключение к WebSocket FunPay"""
        self.message_handler = message_handler
        uri = f"wss://api.funpay.com/ws?golden_key={self.golden_key}"
        
        while True:
            try:
                logger.info(f"🔄 {self.name}: Подключение...")
                
                async with websockets.connect(
                    uri,
                    ping_interval=20,
                    ping_timeout=10
                ) as websocket:
                    self.ws = websocket
                    self.connected = True
                    logger.info(f"✅ {self.name}: Подключен")
                    
                    # Запускаем пинг
                    asyncio.create_task(self._send_ping())
                    
                    # Слушаем сообщения
                    await self._listen()
                    
            except Exception as e:
                logger.error(f"❌ {self.name}: Ошибка: {e}")
                self.connected = False
                await asyncio.sleep(5)
    
    async def _send_ping(self):
        """Отправка ping для поддержания соединения"""
        while self.connected and self.ws:
            try:
                await asyncio.sleep(30)
                await self.ws.send(json.dumps({"type": "ping"}))
                logger.debug(f"💓 {self.name}: Ping отправлен")
            except:
                break
    
    async def _listen(self):
        """Прослушивание входящих сообщений"""
        try:
            async for message in self.ws:
                try:
                    if isinstance(message, bytes):
                        message = message.decode('utf-8')

                    data = json.loads(message)

                    logger.debug(f"📨 {self.name}: Получено: {json.dumps(data, ensure_ascii=False)[:200]}")
                    
                    if data.get('type') == 'new_message' and self.message_handler:
                        await self.message_handler(self.suffix, data)
                    elif data.get('type') == 'pong':
                        logger.debug(f"💓 {self.name}: Pong получен")
                    elif data.get('type') == 'ping':
                        await self.ws.send(json.dumps({"type": "pong"}))
                        
                except json.JSONDecodeError as e:
                    logger.error(f"❌ {self.name}: Ошибка парсинга JSON: {e}")
                    logger.debug(f"Raw message: {message[:200]}")
                except Exception as e:
                    logger.error(f"❌ {self.name}: Ошибка обработки: {e}")
                    
        except websockets.exceptions.ConnectionClosed:
            logger.warning(f"⚠️ {self.name}: Соединение закрыто")
        except Exception as e:
            logger.error(f"❌ {self.name}: Ошибка: {e}")
    
    async def send_message(self, chat_id: str, text: str):
        """Отправка сообщения"""
        data = {'chatId': chat_id, 'text': text}
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    'https://funpay.com/chat/sendMessage',
                    headers=self.get_headers(),
                    data=data
                ) as resp:
                    if resp.status == 200:
                        logger.info(f"✅ {self.name}: Сообщение отправлено в {chat_id}")
                    else:
                        logger.error(f"❌ {self.name}: Ошибка {resp.status}")
            except Exception as e:
                logger.error(f"❌ {self.name}: Ошибка отправки: {e}")