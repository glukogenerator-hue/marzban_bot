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
from config import settings
from datetime import datetime, timedelta

admin_router = Router()

class AdminStates(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_user_search = State()
    waiting_for_reply = State()
    waiting_for_user_id_search = State()

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
    """Показать список пользователей с кнопками"""
    from keyboards.admin_keyboards import get_users_list_keyboard
    
    users = await db_manager.get_all_users()
    
    if not users:
        await message.answer("❌ Пользователей не найдено")
        return
    
    # Показываем первых 10 пользователей с кнопками
    text = f"👥 <b>Список пользователей</b> (всего: {len(users)})\n\n"
    text += "Выберите пользователя для управления:\n\n"
    
    keyboard_users = []
    for i, user in enumerate(users[:10], 1):
        status = "✅" if user.is_active else "❌"
        username = f"@{user.username}" if user.username else "без username"
        full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "Без имени"
        
        text += (
            f"{i}. {status} {full_name} {username}\n"
            f"   ID: <code>{user.telegram_id}</code>\n\n"
        )
        
        # Добавляем кнопку для каждого пользователя
        button_text = f"{status} {full_name[:20]}"
        keyboard_users.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"admin_user_{user.telegram_id}"
            )
        ])
    
    if len(users) > 10:
        text += f"\n...и еще {len(users) - 10} пользователей\n"
        text += "💡 Используйте /user [telegram_id] для управления остальными пользователями"
    
    await message.answer(
        text,
        reply_markup=get_users_list_keyboard(keyboard_users, len(users) > 10),
        parse_mode="HTML"
    )

async def show_user_info(telegram_id: int, message: Message = None, callback: CallbackQuery = None):
    """Показать информацию о пользователе (вспомогательная функция)"""
    user = await db_manager.get_user(telegram_id)
    
    if not user:
        error_text = f"❌ Пользователь с ID {telegram_id} не найден"
        if callback:
            await callback.answer(error_text, show_alert=True)
        elif message:
            await message.answer(error_text)
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
            f"Трафик: {format_bytes(user.used_traffic or 0)} / {format_bytes(user.data_limit or 0) if user.data_limit else '♾️ Безлимит'}\n"
            f"Истекает: {format_date(user.expire_date)}\n"
        )
    
    text += f"\nЗарегистрирован: {format_date(user.created_at)}"
    
    if callback:
        await callback.message.edit_text(
            text,
            reply_markup=get_user_management_keyboard(telegram_id),
            parse_mode="HTML"
        )
        await callback.answer()
    elif message:
        await message.answer(
            text,
            reply_markup=get_user_management_keyboard(telegram_id),
            parse_mode="HTML"
        )

@admin_router.callback_query(F.data.startswith("admin_user_"))
@admin_only
async def manage_user_callback(callback: CallbackQuery):
    """Управление пользователем через кнопку"""
    try:
        telegram_id = int(callback.data.split("_")[2])
    except (IndexError, ValueError):
        await callback.answer("❌ Ошибка получения ID пользователя", show_alert=True)
        return
    
    await show_user_info(telegram_id, callback=callback)

@admin_router.callback_query(F.data == "admin_users_refresh")
@admin_only
async def refresh_users_list(callback: CallbackQuery):
    """Обновить список пользователей"""
    await callback.answer("🔄 Обновление списка...")
    # Вызываем обработчик показа пользователей
    await show_users(callback.message)
    await callback.message.delete()

@admin_router.callback_query(F.data == "admin_search_user")
@admin_only
async def search_user_by_id(callback: CallbackQuery, state: FSMContext):
    """Поиск пользователя по ID"""
    await state.set_state(AdminStates.waiting_for_user_id_search)
    await callback.message.answer(
        "🔍 <b>Поиск пользователя</b>\n\n"
        "Введите Telegram ID пользователя:\n"
        "(Для отмены используйте /cancel)",
        parse_mode="HTML"
    )
    await callback.answer()

