from functools import wraps
from aiogram import types
from aiogram.types import Message, CallbackQuery
from config import settings
from database.db_manager import db_manager
from utils.logger import logger
from typing import Union

def admin_only(func):
    """Декоратор для проверки прав админа (работает с Message и CallbackQuery)"""
    @wraps(func)
    async def wrapper(event: Union[Message, CallbackQuery], *args, **kwargs):
        user_id = event.from_user.id if hasattr(event, 'from_user') else None
        
        if not user_id or user_id not in settings.ADMIN_IDS:
            error_msg = "❌ У вас нет прав администратора"
            if isinstance(event, CallbackQuery):
                await event.answer(error_msg, show_alert=True)
            else:
                await event.answer(error_msg)
            logger.warning(f"Unauthorized admin access attempt: {user_id}")
            return
        return await func(event, *args, **kwargs)
    return wrapper

def user_registered(func):
    """Декоратор для проверки регистрации пользователя (работает с Message и CallbackQuery)"""
    @wraps(func)
    async def wrapper(event: Union[Message, CallbackQuery], *args, **kwargs):
        user_id = event.from_user.id if hasattr(event, 'from_user') else None
        
        if not user_id:
            error_msg = "❌ Ошибка получения ID пользователя"
            if isinstance(event, CallbackQuery):
                await event.answer(error_msg, show_alert=True)
            else:
                await event.answer(error_msg)
            return
        
        user = await db_manager.get_user(user_id)
        if not user:
            error_msg = "❌ Вы не зарегистрированы. Используйте /start"
            if isinstance(event, CallbackQuery):
                await event.answer(error_msg, show_alert=True)
            else:
                await event.answer(error_msg)
            return
        return await func(event, *args, **kwargs)
    return wrapper
