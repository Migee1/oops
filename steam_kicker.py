import base64
import time
import asyncio
import json
import os
from threading import Thread
from typing import Union, Optional

from bs4 import BeautifulSoup as bs, PageElement

from pip._internal.cli.main import main
try:
    from pydantic import BaseModel
except ImportError:
    main(["install", "-U", "pydantic"])
    from pydantic import BaseModel

t = 0
if t:
    from cardinal import Cardinal as C

from telebot.types import CallbackQuery, InlineKeyboardMarkup as K, InlineKeyboardButton as B

import os
import json

from tg_bot import CBT as _CBT

import logging

logger = logging.getLogger(f"FPC.{__name__}")
prefix = '[SteamKickerPlugin]'

def log(msg=None, debug=0, err=0, lvl="info", **kw):
    if debug:
        return logger.debug(f"TRACEBACK", exc_info=kw.pop('exc_info', True), **kw)
    msg = f"{prefix} {msg}"
    if err:
        return logger.error(f"{msg}", **kw)
    return getattr(logger, lvl)(msg, **kw)

CREDITS = "@thhhhoo3"
SETTINGS_PAGE = True
UUID = '40c07291-90db-4ab9-99f6-8615cf10ce69'
NAME = 'Steam Account Kicker'
DESCRIPTION = 'Плагин для принудительного выхода арендаторов из Steam аккаунтов через смену пароля с автоматическим 2FA из maFile'
VERSION = '1.0.0'

log(f"Плагин {NAME} успешно загружен")

s: Optional['Settings'] = None

_PARENT_FOLDER = 'steam_kicker'
_STORAGE_PATH = os.path.join(os.path.dirname(__file__), "..", "storage", "plugins", _PARENT_FOLDER)


def _get_path(f):
    return os.path.join(_STORAGE_PATH, f if "." in f else f + ".json")


os.makedirs(_STORAGE_PATH, exist_ok=True)


