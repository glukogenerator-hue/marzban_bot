from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, FSInputFile, BufferedInputFile
from database.db_manager import db_manager
from marzban.api_client import marzban_api
from keyboards.user_keyboards import *
from utils.helpers import *
from utils.decorators import user_registered
from utils.logger import logger
from config import settings
from datetime import datetime, timedelta

user_router = Router()

class UserStates(StatesGroup):
    waiting_for_message = State()

@user_router.message(Command("start"))
async def cmd_start(message: Message):
    """Команда /start"""
    user = await db_manager.get_user(message.from_user.id)
    
    if not user:
        # Создаем нового пользователя
        user = await db_manager.create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name
        )
        
        welcome_text = (
            f"👋 Добро пожаловать, {message.from_user.first_name}!\n\n"
            f"Вы успешно зарегистрированы в системе.\n"
            f"Используйте меню ниже для управления подпиской."
        )
    else:
        welcome_text = (
            f"👋 С возвращением, {message.from_user.first_name}!\n\n"
            f"Используйте меню для управления подпиской."
        )
    
    # Проверяем наличие активной подписки
    has_subscription = user.marzban_username is not None and user.is_active
    
    await message.answer(welcome_text, reply_markup=get_main_keyboard(has_subscription=has_subscription))

@user_router.message(F.text == "📊 Моя подписка")
@user_registered
async def show_subscription(message: Message):
    """Показать информацию о подписке"""
    user = await db_manager.get_user(message.from_user.id)
    
    if not user.marzban_username:
        text = (
            "❌ У вас еще нет активной подписки.\n\n"
            "Вы можете:\n"
            "🎁 Получить тестовый доступ на 3 дня\n"
            "💳 Купить полную подписку"
        )
        await message.answer(text, reply_markup=get_subscription_keyboard(user.trial_used, has_active_subscription=False))
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
        
        status_emoji = "✅" if usage['status'] == 'active' else "❌"
        used_traffic = format_bytes(usage['used_traffic'])
        total_traffic = format_bytes(usage['data_limit'])
        traffic_percent = get_traffic_percentage(usage['used_traffic'], usage['data_limit'])
        
        expire_date = datetime.fromtimestamp(usage['expire'])
        days_left = calculate_expire_days(expire_date)
        
        text = (
            f"📊 <b>Ваша подписка</b>\n\n"
            f"Статус: {status_emoji} {usage['status']}\n"
            f"Пользователь: <code>{user.marzban_username}</code>\n\n"
            f"📈 Трафик: {used_traffic} / {total_traffic} ({traffic_percent:.1f}%)\n"
            f"📅 Действует до: {format_date(expire_date)}\n"
            f"⏳ Осталось дней: {days_left}\n"
        )
        
        if user.trial_used and days_left <= 3:
            text += "\n⚠️ Подписка скоро истечет! Рекомендуем продлить."
        
    except Exception as e:
        logger.error(f"Failed to get user usage: {e}")
        text = "❌ Не удалось получить информацию о подписке. Попробуйте позже."
    
    await message.answer(text, reply_markup=get_subscription_keyboard(user.trial_used, has_active_subscription=True), parse_mode="HTML")

@user_router.callback_query(F.data == "get_trial")
@user_registered
async def get_trial_access(callback: CallbackQuery):
    """Получить тестовый доступ"""
    user = await db_manager.get_user(callback.from_user.id)
    
    if not user:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return
    
    if user.trial_used:
        await callback.answer("❌ Вы уже использовали тестовый доступ", show_alert=True)
        return
    
    if user.marzban_username:
        await callback.answer("❌ У вас уже есть активная подписка", show_alert=True)
        return
    
    try:
        # Создаем пользователя в Marzban
        username = generate_username(user.telegram_id)
        marzban_user = await marzban_api.create_user(
            username=username,
            data_limit=settings.TRIAL_DATA_LIMIT,
            expire_days=settings.TRIAL_EXPIRE_DAYS
        )
        
        # Обновляем данные в БД
        subscription_url = marzban_user.get('subscription_url', '')
        expire_date = datetime.utcnow() + timedelta(days=settings.TRIAL_EXPIRE_DAYS)
        
        await db_manager.update_user(
            user.telegram_id,
            marzban_username=username,
            subscription_url=subscription_url,
            trial_used=True,
            is_active=True,
            data_limit=settings.TRIAL_DATA_LIMIT,
            expire_date=expire_date
        )
        
        text = (
            f"🎉 <b>Тестовый доступ активирован!</b>\n\n"
            f"Ваши данные:\n"
            f"Пользователь: <code>{username}</code>\n"
            f"📊 Трафик: {format_bytes(settings.TRIAL_DATA_LIMIT)}\n"
            f"Срок действия: {settings.TRIAL_EXPIRE_DAYS} дней\n\n"
            f"Используйте меню '🔗 Подключение' для получения ссылки подписки."
        )
        
        await callback.message.edit_text(text, parse_mode="HTML")
        await callback.answer("✅ Тестовый доступ активирован!")
        
    except Exception as e:
        logger.error(f"Failed to create trial user: {e}")
        await callback.answer("❌ Не удалось создать тестовый доступ", show_alert=True)

