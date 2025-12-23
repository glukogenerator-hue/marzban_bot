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
    
    await message.answer(welcome_text, reply_markup=get_main_keyboard())

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
        await message.answer(text, reply_markup=get_subscription_keyboard(user.trial_used))
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
    
    await message.answer(text, reply_markup=get_subscription_keyboard(user.trial_used), parse_mode="HTML")

@user_router.callback_query(F.data == "get_trial")
async def get_trial_access(callback: CallbackQuery):
    """Получить тестовый доступ"""
    user = await db_manager.get_user(callback.from_user.id)
    
    if user.trial_used:
        await callback.answer("❌ Вы уже использовали тестовый доступ", show_alert=True)
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
            f"Трафик: {format_bytes(settings.TRIAL_DATA_LIMIT)}\n"
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
async def copy_link(callback: CallbackQuery):
    """Скопировать ссылку"""
    user = await db_manager.get_user(callback.from_user.id)
    
    if not user.subscription_url:
        await callback.answer("❌ У вас нет активной подписки", show_alert=True)
        return
    
   await callback.message.answer(
        f"Ваша подписка:\n<code>{user.subscription_url}</code>\n\n"
        "Нажмите на ссылку, чтобы скопировать.",
        parse_mode="HTML"
    )
    await callback.answer()


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
        await message.answer("❌ Отменено", reply_markup=get_main_keyboard())
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
    await message.answer(
        "✅ Ваше сообщение отправлено администратору!",
        reply_markup=get_main_keyboard()
    )