def _load(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def load_settings():
    global s
    s = Settings(**_load(_get_path('settings.json')))


def save_settings():
    global s
    _save(_get_path('settings.json'), s.model_dump())


class Settings(BaseModel):
    steam_mafiles_folder: str = "mafiles"  # папка с maFile внутри storage/plugins/steam_kicker/
    auto_reset_on_rental_end: bool = True  # автосброс при окончании аренды


    def toggle(self, p):
        setattr(self, p, not getattr(self, p))
        save_settings()


load_settings()


class SteamAccountStorage:
    """Хранилище привязок аренда -> Steam аккаунт"""
    def __init__(self):
        self.data = _load(_get_path("rentals.json"))

    def add_rental(self, funpay_username: str, steam_login: str, mafile_path: str, current_password: str, order_id: int = None):

        self.data[funpay_username] = {
            "steam_login": steam_login,
            "mafile_path": mafile_path,
            "current_password": current_password,
            "order_id": order_id,
            "rental_start": time.time()
        }
        _save(_get_path("rentals.json"), self.data)

    def remove_rental(self, funpay_username: str):
        """Удаляет запись об аренде по FunPay логину"""
        if funpay_username in self.data:
            del self.data[funpay_username]
            _save(_get_path("rentals.json"), self.data)

    def get_steam_account(self, funpay_username: str) -> Optional[dict]:
        """Получает данные Steam аккаунта по FunPay логину арендатора"""
        return self.data.get(funpay_username)

    def get_rental_by_order(self, order_id: int) -> Optional[tuple[str, dict]]:
        """Ищет аренду по ID заказа"""
        for username, data in self.data.items(): # funpay_username?
            if data.get('order_id') == order_id:
                return username, data
        return None, None

    def get_all_rentals(self) -> dict:
        return self.data

    def clear(self):
        self.data = {}
        _save(_get_path("rentals.json"), self.data)


rental_storage = SteamAccountStorage()


def get_steam_guard_code(shared_secret: str) -> str:
    """Генерирует актуальный Steam Guard код из shared_secret"""
    try:
        import steam_totp
        return steam_totp.get_code(shared_secret)
    except ImportError:
        from subprocess import call
        call(["pip", "install", "steam-totp"])
        import steam_totp
        return steam_totp.get_code(shared_secret)


def login_and_change_password(mafile_path: str, new_password: str) -> tuple[bool, str]:
    """
    Меняет пароль Steam аккаунта используя maFile
    Возвращает (успех, сообщение_об_ошибке)
    """
    full_path = os.path.join(_STORAGE_PATH, mafile_path)
    
    if not os.path.exists(full_path):
        return False, f"maFile не найден: {mafile_path}"
    
    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            mafile = json.load(f)
    except Exception as e:
        return False, f"Ошибка чтения maFile: {str(e)}"
    
    login = mafile.get('account_name')
    if not login:
        return False, "В maFile не указан account_name"
    
    shared_secret = mafile.get('shared_secret')
    if not shared_secret:
        return False, "В maFile не указан shared_secret"
    
    try:
        twofactor_code = get_steam_guard_code(shared_secret)
    except Exception as e:
        return False, f"Ошибка генерации 2FA кода: {str(e)}"
    
    try:
        from steam.client import SteamClient
        from steam.enums import EResult
    except ImportError:
        from subprocess import call
        call(["pip", "install", "steam"])
        from steam.client import SteamClient
        from steam.enums import EResult
    
    client = SteamClient()
    
    try:
        # Логинимся
        result = client.login(
            username=login,
            password=mafile.get('password', ''),
            two_factor_code=twofactor_code
        )
        
        if result != EResult.OK:
            return False, f"Ошибка логина: {result}"
        
        # Меняем пароль
        change_result = client.change_password(new_password)
        
        if change_result == EResult.OK:
            # Обновляем пароль в maFile
            mafile['password'] = new_password
            with open(full_path, 'w', encoding='utf-8') as f:
                json.dump(mafile, f, indent=4)
            return True, "Пароль успешно изменён"
        else:
            return False, f"Ошибка смены пароля: {change_result}"
            
    except Exception as e:
        return False, f"Ошибка: {str(e)}"
    finally:
        client.disconnect()


class CBT:
    SETTINGS = f'{_CBT.PLUGIN_SETTINGS}:{UUID}:0'
    KICK_USER = 'KICK_USER'
    KICK_USER_CONFIRM = 'KICK_USER_CONFIRM'
    KICK_USER_CANCEL = 'KICK_USER_CANCEL'
    RENTAL_LIST = 'RENTAL_LIST'
    RENTAL_LIST_PAGE = 'RENTAL_LIST_PAGE'
    VIEW_RENTAL = 'VIEW_RENTAL'
    TOGGLE_SETTING = 'TOGGLE_SETTING'
    GENERATE_PASSWORD = 'GENERATE_PASSWORD'
    KICK_ALL = 'KICK_ALL'
    KICK_ALL_CONFIRM = 'KICK_ALL_CONFIRM'
    REFRESH_LIST = 'REFRESH_LIST'


def generate_strong_password(length=20):
    import random
    import string
    chars = string.ascii_letters + string.digits + "!@#$%"
    return ''.join(random.choice(chars) for _ in range(length))


def _main_kb():
    return K(row_width=1).add(
        B("🔑 Принудительный выход арендатора", None, CBT.KICK_USER),
        B("📋 Список активных аренд", None, f"{CBT.RENTAL_LIST}:0"),
        B(f"{'🟢' if s.auto_reset_on_rental_end else '🔴'} Автосброс при окончании аренды", 
          None, f"{CBT.TOGGLE_SETTING}:auto_reset_on_rental_end"),
        B('◀️ Назад', None, f"{_CBT.EDIT_PLUGIN}:{UUID}:0")
    )


def _main_text():
    return f"""⚙️ <b>Настройки плагина «{NAME}»</b>

<b>📁 Папка с maFile:</b> <code>{s.steam_mafiles_folder}</code>
<b>📊 Активных аренд:</b> <code>{len(rental_storage.get_all_rentals())}</code>

• maFile должны лежать в папке <code>storage/plugins/steam_kicker/{s.steam_mafiles_folder}/</code>
• Имя файла должно быть <code>login.maFile</code> (например: <code>myaccount.maFile</code>)
• После смены пароля новый пароль сохраняется в тот же maFile"""


def _rental_list_kb(offset=0, max_on_page=10): # !
    rentals = rental_storage.get_all_rentals()
    items = list(rentals.items())
    kb = K(row_width=1)
    
    for username, data in items[offset:offset + max_on_page]:
        steam_login = data.get('steam_login', '?')
        # Получаем username через tg бота (если есть доступ)
        kb.add(B(f"👤 {steam_login}", None, f"{CBT.VIEW_RENTAL}:{funpay_username}:{offset}"))
    
    navigation_row = []
    if offset > 0:
        navigation_row.append(B("⬅️", None, f"{CBT.RENTAL_LIST_PAGE}:{offset - max_on_page}"))
    if offset + max_on_page < len(items):
        navigation_row.append(B("➡️", None, f"{CBT.RENTAL_LIST_PAGE}:{offset + max_on_page}"))
    if navigation_row:
        curr_page = offset // max_on_page + 1
        total_pages = (len(items) + max_on_page - 1) // max_on_page
        navigation_row.insert(1, B(f"{curr_page}/{total_pages}", None, _CBT.EMPTY))
        kb.row(*navigation_row)
    
    kb.row(B("🔄 Обновить", None, CBT.REFRESH_LIST))
    kb.row(B("🔁 Принудительно выгнать всех", None, CBT.KICK_ALL))
    kb.row(B("◀️ Назад", None, CBT.SETTINGS))
    return kb


def _rental_list_text(): # !
    rentals = rental_storage.get_all_rentals()
    if not rentals:
        return "📭 <b>Нет активных аренд</b>\n\nСписок аренд пуст."
    
    text = f"📋 <b>Активные аренды ({len(rentals)})</b>\n\n"
    for f_username, data in list(rentals.items())[:15]:
        steam_login = data.get('steam_login', '?')
        start_time = data.get('rental_start', 0)
        if start_time:
            hours_ago = int((time.time() - start_time) / 3600)
            text += f"• <code>{steam_login}</code> (арендатор: {funpay_username}, {hours_ago}ч назад)\n"
        else:
            text += f"• <code>{steam_login}</code> (арендатор: {funpay_username})\n"
    
    if len(rentals) > 15:
        text += f"\n...и ещё {len(rentals) - 15} аренд"
    
    return text


def _kick_confirm_kb(steam_login: str, funpay_username: str, offset=0):
    return K().add(
        B("✅ Да, выгнать", None, f"{CBT.KICK_USER_CONFIRM}:{steam_login}:{funpay_username}:{offset}"),
        B("❌ Отмена", None, f"{CBT.KICK_USER_CANCEL}:{offset}")
    )


def _kick_confirm_text(steam_login: str, funpay_username: str):
    return f"""⚠️ <b>Подтверждение принудительного выхода</b>

<b>Steam аккаунт:</b> <code>{steam_login}</code>
<b>ID арендатора Funpay:</b> <code>{funpay_username}</code>

После смены пароля арендатор потеряет доступ к аккаунту.
Новый пароль будет сохранён в maFile автоматически."""


def _kick_all_confirm_kb():
    return K().add(
        B("✅ Да, выгнать всех", None, CBT.KICK_ALL_CONFIRM),
        B("❌ Отмена", None, f"{CBT.RENTAL_LIST}:0")
    )


def _kick_all_confirm_text():
    count = len(rental_storage.get_all_rentals())
    return f"""⚠️ <b>Подтверждение массового выхода</b>

Будут принудительно выгнаны <b>{count}</b> арендатор(ов).
Это займёт некоторое время.
Новые пароли сохранятся в maFile автоматически.

<b>Продолжить?</b>"""


def init(cardinal: 'C'):
    tg = cardinal.telegram
    bot = tg.bot

    def _func(data=None, start=None):
        if start:
            return lambda c: c.data.startswith(start)
        if data:
            return lambda c: c.data == data
        return lambda c: False

    def settings_menu(chat_id=None, c=None):
        if c:
            bot.edit_message_text(_main_text(), c.message.chat.id, c.message.id, reply_markup=_main_kb())
        else:
            bot.send_message(chat_id, _main_text(), reply_markup=_main_kb())

    def open_menu(c: CallbackQuery):
        settings_menu(c=c)

    def show_kick_menu(c: CallbackQuery):
        bot.edit_message_text(
            "🔑 <b>Принудительный выход арендатора</b>\n\n"
            "Введи ID арендатора в Telegram или выбери из списка ниже:",
            c.message.chat.id,
            c.message.id,
            reply_markup=K().add(B("📋 Выбрать из активных аренд", None, f"{CBT.RENTAL_LIST}:0"),
                                 B("◀️ Назад", None, CBT.SETTINGS))
        )
    
    def show_rental_list(c: CallbackQuery):
        offset = int(c.data.split(":")[-1]) if ":" in c.data else 0
        bot.edit_message_text(
            _rental_list_text(),
            c.message.chat.id,
            c.message.id,
            reply_markup=_rental_list_kb(offset)
        )
    
    def view_rental_details(c: CallbackQuery):
        _, funpay_username, offset = c.data.split(":")
        funpay_username = str(funpay_username)
        offset = int(offset)
        
        rental = rental_storage.get_steam_account(funpay_username)
        if not rental:
            bot.answer_callback_query(c.id, "Эта аренда больше не активна")
            show_rental_list(c)
            return
        
        steam_login = rental.get('steam_login', '?')
        password = rental.get('current_password', '?')
        start_time = rental.get('rental_start', 0)
        
        hours_ago = int((time.time() - start_time) / 3600) if start_time else 0
        
        text = f"""📋 <b>Детали аренды</b>

<b>Steam аккаунт:</b> <code>{steam_login}</code>
<b>Арендатор:</b> <code>{funpay_username}</code>
<b>Текущий пароль:</b> <code>{password}</code>
<b>Активна:</b> {hours_ago} часов
        
<b>Действия:</b>"""
        
        kb = K().add(
            B("🔑 Выгнать арендатора", None, f"{CBT.KICK_USER}:{steam_login}:{funpay_username}:{offset}"),
            B("◀️ Назад к списку", None, f"{CBT.RENTAL_LIST}:{offset}")
        )
        
        bot.edit_message_text(text, c.message.chat.id, c.message.id, reply_markup=kb)
    
    def kick_user(c: CallbackQuery):
        try:
            _, steam_login, funpay_username, offset = c.data.split(":", 3)
            funpay_username = str(funpay_username)
            offset = int(offset)
        except ValueError:
            # Если просто CBT.KICK_USER без параметров
            bot.edit_message_text(
                "Введи Steam логин аккаунта для сброса:",
                c.message.chat.id,
                c.message.id,
                reply_markup=K().add(B("◀️ Назад", None, CBT.SETTINGS))
            )
            return
        
        bot.edit_message_text(
            _kick_confirm_text(steam_login, funpay_username),
            c.message.chat.id,
            c.message.id,
            reply_markup=_kick_confirm_kb(steam_login, funpay_username, offset)
        )
    
    def execute_kick(c: CallbackQuery):
        _, steam_login, funpay_username, offset = c.data.split(":", 3)
        funpay_username = str(funpay_username)
        offset = int(offset)
        
        # Ищем maFile для этого аккаунта
        rental = rental_storage.get_steam_account(funpay_username)
        if not rental:
            bot.answer_callback_query(c.id, "Аренда не найдена!")
            settings_menu(c=c)
            return
        
        mafile_path = rental.get('mafile_path')
        if not mafile_path:
            bot.answer_callback_query(c.id, "maFile не привязан к этой аренде!")
            return
        
        new_password = generate_strong_password()
        
        bot.edit_message_text(
            f"🔄 <b>Выполняется смена пароля для {steam_login}...</b>\n\n"
            f"Это может занять до 30 секунд.",
            c.message.chat.id,
            c.message.id
        )
        
        # Выполняем смену пароля в отдельном потоке
        def do_kick():
            success, msg = login_and_change_password(mafile_path, new_password)
            
            if success:
                # Обновляем пароль в хранилище
                rental['current_password'] = new_password
                rental_storage.add_rental(funpay_username, steam_login, mafile_path, new_password)
                
                bot.send_message(
                    c.message.chat.id,
                    f"✅ <b>Арендатор выгнан!</b>\n\n"
                    f"<b>Steam аккаунт:</b> <code>{steam_login}</code>\n"
                    f"<b>Новый пароль:</b> <code>{new_password}</code>\n\n"
                    f"⚠️ Сохрани этот пароль для следующей аренды."
                )
            else:
                bot.send_message(
                    c.message.chat.id,
                    f"❌ <b>Ошибка при смене пароля!</b>\n\n"
                    f"<b>Steam аккаунт:</b> <code>{steam_login}</code>\n"
                    f"<b>Ошибка:</b> {msg}"
                )
            
            # Возвращаемся в меню настроек
            settings_menu(chat_id=c.message.chat.id)
        
        Thread(target=do_kick).start()
    
    def cancel_kick(c: CallbackQuery):
        _, offset = c.data.split(":", 1)
        offset = int(offset)
        # Возвращаемся к списку аренд или в меню
        if offset >= 0:
            show_rental_list(c)
        else:
            settings_menu(c=c)
    
    def kick_all_users(c: CallbackQuery):
        bot.edit_message_text(
            _kick_all_confirm_text(),
            c.message.chat.id,
            c.message.id,
            reply_markup=_kick_all_confirm_kb()
        )
    
    def execute_kick_all(c: CallbackQuery):
        rentals = rental_storage.get_all_rentals()
        if not rentals:
            bot.answer_callback_query(c.id, "Нет активных аренд!")
            settings_menu(c=c)
            return
        
        bot.edit_message_text(
            f"🔄 <b>Начинаю массовый выход ({len(rentals)} аренд)...</b>\n\n"
            f"Это может занять несколько минут.",
            c.message.chat.id,
            c.message.id
        )
        
        def do_kick_all():
            success_count = 0
            fail_count = 0
            
            for f_username, rental in rentals.items():
                steam_login = rental.get('steam_login')
                mafile_path = rental.get('mafile_path')
                new_password = generate_strong_password()
                
                if not mafile_path:
                    fail_count += 1
                    continue
                
                success, msg = login_and_change_password(mafile_path, new_password)
                
                if success:
                    rental['current_password'] = new_password
                    rental_storage.add_rental(str(f_username), steam_login, mafile_path, new_password)
                    success_count += 1
                else:
                    fail_count += 1
                
                time.sleep(2)  # пауза между аккаунтами
            
            bot.send_message(
                c.message.chat.id,
                f"✅ <b>Массовый выход завершён!</b>\n\n"
                f"• Успешно: <code>{success_count}</code>\n"
                f"• Ошибок: <code>{fail_count}</code>\n"
                f"• Всего: <code>{len(rentals)}</code>"
            )
            settings_menu(chat_id=c.message.chat.id)
        
        Thread(target=do_kick_all).start()
    
    def toggle_setting(c: CallbackQuery):
        _, setting_name = c.data.split(":", 1)
        s.toggle(setting_name)
        bot.edit_message_reply_markup(c.message.chat.id, c.message.id, reply_markup=_main_kb())
    
    def refresh_list(c: CallbackQuery):
        show_rental_list(c)
    
    # Регистрируем обработчики
    tg.cbq_handler(open_menu, _func(start=CBT.SETTINGS))
    tg.cbq_handler(show_kick_menu, _func(data=CBT.KICK_USER))
    tg.cbq_handler(show_rental_list, _func(start=f"{CBT.RENTAL_LIST}:"))
    tg.cbq_handler(view_rental_details, _func(start=CBT.VIEW_RENTAL))
    tg.cbq_handler(kick_user, _func(start=CBT.KICK_USER))
    tg.cbq_handler(execute_kick, _func(start=CBT.KICK_USER_CONFIRM))
    tg.cbq_handler(cancel_kick, _func(start=CBT.KICK_USER_CANCEL))
    tg.cbq_handler(kick_all_users, _func(data=CBT.KICK_ALL))
    tg.cbq_handler(execute_kick_all, _func(data=CBT.KICK_ALL_CONFIRM))
    tg.cbq_handler(toggle_setting, _func(start=CBT.TOGGLE_SETTING))
    tg.cbq_handler(refresh_list, _func(data=CBT.REFRESH_LIST))


# Экспортируем хуки для Cardinal
BIND_TO_DELETE = None
BIND_TO_PRE_INIT = [init]
BIND_TO_ORDERS = [on_new_order]  # Хук на новые заказы

@cardinal.on_new_order
def handle_new_order(order):
    """
    order содержит:
    - order.buyer_username - логин покупателя на FunPay
    - order.id - ID заказа
    - order.product_id - ID товара (лота)
    - order.price - цена
    - order.quantity - количество
    - order.comment - комментарий (может содержать Steam логин)
    """
    
    # Получаем из комментария или настроек лота какой Steam аккаунт выдать
    steam_account = get_steam_account_by_product(order.product_id)
    
    # Добавляем аренду
    rental_storage.add_rental(
        funpay_username=order.buyer_username,
        steam_login=steam_account['login'],
        mafile_path=steam_account['mafile_path'],
        current_password=steam_account['password'],
        order_id=order.id
    )
    
    # Выдаём данные арендатору
    send_steam_credentials(order.buyer_username, steam_account)