@user_router.message(F.text == "🔗 Подключение")
@user_registered
async def show_connection(message: Message):
    """Показать информацию о подключении"""
    user = await db_manager.get_user(message.from_user.id)
    
    if not user.subscription_url:
        await message.answer("❌ У вас нет активной подписки")
        return
    
    text = (
        f"🔗 <b>Подключение к VPN</b>\n\n"
        f"Ваша ссылка подписки:\n"
        f"<code>{user.subscription_url}</code>\n\n"
        f"Выберите действие:"
    )
    
    await message.answer(text, reply_markup=get_connection_keyboard(), parse_mode="HTML")

@user_router.callback_query(F.data == "get_qr")
@user_registered
async def send_qr_code(callback: CallbackQuery):
    """Отправить QR код"""
    user = await db_manager.get_user(callback.from_user.id)
    
    if not user.subscription_url:
        await callback.answer("❌ У вас нет активной подписки", show_alert=True)
        return
    
    try:
        qr_code = generate_qr_code(user.subscription_url)
        photo = BufferedInputFile(qr_code.read(), filename="qrcode.png")
        
        await callback.message.answer_photo(
            photo=photo,
            caption="📱 Отсканируйте QR код в приложении VPN клиента"
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Failed to generate QR code: {e}")
        await callback.answer("❌ Не удалось создать QR код", show_alert=True)

@user_router.callback_query(F.data == "copy_link")
@user_registered
async def copy_link(callback: CallbackQuery):
    """Скопировать ссылку"""
    user = await db_manager.get_user(callback.from_user.id)
    
    if not user.subscription_url:
        await callback.answer("❌ У вас нет активной подписки", show_alert=True)
        return
    
    await callback.answer("✅ Ссылка скопирована в буфер обмена!")
    await callback.message.answer(
        f"Ваша ссылка:\n<code>{user.subscription_url}</code>",
        parse_mode="HTML"
    )

@user_router.message(F.text == "💳 Купить подписку")
@user_registered
async def buy_subscription(message: Message):
    """Купить подписку"""
    text = (
        "💳 <b>Тарифные планы</b>\n\n"
        "Выберите подходящий тариф:"
    )
    await message.answer(text, reply_markup=get_plans_keyboard(), parse_mode="HTML")

@user_router.message(F.text == "💬 Написать админу")
@user_registered
async def write_to_admin(message: Message, state: FSMContext):
    """Написать админу"""
    await state.set_state(UserStates.waiting_for_message)
    await message.answer(
        "✏️ Напишите ваше сообщение администратору:\n"
        "(Для отмены используйте /cancel)"
    )

@user_router.message(UserStates.waiting_for_message)
async def process_admin_message(message: Message, state: FSMContext):
    """Обработка сообщения админу"""
    if message.text == "/cancel":
        await state.clear()
        user = await db_manager.get_user(message.from_user.id)
        has_subscription = user.marzban_username is not None and user.is_active if user else False
        await message.answer("❌ Отменено", reply_markup=get_main_keyboard(has_subscription=has_subscription))
        return
    
    # Валидация сообщения
    if not message.text or len(message.text.strip()) == 0:
        await message.answer("❌ Сообщение не может быть пустым. Попробуйте еще раз или используйте /cancel")
        return
    
    if len(message.text) > 4000:
        await message.answer("❌ Сообщение слишком длинное (максимум 4000 символов). Попробуйте еще раз или используйте /cancel")
        return
    
    # Сохраняем сообщение в БД
    await db_manager.create_message(
        from_telegram_id=message.from_user.id,
        message_text=message.text
    )
    
    # Уведомляем админов
    for admin_id in settings.ADMIN_IDS:
        try:
            await message.bot.send_message(
                admin_id,
                f"📨 <b>Новое сообщение от пользователя</b>\n\n"
                f"От: {message.from_user.full_name} (@{message.from_user.username})\n"
                f"ID: <code>{message.from_user.id}</code>\n\n"
                f"Сообщение:\n{message.text}",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")
    
    await state.clear()
    user = await db_manager.get_user(message.from_user.id)
    has_subscription = user.marzban_username is not None and user.is_active if user else False
    await message.answer(
        "✅ Ваше сообщение отправлено администратору!",
        reply_markup=get_main_keyboard(has_subscription=has_subscription)
    )

@user_router.message(F.text == "⚙️ Настройки")
@user_registered
async def show_settings(message: Message):
    """Показать настройки"""
    user = await db_manager.get_user(message.from_user.id)
    
    notifications_status = "✅ Включены" if user.notifications_enabled else "❌ Выключены"
    expire_status = "✅ Включены" if user.notify_on_expire else "❌ Выключены"
    
    text = (
        f"⚙️ <b>Настройки</b>\n\n"
        f"🔔 Уведомления: {notifications_status}\n"
        f"⏰ Уведомления об истечении: {expire_status}\n"
        f"Выберите настройку для изменения:"
    )
    
    await message.answer(text, reply_markup=get_settings_keyboard(), parse_mode="HTML")

@user_router.callback_query(F.data == "settings_back")
@user_registered
async def settings_back(callback: CallbackQuery):
    """Вернуться из настроек"""
    await callback.message.edit_text("⚙️ Настройки закрыты")
    await callback.answer()

@user_router.callback_query(F.data == "settings_notifications")
@user_registered
async def toggle_notifications(callback: CallbackQuery):
    """Переключить уведомления"""
    user = await db_manager.get_user(callback.from_user.id)
    new_value = not user.notifications_enabled
    await db_manager.update_user(callback.from_user.id, notifications_enabled=new_value)
    
    status = "включены" if new_value else "выключены"
    await callback.answer(f"✅ Уведомления {status}")
    
    # Обновляем сообщение
    user = await db_manager.get_user(callback.from_user.id)
    notifications_status = "✅ Включены" if user.notifications_enabled else "❌ Выключены"
    expire_status = "✅ Включены" if user.notify_on_expire else "❌ Выключены"
    
    text = (
        f"⚙️ <b>Настройки</b>\n\n"
        f"🔔 Уведомления: {notifications_status}\n"
        f"⏰ Уведомления об истечении: {expire_status}\n"
        f"Выберите настройку для изменения:"
    )
    
    await callback.message.edit_text(text, reply_markup=get_settings_keyboard(), parse_mode="HTML")

@user_router.callback_query(F.data == "settings_expire")
@user_registered
async def toggle_expire_notifications(callback: CallbackQuery):
    """Переключить уведомления об истечении"""
    user = await db_manager.get_user(callback.from_user.id)
    new_value = not user.notify_on_expire
    await db_manager.update_user(callback.from_user.id, notify_on_expire=new_value)
    
    status = "включены" if new_value else "выключены"
    await callback.answer(f"✅ Уведомления об истечении {status}")
    
    # Обновляем сообщение
    user = await db_manager.get_user(callback.from_user.id)
    notifications_status = "✅ Включены" if user.notifications_enabled else "❌ Выключены"
    expire_status = "✅ Включены" if user.notify_on_expire else "❌ Выключены"
    
    text = (
        f"⚙️ <b>Настройки</b>\n\n"
        f"🔔 Уведомления: {notifications_status}\n"
        f"⏰ Уведомления об истечении: {expire_status}\n"
        f"Выберите настройку для изменения:"
    )
    
    await callback.message.edit_text(text, reply_markup=get_settings_keyboard(), parse_mode="HTML")

@user_router.callback_query(F.data == "refresh_subscription")
@user_registered
async def refresh_subscription(callback: CallbackQuery):
    """Обновить информацию о подписке"""
    user = await db_manager.get_user(callback.from_user.id)
    
    if not user.marzban_username:
        await callback.answer("❌ У вас нет активной подписки", show_alert=True)
        return
    
    try:
        usage = await marzban_api.get_user_usage(user.marzban_username)
        
        await db_manager.update_user(
            user.telegram_id,
            used_traffic=usage['used_traffic'],
            is_active=(usage['status'] == 'active')
        )
        
        await callback.answer("✅ Информация обновлена!")
        
        # Показываем обновленную информацию
        status_emoji = "✅" if usage['status'] == 'active' else "❌"
        used_traffic = format_bytes(usage['used_traffic'])
        total_traffic = format_bytes(usage['data_limit'])
        traffic_percent = get_traffic_percentage(usage['used_traffic'], usage['data_limit'])
        
        expire_date = datetime.fromtimestamp(usage['expire'])
        days_left = calculate_expire_days(expire_date)
        
        text = (
            f"📊 <b>Ваша подписка</b>\n\n"
            f"Статус: {status_emoji} {usage['status']}\n"
            f"Пользователь: <code>{user.marzban_username}</code>\n\n"
            f"📅 Действует до: {format_date(expire_date)}\n"
            f"⏳ Осталось дней: {days_left}\n"
        )
        
        try:
            await callback.message.edit_text(text, reply_markup=get_subscription_keyboard(user.trial_used, has_active_subscription=True), parse_mode="HTML")
        except Exception as edit_error:
            # Если сообщение не изменилось, это не критичная ошибка
            error_msg = str(edit_error).lower()
            if "message is not modified" in error_msg or "message_not_modified" in error_msg:
                # Данные не изменились, просто подтверждаем обновление
                pass
            else:
                # Другая ошибка - логируем
                logger.warning(f"Failed to edit message: {edit_error}")
        
    except Exception as e:
        logger.error(f"Failed to refresh subscription: {e}")
        await callback.answer("❌ Не удалось обновить информацию", show_alert=True)

@user_router.callback_query(F.data == "connection_settings")
@user_registered
async def show_connection_settings(callback: CallbackQuery):
    """Показать настройки подключения"""
    user = await db_manager.get_user(callback.from_user.id)
    
    if not user.subscription_url:
        await callback.answer("❌ У вас нет активной подписки", show_alert=True)
        return
    
    text = (
        f"🔗 <b>Подключение к VPN</b>\n\n"
        f"Ваша ссылка подписки:\n"
        f"<code>{user.subscription_url}</code>\n\n"
        f"Выберите действие:"
    )
    
    await callback.message.edit_text(text, reply_markup=get_connection_keyboard(), parse_mode="HTML")
    await callback.answer()

@user_router.callback_query(F.data == "go_to_subscription")
@user_registered
async def go_to_subscription(callback: CallbackQuery):
    """Перейти к подписке после успешного платежа"""
    user = await db_manager.get_user(callback.from_user.id)
    
    if not user.marzban_username:
        text = (
            "❌ У вас еще нет активной подписки.\n\n"
            "Вы можете:\n"
            "🎁 Получить тестовый доступ на 7 дней\n"
            "💳 Купить полную подписку"
        )
        await callback.message.edit_text(text, reply_markup=get_subscription_keyboard(user.trial_used, has_active_subscription=False))
    else:
        # Получаем актуальную информацию из Marzban
        try:
            usage = await marzban_api.get_user_usage(user.marzban_username)
            
            await db_manager.update_user(
                user.telegram_id,
                used_traffic=usage['used_traffic'],
                is_active=(usage['status'] == 'active')
            )
            
            status_emoji = "✅" if usage['status'] == 'active' else "❌"
            used_traffic = format_bytes(usage['used_traffic'])
            total_traffic = format_bytes(usage['data_limit'])
            traffic_percent = get_traffic_percentage(usage['used_traffic'], usage['data_limit'])
            
            expire_date = datetime.fromtimestamp(usage['expire'])
            days_left = calculate_expire_days(expire_date)
            
            text = (
                f"📊 <b>Ваша подписка</b>\n\n"
                f"Статус: {status_emoji} {usage['status']}\n"
                f"Пользователь: <code>{user.marzban_username}</code>\n\n"
                f"📅 Действует до: {format_date(expire_date)}\n"
                f"⏳ Осталось дней: {days_left}\n"
            )
            
            if user.trial_used and days_left <= 3:
                text += "\n⚠️ Подписка скоро истечет! Рекомендуем продлить."
                
        except Exception as e:
            logger.error(f"Failed to get user usage: {e}")
            text = "❌ Не удалось получить информацию о подписке. Попробуйте позже."
        
        await callback.message.edit_text(text, reply_markup=get_subscription_keyboard(user.trial_used, has_active_subscription=True), parse_mode="HTML")
    
    await callback.answer()

@user_router.callback_query(F.data.startswith("buy_plan_"))
@user_registered
async def buy_plan(callback: CallbackQuery):
    """Обработка покупки плана"""
    plan_id = callback.data.split("_")[-1]
    
    if plan_id not in settings.SUBSCRIPTION_PLANS:
        await callback.answer("❌ Неверный план", show_alert=True)
        return
    
    plan = settings.SUBSCRIPTION_PLANS[plan_id]
    
    # Проверяем, включена ли платежная система
    if not settings.TELEGRAM_STARS_ENABLED:
        # Платежная система отключена
        text = (
            f"💳 <b>План: {plan_id} месяц(а/ев)</b>\n\n"
            f"📅 Срок: {plan['days']} дней\n"
            f"💰 Цена: {plan['price']}₽\n"
            f"♾️ Безлимитный трафик\n\n"
            f"⚠️ Платежная система пока не настроена.\n"
            f"Обратитесь к администратору для покупки подписки."
        )
        keyboard = None
    else:
        # Платежная система включена - показываем информацию об оплате
        # Для тестирования всегда 1 звезда
        stars_amount = 1
        
        text = (
            f"💳 <b>План: {plan_id} месяц(а/ев)</b>\n\n"
            f"📅 Срок: {plan['days']} дней\n"
            f"💰 Цена: {plan['price']}₽ ({stars_amount} ⭐️)\n"
            f"♾️ Безлимитный трафик\n\n"
            f"💡 <i>Оплата производится только Telegram Stars</i>\n\n"
            f"Нажмите кнопку ниже, чтобы начать оплату."
        )
        
        # Создаем клавиатуру с кнопкой для оплаты
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"💳 Оплатить {plan['price']}₽",
                        callback_data=f"start_payment_{plan_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔙 Назад к планам",
                        callback_data="show_plans"
                    )
                ]
            ]
        )
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()

