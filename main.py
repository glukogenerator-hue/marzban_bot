import asyncio
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from config import settings
from database.db_manager import db_manager
from handlers.user_handlers import user_router
from handlers.admin_handlers import admin_router
from handlers.payment_handlers import payment_router
from utils.logger import logger

async def main():
    """Главная функция"""
    # Инициализация бота
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    dp = Dispatcher()
    
    # Регистрация роутеров
    dp.include_router(admin_router)
    dp.include_router(user_router)
    dp.include_router(payment_router)
    
    # Инициализация БД
    await db_manager.init_db()
    
    # Синхронизация пользователей из Marzban при первом старте (если база пуста)
    try:
        synced_count = await db_manager.sync_marzban_users()
        if synced_count > 0:
            logger.info(f"Синхронизировано {synced_count} пользователей из Marzban")
    except Exception as e:
        logger.error(f"Ошибка синхронизации пользователей из Marzban: {e}")
    
    # Логируем загруженные настройки
    logger.info(f"Bot started")
    logger.info(f"Admin IDs loaded: {settings.ADMIN_IDS} (type: {type(settings.ADMIN_IDS)})")
    logger.info(f"Telegram Stars enabled: {settings.TELEGRAM_STARS_ENABLED}")
    
    try:
        # Уведомляем админов о запуске
        for admin_id in settings.ADMIN_IDS:
            try:
                await bot.send_message(admin_id, "🤖 Бот запущен и готов к работе!")
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id}: {e}")
        
        # Запуск polling
        await dp.start_polling(bot)
    finally:
        # Закрываем сессии
        await bot.session.close()
        from marzban.api_client import marzban_api
        await marzban_api.close()
        logger.info("Bot stopped")

if __name__ == "__main__":
    asyncio.run(main())
