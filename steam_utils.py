import pyotp
import random
import string
from typing import Optional, Dict

class SteamUtils:
    
    @staticmethod
    def generate_totp_code(shared_secret: str) -> Optional[str]:
        """Генерация TOTP кода"""
        try:
            if not shared_secret:
                return None
            totp = pyotp.TOTP(shared_secret)
            return totp.now()
        except Exception as e:
            print(f"Ошибка TOTP: {e}")
            return None
    
    @staticmethod
    def generate_random_password(length: int = 16) -> str:
        """Генерация случайного пароля"""
        chars = string.ascii_letters + string.digits + "!@#$%^&*"
        return ''.join(random.choice(chars) for _ in range(length))
    
    @staticmethod
    def format_account_message(account: Dict, totp_code: str = None) -> str:
        """Форматирование сообщения с данными аккаунта"""
        message = f"""✅ **Аккаунт арендован!**

                          **Данные для входа:**
        Логин: {account['login']}
        Пароль: {account['password']}
    """

        if totp_code:
            message += f"Steam Guard: {totp_code}\n"

        if account.get('rent_expires'):
            expires = account['rent_expires'].strftime('%d.%m.%Y %H:%M')
            message += f"```\n\n⏰ Аккаунт арендован до: {expires}\n"

        message += """
        📌 Важно:
• Код Steam Guard обновляется каждые 30 секунд
• Не меняйте пароль от аккаунта
• По истечении времени аренды доступ будет закрыт автоматически

❗ Нарушение правил приведет к блокировке без возврата средств!"""

        return message