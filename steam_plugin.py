import asyncio
import json
from steam.client import SteamClient
from steam.enums import EResult
import steam_totp

def login_and_change_password(mafile_path: str, new_password: str) -> bool:
    with open(mafile_path, 'r') as f: # заменить путь
        mafile = json.load(f)
    
    login = mafile.get('account_name')
    shared_secret = mafile['shared_secret']
    
    # 2FA код
    twofactor_code = steam_totp.get_code(shared_secret)
    
    client = SteamClient()
    
    # Логинимся
    result = client.login(
        username=login,
        password=mafile.get('password', ''),
        two_factor_code=twofactor_code
    )
    
    if result != EResult.OK:
        print(f"Ошибка логина: {result}")
        return False
    
    # Меняем пароль
    change_result = client.change_password(new_password)
    
    if change_result == EResult.OK:
        # Обновляем пароль в maFile для будущих входов
        mafile['password'] = new_password
        with open(mafile_path, 'w') as f:
            json.dump(mafile, f, indent=4)
        return True
    
    return False