@user_router.callback_query(F.data == "show_plans")
@user_registered
async def show_plans_callback(callback: CallbackQuery):
    """Показать список планов"""
    text = (
        "💳 <b>Тарифные планы</b>\n\n"
        "Выберите подходящий тариф:\n\n"
        "⚠️ <i>В настоящее время доступна только оплата Telegram Stars</i>"
    )
    from keyboards.user_keyboards import get_plans_keyboard
    await callback.message.edit_text(text, reply_markup=get_plans_keyboard(), parse_mode="HTML")
    await callback.answer()

@user_router.callback_query(F.data == "plans_back")
@user_registered
async def plans_back(callback: CallbackQuery):
    """Вернуться из планов"""
    await callback.message.delete()
    await callback.answer()

@user_router.callback_query(F.data == "instructions")
@user_registered
async def show_instructions(callback: CallbackQuery):
    """Показать инструкции по подключению"""
    text = (
        "📖 <b>Инструкции по подключению</b>\n\n"
        "<b>1. Скачайте VPN клиент:</b>\n"
        "• <b>Android:</b> v2rayNG (https://github.com/2dust/v2rayNG), Clash for Android (https://github.com/Kr328/ClashForAndroid)\n"
        "• <b>iOS:</b> Shadowrocket (App Store), Clash (TestFlight)\n"
        "• <b>Windows:</b> v2rayN (https://github.com/2dust/v2rayN), Clash for Windows (https://github.com/Fndroid/clash_for_windows_pkg)\n"
        "• <b>macOS:</b> ClashX (https://github.com/yichengchen/clashX), v2rayU (https://github.com/yanue/V2rayU)\n"
        "• <b>Linux:</b> Qv2ray (https://github.com/Qv2ray/Qv2ray), Clash (https://github.com/Dreamacro/clash)\n\n"
        "<b>2. Установите и откройте приложение</b>\n\n"
        "<b>3. Добавьте подписку:</b>\n"
        "   • Найдите кнопку 'Добавить подписку', 'Import from URL' или аналогичную\n"
        "   • Вставьте ссылку подписки (можно получить в разделе 'Моя подписка' → 'Настройка подключения')\n"
        "   • Или отсканируйте QR код (также доступен в настройках подключения)\n\n"
        "<b>4. Активируйте подключение:</b>\n"
        "   • Выберите добавленный сервер в списке\n"
        "   • Включите VPN (переключите тумблер)\n"
        "   • Дождитесь установки соединения\n\n"
        "<b>🔧 Устранение неполадок:</b>\n"
        "• <b>Нет подключения:</b> Проверьте интернет, перезапустите VPN клиент, обновите подписку\n"
        "• <b>Подписка не работает:</b> Убедитесь, что подписка активна и не истекла\n"
        "• <b>Медленная скорость:</b> Попробуйте другой сервер (если доступно) или переключите протокол\n"
        "• <b>Ошибка импорта:</b> Скопируйте ссылку заново, проверьте её корректность\n\n"
        "<b>💡 Полезное:</b>\n"
        "• Регулярно обновляйте VPN клиент для лучшей совместимости\n"
        "• Используйте QR код для быстрого подключения на мобильных устройствах\n"
        "• Настройте уведомления об истечении подписки в меню '⚙️ Настройки'\n\n"
        "Если проблемы остаются, напишите администратору через меню '💬 Написать админу'."
    )
    
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

