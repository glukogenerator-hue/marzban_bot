from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from database.db_manager import db_manager
from marzban.api_client import marzban_api
from keyboards.admin_keyboards import *
from keyboards.user_keyboards import get_main_keyboard
from utils.helpers import *
from utils.decorators import admin_only
from utils.logger import logger
from datetime import datetime, timedelta

admin_router = Router()

class AdminStates(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_user_search = State()

@admin_router.message(Command("admin"))
@admin_only
async def cmd_admin(message: Message):
    """Команда /admin"""
    text = (
        "🔐 <b>Панель администратора</b>\n\n"
        "Используйте меню для управления ботом"
    )
    await message.answer(text, reply_markup=get_admin_keyboard(), parse_mode="HTML")

@admin_router.message(F.text == "📊 Статистика")
@admin_only
async def show_statistics(message: Message):
    """Показать статистику"""
    total_users = await db_manager.get_users_count()
    active_users = await db_manager.get_users_count(active_only=True)
    
    users = await db_manager.get_all_users()
    
    # Расчет статистики по трафику
    total_traffic_used = sum(u.used_traffic or 0 for u in users)
    total_traffic_limit = sum(u.data_limit or 0 for u in users)
    
    # Пользователи с истекающими подписками
    expiring_soon = await db_manager.get_expiring_users(days=7)
    
    text = (
        f"📊 <b>Статистика бота</b>\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"✅ Активных подписок: {active_users}\n"
        f"❌ Неактивных: {total_users - active_users}\n\n"
        f"📈 Использовано трафика: {format_bytes(total_traffic_used)}\n"
        f"📊 Лимит трафика: {format_bytes(total_traffic_limit)}\n\n"
        f"⚠️ Истекает в ближайшие 7 дней: {len(expiring_soon)}\n\n"
        f"📅 Обновлено: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )
    
    await message.answer(text, parse_mode="HTML")

@admin_router.message(F.text == "👥 Пользователи")
@admin_only
async def show_users(message: Message):
    """Показать список пользователей"""
    users = await db_manager.get_all_users()
    
    if not users:
        await message.answer("❌ Пользователей не найдено")
        return
    
    # Показываем первых 10 пользователей
    text = "👥 <b>Список пользователей</b>\n\n"
    
    for i, user in enumerate(users[:10], 1):
        status = "✅" if user.is_active else "❌"
        username = f"@{user.username}" if user.username else "Без username"
        text += (
            f"{i}. {status} {user.first_name} {username}\n"
            f"   ID: <code>{user.telegram_id}</code>\n"
        )
        if user.marzban_username:
            text += f"   Marzban: <code>{user.marzban_username}</code>\n"
        text += "\n"
    
    if len(users) > 10:
        text += f"\n...и еще {len(users) - 10} пользователей"
    
    text += "\n💡 Используйте /user [telegram_id] для управления пользователем"
    
    await message.answer(text, parse_mode="HTML")

@admin_router.message(Command("user"))
@admin_only
async def manage_user(message: Message):
    """Управление пользователем"""
    try:
        parts = message.text.split()
        if len(parts) < 2:
            raise ValueError("Missing telegram_id")
        telegram_id = int(parts[1])
        
        # Валидация ID
        if telegram_id <= 0:
            raise ValueError("Invalid telegram_id")
    except (IndexError, ValueError) as e:
        await message.answer("❌ Использование: /user [telegram_id]\nПример: /user 123456789")
        logger.warning(f"Invalid user command: {message.text}, error: {e}")
        return
    
    user = await db_manager.get_user(telegram_id)
    
    if not user:
        await message.answer(f"❌ Пользователь с ID {telegram_id} не найден")
        return
    
    status = "✅ Активна" if user.is_active else "❌ Неактивна"
    trial = "Да" if user.trial_used else "Нет"
    
    text = (
        f"👤 <b>Информация о пользователе</b>\n\n"
        f"Имя: {user.first_name or 'Не указано'}\n"
        f"Username: @{user.username or 'Нет'}\n"
        f"Telegram ID: <code>{user.telegram_id}</code>\n\n"
        f"Статус: {status}\n"
        f"Тестовый доступ использован: {trial}\n"
    )
    
    if user.marzban_username:
        text += (
            f"\nMarzban: <code>{user.marzban_username}</code>\n"
            f"Трафик: {format_bytes(user.used_traffic or 0)} / {format_bytes(user.data_limit or 0)}\n"
            f"Истекает: {format_date(user.expire_date)}\n"
        )
    
    text += f"\nЗарегистрирован: {format_date(user.created_at)}"
    
    await message.answer(
        text,
        reply_markup=get_user_management_keyboard(telegram_id),
        parse_mode="HTML"
    )

@admin_router.callback_query(F.data.startswith("admin_delete_"))
@admin_only
async def delete_user_callback(callback: CallbackQuery):
    """Удалить пользователя"""
    try:
        telegram_id = int(callback.data.split("_")[2])
    except (IndexError, ValueError):
        await callback.answer("❌ Ошибка получения ID пользователя", show_alert=True)
        return
    user = await db_manager.get_user(telegram_id)
    
    if not user:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return
    
    # Удаляем из Marzban
    if user.marzban_username:
        try:
            await marzban_api.delete_user(user.marzban_username)
        except Exception as e:
            logger.error(f"Failed to delete user from Marzban: {e}")
    
    # Удаляем из БД
    await db_manager.delete_user(telegram_id)
    
    await callback.message.edit_text(
        f"✅ Пользователь {telegram_id} успешно удален"
    )
    await callback.answer()

@admin_router.callback_query(F.data.startswith("admin_suspend_"))
@admin_only
async def suspend_user_callback(callback: CallbackQuery):
    """Приостановить пользователя"""
    try:
        telegram_id = int(callback.data.split("_")[2])
    except (IndexError, ValueError):
        await callback.answer("❌ Ошибка получения ID пользователя", show_alert=True)
        return
    user = await db_manager.get_user(telegram_id)
    
    if not user or not user.marzban_username:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return
    
    try:
        await marzban_api.update_user(user.marzban_username, status="disabled")
        await db_manager.update_user(telegram_id, is_active=False)
        
        await callback.answer("✅ Пользователь приостановлен")
        await callback.message.edit_text(
            f"⏸️ Пользователь {telegram_id} приостановлен\n\n"
            f"Используйте /user {telegram_id} для просмотра информации"
        )
    except Exception as e:
        logger.error(f"Failed to suspend user: {e}")
        await callback.answer("❌ Ошибка при приостановке пользователя", show_alert=True)

@admin_router.callback_query(F.data.startswith("admin_activate_"))
@admin_only
async def activate_user_callback(callback: CallbackQuery):
    """Активировать пользователя"""
    try:
        telegram_id = int(callback.data.split("_")[2])
    except (IndexError, ValueError):
        await callback.answer("❌ Ошибка получения ID пользователя", show_alert=True)
        return
    user = await db_manager.get_user(telegram_id)
    
    if not user or not user.marzban_username:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return
    
    try:
        await marzban_api.update_user(user.marzban_username, status="active")
        await db_manager.update_user(telegram_id, is_active=True)
        
        await callback.answer("✅ Пользователь активирован")
        await callback.message.edit_text(
            f"✅ Пользователь {telegram_id} активирован\n\n"
            f"Используйте /user {telegram_id} для просмотра информации"
        )
    except Exception as e:
        logger.error(f"Failed to activate user: {e}")
        await callback.answer("❌ Ошибка при активации пользователя", show_alert=True)

@admin_router.message(F.text == "📨 Рассылка")
@admin_only
async def broadcast_menu(message: Message, state: FSMContext):
    """Меню рассылки"""
    await state.set_state(AdminStates.waiting_for_broadcast)
    text = (
        "📨 <b>Рассылка сообщений</b>\n\n"
        "Напишите сообщение, которое хотите отправить пользователям.\n"
        "Затем выберите группу получателей.\n\n"
        "Для отмены используйте /cancel"
    )
    await message.answer(text, parse_mode="HTML")

@admin_router.message(AdminStates.waiting_for_broadcast)
@admin_only
async def process_broadcast_message(message: Message, state: FSMContext):
    """Обработка сообщения для рассылки"""
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Рассылка отменена", reply_markup=get_admin_keyboard())
        return
    
    await state.update_data(broadcast_text=message.text)
    
    text = (
        "📨 <b>Подтверждение рассылки</b>\n\n"
        f"Текст сообщения:\n{message.text}\n\n"
        "Кому отправить?"
    )
    
    await message.answer(text, reply_markup=get_broadcast_keyboard(), parse_mode="HTML")

@admin_router.callback_query(F.data.startswith("broadcast_"))
@admin_only
async def process_broadcast(callback: CallbackQuery, state: FSMContext):
    """Обработка рассылки"""
    try:
        action = callback.data.split("_")[1]
    except IndexError:
        await callback.answer("❌ Ошибка обработки команды", show_alert=True)
        return
    
    if action == "cancel":
        await state.clear()
        await callback.message.edit_text("❌ Рассылка отменена")
        return
    
    data = await state.get_data()
    broadcast_text = data.get("broadcast_text")
    
    if not broadcast_text:
        await callback.answer("❌ Текст сообщения не найден", show_alert=True)
        return
    
    # Получаем пользователей
    if action == "all":
        users = await db_manager.get_all_users()
    else:  # active
        users = await db_manager.get_all_users(active_only=True)
    
    await callback.message.edit_text(
        f"📨 Начинаю рассылку {len(users)} пользователям..."
    )
    
    # Отправляем сообщения
    success = 0
    failed = 0
    
    for user in users:
        try:
            await callback.bot.send_message(
                user.telegram_id,
                f"📢 <b>Сообщение от администратора:</b>\n\n{broadcast_text}",
                parse_mode="HTML"
            )
            success += 1
        except Exception as e:
            logger.error(f"Failed to send broadcast to {user.telegram_id}: {e}")
            failed += 1
    
    await state.clear()
    await callback.message.edit_text(
        f"✅ Рассылка завершена!\n\n"
        f"Успешно: {success}\n"
        f"Ошибок: {failed}"
    )

@admin_router.message(F.text == "💬 Сообщения")
@admin_only
async def show_messages(message: Message):
    """Показать непрочитанные сообщения"""
    messages = await db_manager.get_unread_messages()
    
    if not messages:
        await message.answer("✅ Нет непрочитанных сообщений")
        return
    
    text = f"💬 <b>Непрочитанных сообщений: {len(messages)}</b>\n\n"
    
    for msg in messages[:5]:
        user = await db_manager.get_user(msg.from_telegram_id)
        username = f"@{user.username}" if user and user.username else "Без username"
        
        text += (
            f"От: {user.first_name if user else 'Неизвестно'} {username}\n"
            f"ID: <code>{msg.from_telegram_id}</code>\n"
            f"Сообщение: {msg.message_text[:100]}...\n"
            f"Время: {format_date(msg.created_at)}\n\n"
        )
        
        # Отмечаем как прочитанное
        await db_manager.mark_message_read(msg.id)
    
    if len(messages) > 5:
        text += f"...и еще {len(messages) - 5} сообщений"
    
    await message.answer(text, parse_mode="HTML")

@admin_router.message(F.text == "👤 Режим пользователя")
@admin_only
async def user_mode(message: Message):
    """Переключить в режим пользователя"""
    # Проверяем наличие подписки у админа
    user = await db_manager.get_user(message.from_user.id)
    has_subscription = user.marzban_username is not None and user.is_active if user else False
    
    await message.answer(
        "👤 Вы переключены в режим пользователя\n\n"
        "Для возврата используйте /admin",
        reply_markup=get_main_keyboard(has_subscription=has_subscription)
    )

@admin_router.message(F.text == "📋 Логи")
@admin_only
async def show_logs(message: Message):
    """Показать последние логи"""
    try:
        from pathlib import Path
        log_path = Path(settings.LOG_FILE)
        
        if not log_path.exists():
            await message.answer("❌ Файл логов не найден")
            return
        
        with open(log_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            last_lines = lines[-20:] if len(lines) > 20 else lines
            
        log_text = ''.join(last_lines)
        
        # Telegram имеет лимит на длину сообщения (4096 символов)
        if len(log_text) > 4000:
            log_text = log_text[-4000:]
        
        await message.answer(
            f"📋 <b>Последние записи лога:</b>\n\n"
            f"<code>{log_text}</code>",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to read logs: {e}")
        await message.answer("❌ Не удалось прочитать логи")

@admin_router.message(F.text == "⚙️ Управление")
@admin_only
async def show_management(message: Message):
    """Показать меню управления"""
    text = (
        "⚙️ <b>Управление ботом</b>\n\n"
        "Доступные функции:\n"
        "• 📊 Статистика - просмотр статистики\n"
        "• 👥 Пользователи - управление пользователями\n"
        "• 📨 Рассылка - отправка сообщений\n"
        "• 💬 Сообщения - просмотр сообщений от пользователей\n"
        "• 📋 Логи - просмотр логов бота\n\n"
        "Используйте команду /user [telegram_id] для управления конкретным пользователем"
    )
    await message.answer(text, parse_mode="HTML")

@admin_router.callback_query(F.data.startswith("admin_edit_"))
@admin_only
async def edit_user_subscription(callback: CallbackQuery):
    """Редактировать подписку пользователя"""
    try:
        telegram_id = int(callback.data.split("_")[2])
    except (IndexError, ValueError):
        await callback.answer("❌ Ошибка получения ID пользователя", show_alert=True)
        return
    
    user = await db_manager.get_user(telegram_id)
    
    if not user or not user.marzban_username:
        await callback.answer("❌ Пользователь не найден или не имеет подписки", show_alert=True)
        return
    
    text = (
        f"✏️ <b>Редактирование подписки</b>\n\n"
        f"Пользователь: {user.first_name} (@{user.username or 'нет'})\n"
        f"Marzban: <code>{user.marzban_username}</code>\n\n"
        f"Текущие параметры:\n"
        f"• Трафик: {format_bytes(user.data_limit or 0)}\n"
        f"• Истекает: {format_date(user.expire_date)}\n"
        f"• Статус: {'✅ Активна' if user.is_active else '❌ Неактивна'}\n\n"
        f"⚠️ Функция редактирования подписки в разработке.\n"
        f"Используйте API Marzban для ручного редактирования."
    )
    
    await callback.message.edit_text(text, parse_mode="HTML")
    await callback.answer()

@admin_router.callback_query(F.data == "admin_back")
@admin_only
async def admin_back(callback: CallbackQuery):
    """Вернуться в админ панель"""
    await callback.message.delete()
    await callback.answer()
