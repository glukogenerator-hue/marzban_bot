from functools import wraps
from aiogram import types
from config import settings
from database.db_manager import db_manager
from utils.logger import logger

def admin_only(func):
    """Декоратор для проверки прав админа"""
    @wraps(func)
    async def wrapper(message: types.Message, *args, **kwargs):
        if message.from_user.id not in settings.ADMIN_IDS:
            await message.answer("❌ У вас нет прав администратора")
            logger.warning(f"Unauthorized admin access attempt: {message.from_user.id}")
            return
        return await func(message, *args, **kwargs)
    return wrapper

def user_registered(func):
    """Декоратор для проверки регистрации пользователя"""
    @wraps(func)
    async def wrapper(message: types.Message, *args, **kwargs):
        user = await db_manager.get_user(message.from_user.id)
        if not user:
            await message.answer("❌ Вы не зарегистрированы. Используйте /start")
            return
        return await func(message, *args, **kwargs)
    return wrapper