@admin_router.message(AdminStates.waiting_for_user_id_search)
@admin_only
async def process_user_id_search(message: Message, state: FSMContext):
    """Обработка поиска пользователя по ID"""
    if message.text == "/cancel":
        await state.clear()
        from keyboards.admin_keyboards import get_admin_keyboard
        await message.answer("❌ Поиск отменен", reply_markup=get_admin_keyboard())
        return
    
    try:
        telegram_id = int(message.text.strip())
        
        if telegram_id <= 0:
            raise ValueError("Invalid ID")
        
        await state.clear()
        await show_user_info(telegram_id, message=message)
        
    except (ValueError, TypeError):
        await message.answer(
            "❌ Неверный формат ID. Введите число.\n"
            "Пример: 123456789\n\n"
            "Для отмены используйте /cancel"
        )

@admin_router.message(Command("user"))
@admin_only
async def manage_user(message: Message):
    """Управление пользователем через команду"""
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
    
    await show_user_info(telegram_id, message=message)

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
        # Получаем текущий лимит трафика пользователя
        current_data_limit = user.data_limit or 0
        # Если лимит трафика равен 0 (безлимитный) или не установлен, оставляем 0
        # Иначе устанавливаем безлимитный трафик (0) при активации администратором
        # Для платных подписок лучше установить безлимитный трафик
        data_limit = 0  # безлимитный трафик при активации админом
        
        await marzban_api.update_user(
            user.marzban_username,
            status="active",
            data_limit=data_limit
        )
        await db_manager.update_user(
            telegram_id,
            is_active=True,
            data_limit=data_limit
        )
        
        await callback.answer("✅ Пользователь активирован с безлимитным трафиком")
        await callback.message.edit_text(
            f"✅ Пользователь {telegram_id} активирован\n\n"
            f"Лимит трафика: ♾️ Безлимитный\n"
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
    from keyboards.admin_keyboards import get_message_keyboard
    
    messages = await db_manager.get_unread_messages()
    
    if not messages:
        await message.answer("✅ Нет непрочитанных сообщений")
        return
    
    # Показываем сообщения по одному с кнопкой ответа
    for msg in messages[:10]:  # Показываем до 10 сообщений
        user = await db_manager.get_user(msg.from_telegram_id)
        username = f"@{user.username}" if user and user.username else "Без username"
        full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() if user else "Неизвестно"
        
        text = (
            f"💬 <b>Сообщение от пользователя</b>\n\n"
            f"👤 Имя: {full_name}\n"
            f"📱 Username: {username}\n"
            f"🆔 ID: <code>{msg.from_telegram_id}</code>\n"
            f"📅 Время: {format_date(msg.created_at)}\n\n"
            f"💭 Сообщение:\n{msg.message_text}"
        )
        
        # Отмечаем как прочитанное
        await db_manager.mark_message_read(msg.id)
        
        # Отправляем с кнопкой ответа
        await message.answer(
            text,
            reply_markup=get_message_keyboard(msg.from_telegram_id, msg.id),
            parse_mode="HTML"
        )
    
    if len(messages) > 10:
        await message.answer(f"📬 ...и еще {len(messages) - 10} сообщений")

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
        import aiofiles
        from pathlib import Path
        
        log_path = Path(settings.LOG_FILE)
        
        if not log_path.exists():
            await message.answer("❌ Файл логов не найден")
            return
        
        # Асинхронное чтение файла
        async with aiofiles.open(log_path, 'r', encoding='utf-8') as f:
            lines = await f.readlines()
            last_lines = lines[-30:] if len(lines) > 30 else lines
            
        log_text = ''.join(last_lines)
        
        # Telegram имеет лимит на длину сообщения (4096 символов)
        if len(log_text) > 4000:
            log_text = log_text[-4000:]
            log_text = "... (показаны последние 4000 символов)\n\n" + log_text
        
        if not log_text.strip():
            await message.answer("📋 Лог файл пуст")
            return
        
        await message.answer(
            f"📋 <b>Последние записи лога ({len(last_lines)} строк):</b>\n\n"
            f"<code>{log_text}</code>",
            parse_mode="HTML"
        )
    except ImportError:
        # Если aiofiles не установлен, используем обычное чтение
        try:
            from pathlib import Path
            log_path = Path(settings.LOG_FILE)
            
            if not log_path.exists():
                await message.answer("❌ Файл логов не найден")
                return
            
            with open(log_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                last_lines = lines[-30:] if len(lines) > 30 else lines
                
            log_text = ''.join(last_lines)
            
            if len(log_text) > 4000:
                log_text = log_text[-4000:]
                log_text = "... (показаны последние 4000 символов)\n\n" + log_text
            
            if not log_text.strip():
                await message.answer("📋 Лог файл пуст")
                return
            
            await message.answer(
                f"📋 <b>Последние записи лога ({len(last_lines)} строк):</b>\n\n"
                f"<code>{log_text}</code>",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to read logs: {e}")
            await message.answer(f"❌ Не удалось прочитать логи: {e}")
    except Exception as e:
        logger.error(f"Failed to read logs: {e}")
        await message.answer(f"❌ Не удалось прочитать логи: {e}")

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
    
    # Получаем актуальную информацию из Marzban
    try:
        usage = await marzban_api.get_user_usage(user.marzban_username)
        
        # Обновляем данные в БД
        await db_manager.update_user(
            user.telegram_id,
            used_traffic=usage['used_traffic'],
            is_active=(usage['status'] == 'active')
        )
        
        expire_date = datetime.fromtimestamp(usage['expire']) if usage.get('expire') else user.expire_date
        data_limit = usage.get('data_limit', 0) or user.data_limit or 0
        
        from keyboards.admin_keyboards import get_subscription_edit_keyboard
        
        text = (
            f"✏️ <b>Редактирование подписки</b>\n\n"
            f"Пользователь: {user.first_name or 'Не указано'} (@{user.username or 'нет'})\n"
            f"Marzban: <code>{user.marzban_username}</code>\n\n"
            f"Текущие параметры:\n"
            f"• Трафик: {format_bytes(data_limit) if data_limit else '♾️ Безлимит'}\n"
            f"• Использовано: {format_bytes(usage.get('used_traffic', 0))}\n"
            f"• Истекает: {format_date(expire_date)}\n"
            f"• Статус: {'✅ Активна' if usage.get('status') == 'active' else '❌ Неактивна'}\n\n"
            f"Выберите действие:"
        )
        
        try:
            await callback.message.edit_text(
                text,
                reply_markup=get_subscription_edit_keyboard(telegram_id),
                parse_mode="HTML"
            )
        except Exception as edit_error:
            # Если сообщение не изменилось, это не критичная ошибка
            error_msg = str(edit_error).lower()
            if "message is not modified" in error_msg or "message_not_modified" in error_msg:
                # Данные не изменились, просто подтверждаем
                pass
            else:
                # Другая ошибка - отправляем новое сообщение
                await callback.message.answer(
                    text,
                    reply_markup=get_subscription_edit_keyboard(telegram_id),
                    parse_mode="HTML"
                )
        
        await callback.answer("✅ Информация обновлена")
        
    except Exception as e:
        logger.error(f"Failed to get user usage for edit: {e}")
        # Показываем информацию из БД если не удалось получить из Marzban
        from keyboards.admin_keyboards import get_subscription_edit_keyboard
        
        text = (
            f"✏️ <b>Редактирование подписки</b>\n\n"
            f"Пользователь: {user.first_name or 'Не указано'} (@{user.username or 'нет'})\n"
            f"Marzban: <code>{user.marzban_username}</code>\n\n"
            f"Текущие параметры (из БД):\n"
            f"• Трафик: {format_bytes(user.data_limit or 0) if user.data_limit else '♾️ Безлимит'}\n"
            f"• Использовано: {format_bytes(user.used_traffic or 0)}\n"
            f"• Истекает: {format_date(user.expire_date)}\n"
            f"• Статус: {'✅ Активна' if user.is_active else '❌ Неактивна'}\n\n"
            f"Выберите действие:"
        )
        
        try:
            await callback.message.edit_text(
                text,
                reply_markup=get_subscription_edit_keyboard(telegram_id),
                parse_mode="HTML"
            )
        except Exception as edit_error:
            error_msg = str(edit_error).lower()
            if "message is not modified" not in error_msg and "message_not_modified" not in error_msg:
                await callback.message.answer(
                    text,
                    reply_markup=get_subscription_edit_keyboard(telegram_id),
                    parse_mode="HTML"
                )
        
        await callback.answer("⚠️ Использованы данные из БД")

@admin_router.callback_query(F.data.startswith("admin_extend_"))
@admin_only
async def extend_user_subscription(callback: CallbackQuery):
    """Продлить подписку пользователя"""
    try:
        parts = callback.data.split("_")
        telegram_id = int(parts[2])
        days = int(parts[3])
    except (IndexError, ValueError):
        await callback.answer("❌ Ошибка получения данных", show_alert=True)
        return
    
    user = await db_manager.get_user(telegram_id)
    
    if not user or not user.marzban_username:
        await callback.answer("❌ Пользователь не найден или не имеет подписки", show_alert=True)
        return
    
    try:
        # Получаем текущую информацию из Marzban
        usage = await marzban_api.get_user_usage(user.marzban_username)
        current_expire = usage.get('expire', 0)
        current_data_limit = usage.get('data_limit', 0) or user.data_limit or 0
        
        # Вычисляем новую дату истечения
        if current_expire:
            current_expire_dt = datetime.fromtimestamp(current_expire)
            # Если подписка уже истекла, начинаем с текущей даты
            if current_expire_dt < datetime.utcnow():
                new_expire = datetime.utcnow() + timedelta(days=days)
            else:
                # Продлеваем от текущей даты истечения
                new_expire = current_expire_dt + timedelta(days=days)
        else:
            # Если нет даты истечения, начинаем с текущей даты
            new_expire = datetime.utcnow() + timedelta(days=days)
        
        new_expire_timestamp = int(new_expire.timestamp())
        
        # Обновляем в Marzban через прямой запрос с timestamp
        token = await marzban_api._get_token()
        headers = {"Authorization": f"Bearer {token}"}
        session = await marzban_api._get_session()
        
        async with session.put(
            f"{marzban_api.base_url}/api/user/{user.marzban_username}",
            headers=headers,
            json={
                "expire": new_expire_timestamp,
                "status": "active",
                "data_limit": current_data_limit  # Сохраняем текущий лимит трафика
            }
        ) as resp:
            if resp.status not in [200, 201]:
                error_text = await resp.text()
                raise Exception(f"Failed to update expire: {resp.status} - {error_text}")
        
        # Обновляем в БД
        await db_manager.update_user(
            user.telegram_id,
            expire_date=new_expire,
            is_active=True,
            data_limit=current_data_limit
        )
        
        await callback.answer(f"✅ Подписка продлена на {days} дней!")
        
        # Обновляем информацию о пользователе
        await show_user_info(telegram_id, callback=callback)
        
    except Exception as e:
        logger.error(f"Failed to extend subscription: {e}")
        await callback.answer(f"❌ Не удалось продлить подписку: {str(e)[:50]}", show_alert=True)

@admin_router.callback_query(F.data == "admin_back")
@admin_only
async def admin_back(callback: CallbackQuery):
    """Вернуться в админ панель"""
    await callback.message.delete()
    await callback.answer()

@admin_router.callback_query(F.data.startswith("reply_to_"))
@admin_only
async def start_reply_to_user(callback: CallbackQuery, state: FSMContext):
    """Начать ответ пользователю"""
    try:
        parts = callback.data.split("_")
        user_telegram_id = int(parts[2])
        message_id = int(parts[3]) if len(parts) > 3 else None
    except (IndexError, ValueError):
        await callback.answer("❌ Ошибка получения данных", show_alert=True)
        return
    
    user = await db_manager.get_user(user_telegram_id)
    if not user:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return
    
    # Сохраняем данные в состоянии
    await state.update_data(
        reply_to_user_id=user_telegram_id,
        reply_to_message_id=message_id
    )
    await state.set_state(AdminStates.waiting_for_reply)
    
    username = f"@{user.username}" if user.username else "без username"
    text = (
        f"💬 <b>Ответ пользователю</b>\n\n"
        f"👤 Получатель: {user.first_name or 'Неизвестно'} {username}\n"
        f"🆔 ID: <code>{user_telegram_id}</code>\n\n"
        f"✏️ Напишите ваш ответ:\n"
        f"(Для отмены используйте /cancel)"
    )
    
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

@admin_router.callback_query(F.data.startswith("mark_read_"))
@admin_only
async def mark_message_read_callback(callback: CallbackQuery):
    """Отметить сообщение прочитанным"""
    try:
        message_id = int(callback.data.split("_")[2])
    except (IndexError, ValueError):
        await callback.answer("❌ Ошибка получения ID сообщения", show_alert=True)
        return
    
    success = await db_manager.mark_message_read(message_id)
    if success:
        await callback.answer("✅ Сообщение отмечено как прочитанное")
        # Обновляем сообщение, убирая кнопку
        try:
            text = callback.message.text or callback.message.caption or ""
            await callback.message.edit_text(text, parse_mode="HTML")
        except:
            pass
    else:
        await callback.answer("❌ Не удалось отметить сообщение", show_alert=True)

@admin_router.message(AdminStates.waiting_for_reply)
@admin_only
async def process_reply_to_user(message: Message, state: FSMContext):
    """Обработка ответа пользователю"""
    if message.text == "/cancel":
        await state.clear()
        from keyboards.admin_keyboards import get_admin_keyboard
        await message.answer("❌ Ответ отменен", reply_markup=get_admin_keyboard())
        return
    
    data = await state.get_data()
    user_telegram_id = data.get("reply_to_user_id")
    reply_to_message_id = data.get("reply_to_message_id")
    
    if not user_telegram_id:
        await message.answer("❌ Ошибка: не найден получатель")
        await state.clear()
        return
    
    # Валидация сообщения
    if not message.text or len(message.text.strip()) == 0:
        await message.answer("❌ Сообщение не может быть пустым. Попробуйте еще раз или используйте /cancel")
        return
    
    if len(message.text) > 4000:
        await message.answer("❌ Сообщение слишком длинное (максимум 4000 символов). Попробуйте еще раз или используйте /cancel")
        return
    
    try:
        # Отправляем сообщение пользователю
        await message.bot.send_message(
            user_telegram_id,
            f"💬 <b>Ответ от администратора:</b>\n\n{message.text}",
            parse_mode="HTML"
        )
        
        # Сохраняем ответ в БД
        await db_manager.create_message(
            from_telegram_id=message.from_user.id,
            message_text=message.text,
            to_telegram_id=user_telegram_id
        )
        
        user = await db_manager.get_user(user_telegram_id)
        username = f"@{user.username}" if user and user.username else "без username"
        
        from keyboards.admin_keyboards import get_admin_keyboard
        await message.answer(
            f"✅ Ответ отправлен пользователю {user.first_name if user else 'Неизвестно'} {username}",
            reply_markup=get_admin_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Failed to send reply to user {user_telegram_id}: {e}")
        from keyboards.admin_keyboards import get_admin_keyboard
        await message.answer(
            f"❌ Не удалось отправить ответ: {e}\n\n"
            f"Возможно, пользователь заблокировал бота.",
            reply_markup=get_admin_keyboard()
        )
    
    await state.clear()