@user_router.message(F.text == "🔄 Продлить подписку")
@user_registered
async def renew_subscription(message: Message):
    """Продлить подписку"""
    user = await db_manager.get_user(message.from_user.id)
    
    if not user.marzban_username:
        await message.answer("❌ У вас нет активной подписки")
        # Обновляем клавиатуру, так как подписки нет
        await message.answer(
            "Используйте меню ниже:",
            reply_markup=get_main_keyboard(has_subscription=False)
        )
        return
    
    text = (
        "🔄 <b>Продление подписки</b>\n\n"
        "Выберите срок продления:"
    )
    
    await message.answer(text, reply_markup=get_plans_keyboard(), parse_mode="HTML")

@user_router.message(F.text == "ℹ️ Помощь")
@user_registered
async def show_help(message: Message):
    """Показать справку"""
    text = (
        "ℹ️ <b>Справка</b>\n\n"
        "<b>Меню:</b>\n"
        "📊 Моя подписка - информация о вашей подписке (включая настройку подключения)\n"
        "💳 Купить подписку - выбрать тарифный план\n"
        "🔄 Продлить подписку - продлить текущую подписку\n"
        "⚙️ Настройки - настройки уведомлений\n"
        "💬 Написать админу - связаться с администратором\n\n"
        "<b>📱 Рекомендуемые VPN клиенты:</b>\n"
        "• <b>Android:</b> Hiddify v2rayNG, Clash for Android\n"
        "• <b>iOS:</b> Shadowrocket, Clash\n"
        "• <b>Windows:</b> v2rayN, Clash for Windows\n"
        "• <b>macOS:</b> ClashX, v2rayU\n"
        "• <b>Linux:</b> Qv2ray, Clash\n\n"
        "<b>💡 Полезные советы:</b>\n"
        "1. Для подключения используйте ссылку подписки или QR код из раздела 'Моя подписка' → 'Настройка подключения'.\n"
        "2. Уведомления об истечении подписки можно настроить в меню '⚙️ Настройки'.\n"
        "3. При проблемах с подключением перезапустите VPN клиент и обновите подписку.\n"
        "4. Тестовый доступ предоставляется на 7 дней с ограниченным трафиком.\n"
        "5. Для экономии трафика отключайте VPN при загрузке больших файлов или просмотре локального контента.\n"
        "6. Используйте режим 'Split Tunneling' (если поддерживается клиентом) для выбора приложений, работающих через VPN.\n"
        "7. Регулярно проверяйте обновления VPN клиента для улучшения безопасности и скорости.\n"
        "8. При блокировке VPN попробуйте сменить протокол подключения в настройках клиента.\n\n"
        "<b>📊 Проверка скорости:</b>\n"
        "• Используйте speedtest.net или fast.com для проверки скорости соединения\n"
        "• Помните, что скорость зависит от многих факторов: загрузка сервера, ваше интернет-соединение, расстояние до сервера\n\n"
        "<b>🔒 Безопасность:</b>\n"
        "• Не передавайте свою ссылку подписки третьим лицам\n"
        "• Регулярно обновляйте пароли и используйте двухфакторную аутентификацию где возможно\n"
        "• При использовании публичных Wi-Fi всегда включайте VPN\n\n"
        "<b>Вопросы?</b>\n"
        "Напишите администратору через меню '💬 Написать админу'"
    )
    
    await message.answer(text, parse_mode="HTML")