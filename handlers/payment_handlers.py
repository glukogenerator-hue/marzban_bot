"""
Обработчики платежей
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from services import payment_service, user_service
from database.db_manager import db_manager
from utils.validation import DataValidator
from utils.error_handler import handle_error
from utils.logger import logger
from config import settings

payment_router = Router()

class PaymentStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_provider = State()
    waiting_for_payment_check = State()


@payment_router.message(F.text == "💳 Купить подписку")
async def start_payment(message: Message, state: FSMContext):
    """Начать процесс покупки подписки"""
    # Проверяем доступные провайдеры
    providers = await payment_service.get_payment_providers()
    
    if not providers:
        await message.answer("❌ Платежные системы временно недоступны. Попробуйте позже.")
        return
    
    # Показываем тарифы
    text = (
        "💳 <b>Выберите тарифный план</b>\n\n"
        "Доступные варианты:\n"
        "🔹 300₽ - 30 дней\n"
        "🔹 750₽ - 90 дней\n"
        "🔹 1000₽ - 180 дней\n"
        "🔹 2000₽ - 365 дней\n\n"
        "Введите сумму платежа (например: 300):"
    )
    
    await message.answer(text, parse_mode="HTML")
    await state.set_state(PaymentStates.waiting_for_amount)


@payment_router.message(PaymentStates.waiting_for_amount)
async def process_amount(message: Message, state: FSMContext):
    """Обработка выбранной суммы"""
    try:
        amount = float(message.text.strip())
        
        # Валидация суммы
        valid_amounts = [300, 750, 1000, 2000]
        if amount not in valid_amounts:
            await message.answer(
                f"❌ Неверная сумма. Допустимые значения: {', '.join(map(str, valid_amounts))}\n"
                "Попробуйте еще раз:"
            )
            return
        
        await state.update_data(amount=amount)
        
        # Выбираем провайдера
        providers = await payment_service.get_payment_providers()
        
        if 'yookassa' in providers:
            provider = 'yookassa'
        elif 'cryptobot' in providers:
            provider = 'cryptobot'
        else:
            await message.answer("❌ Платежные системы недоступны")
            await state.clear()
            return
        
        await state.update_data(provider=provider)
        
        # Создаем платеж
        user = await user_service.get_user(message.from_user.id)
        if not user:
            await message.answer("❌ Вы не зарегистрированы. Используйте /start")
            await state.clear()
            return
        
        description = f"Подписка VPN на {amount}₽"
        
        payment_data = await payment_service.create_payment(
            user_id=message.from_user.id,
            amount=amount,
            description=description,
            provider=provider
        )
        
        if not payment_data:
            await message.answer("❌ Не удалось создать платеж. Попробуйте позже.")
            await state.clear()
            return
        
        # Создаем клавиатуру с ссылкой на оплату
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить", url=payment_data['payment_url'])],
            [InlineKeyboardButton(text="✅ Проверить оплату", callback_data=f"check_payment_{payment_data['order_id']}")]
        ])
        
        await message.answer(
            f"✅ <b>Платеж создан!</b>\n\n"
            f"Сумма: {amount}₽\n"
            f"Order ID: <code>{payment_data['order_id']}</code>\n\n"
            f"Нажмите кнопку ниже для оплаты, затем вернитесь и нажмите 'Проверить оплату'",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        
        await state.set_state(PaymentStates.waiting_for_payment_check)
        await state.update_data(order_id=payment_data['order_id'])
        
    except ValueError:
        await message.answer("❌ Введите корректное число (например: 300)")
    except Exception as e:
        await handle_error(message, e, "Creating payment")
        await state.clear()


@payment_router.callback_query(F.data.startswith("check_payment_"))
async def check_payment_callback(callback: CallbackQuery, state: FSMContext):
    """Проверка статуса платежа"""
    try:
        order_id = callback.data.split("_")[2]
        
        # Получаем данные из состояния
        state_data = await state.get_data()
        provider = state_data.get('provider', 'yookassa')
        
        # Проверяем статус
        payment_status = await payment_service.check_payment_status(order_id, provider)
        
        if not payment_status:
            await callback.answer("❌ Не удалось проверить статус", show_alert=True)
            return
        
        if payment_status['paid']:
            await callback.message.edit_text(
                f"✅ <b>Оплата успешна!</b>\n\n"
                f"Ваша подписка активирована.\n"
                f"Используйте /start для получения доступа.",
                parse_mode="HTML"
            )
            await state.clear()
        else:
            await callback.answer("⏳ Оплата еще не поступила. Попробуйте через минуту.", show_alert=True)
            
    except Exception as e:
        await handle_error(callback, e, "Checking payment status")


@payment_router.message(F.text == "💳 Мои платежи")
async def my_payments(message: Message):
    """Показать историю платежей пользователя"""
    # Получаем транзакции пользователя
    # TODO: Реализовать полную историю
    await message.answer("📊 История платежей будет доступна в ближайшем обновлении")


@payment_router.message(F.text == "🔄 Проверить оплату")
async def manual_check_payment(message: Message):
    """Ручная проверка оплаты"""
    await message.answer(
        "Введите Order ID для проверки:\n"
        "Пример: order_123456_1234567890"
    )


@payment_router.message(F.text.startswith("order_"))
async def process_manual_check(message: Message):
    """Обработка ручной проверки"""
    try:
        order_id = message.text.strip()
        
        # Ищем транзакцию
        transaction = await db_manager.get_transaction_by_order_id(order_id)
        if not transaction:
            await message.answer("❌ Платеж не найден")
            return
        
        # Проверяем статус
        payment_status = await payment_service.check_payment_status(
            order_id, 
            transaction.payment_provider or 'yookassa'
        )
        
        if payment_status and payment_status['paid']:
            await message.answer("✅ Платеж подтвержден и активирован!")
        else:
            await message.answer("⏳ Платеж еще не подтвержден")
            
    except Exception as e:
        await handle_error(message, e, "Manual payment check")


# Обработчик для продления подписки через платеж
@payment_router.message(F.text == "🔄 Продлить подписку")
async def renew_subscription_payment(message: Message, state: FSMContext):
    """Обработчик продления через платеж"""
    user = await user_service.get_user(message.from_user.id)
    
    if not user or not user.marzban_username:
        await message.answer("❌ У вас нет активной подписки")
        return
    
    # Показываем тарифы для продления
    text = (
        "🔄 <b>Продление подписки</b>\n\n"
        "Выберите сумму для продления:\n"
        "🔹 300₽ - 30 дней\n"
        "🔹 750₽ - 90 дней\n"
        "🔹 1000₽ - 180 дней\n"
        "🔹 2000₽ - 365 дней\n\n"
        "Введите сумму:"
    )
    
    await message.answer(text, parse_mode="HTML")
    await state.set_state(PaymentStates.waiting_for_amount)