"""
Обработчики платежей через Telegram Stars
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, LabeledPrice, PreCheckoutQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from services import user_service, payment_service
from database.db_manager import db_manager
from utils.validation import DataValidator
from utils.error_handler import handle_error
from utils.logger import logger
from keyboards.payment_keyboard import payment_keyboard, payment_with_cancel_keyboard
from config import settings

payment_router = Router()


class PaymentStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_payment_check = State()


def rub_to_stars(rub_amount: float) -> int:
    """
    Конвертировать рубли в звезды (1 звезда ≈ 7 RUB)
    
    Args:
        rub_amount: Сумма в рублях
        
    Returns:
        int: Количество звезд
    """
    # Для тестирования всегда возвращаем 1 звезду
    return 1


def get_plan_by_amount(amount: float) -> dict:
    """
    Получить информацию о тарифном плане по сумме
    
    Args:
        amount: Сумма в рублях
        
    Returns:
        dict: Информация о плане или None
    """
    plans = settings.SUBSCRIPTION_PLANS
    for plan_id, plan_data in plans.items():
        if plan_data["price"] == amount:
            return {"id": plan_id, **plan_data}
    return None


@payment_router.message(F.text == "💳 Купить подписку")
async def start_payment(message: Message, state: FSMContext):
    """Начать процесс покупки подписки"""
    # Проверяем, включены ли Telegram Stars
    if not settings.TELEGRAM_STARS_ENABLED:
        await message.answer("❌ Платежная система временно недоступна. Попробуйте позже.")
        return
    
    # Проверяем регистрацию пользователя
    user = await user_service.get_user(message.from_user.id)
    if not user:
        await message.answer("❌ Вы не зарегистрированы. Используйте /start")
        return
    
    # Показываем тарифы
    text = (
        "💳 <b>Выберите тарифный план</b>\n\n"
        "Доступные варианты:\n"
    )
    
    for plan_id, plan in settings.SUBSCRIPTION_PLANS.items():
        stars = rub_to_stars(plan["price"])
        text += f"🔹 {plan['price']}₽ ({stars} ⭐️) - {plan['days']} дней\n"
    
    text += "\nВведите сумму платежа (например: 300):"
    
    await message.answer(text, parse_mode="HTML")
    await state.set_state(PaymentStates.waiting_for_amount)


@payment_router.message(PaymentStates.waiting_for_amount)
async def process_amount(message: Message, state: FSMContext):
    """Обработка выбранной суммы"""
    try:
        amount = float(message.text.strip())
        
        # Валидация суммы
        valid_amounts = [plan["price"] for plan in settings.SUBSCRIPTION_PLANS.values()]
        if amount not in valid_amounts:
            await message.answer(
                f"❌ Неверная сумма. Допустимые значения: {', '.join(map(str, valid_amounts))}\n"
                "Попробуйте еще раз:"
            )
            return
        
        # Получаем информацию о плане
        plan = get_plan_by_amount(amount)
        if not plan:
            await message.answer("❌ Не удалось найти тарифный план. Попробуйте еще раз:")
            return
        
        # Конвертируем в звезды
        stars_amount = rub_to_stars(amount)
        
        # Сохраняем данные в состоянии
        await state.update_data(
            amount=amount,
            stars_amount=stars_amount,
            plan_id=plan["id"],
            days=plan["days"]
        )
        
        # Создаем транзакцию в базе данных
        user = await user_service.get_user(message.from_user.id)
        transaction = await db_manager.create_transaction(
            user_id=user.id,
            telegram_id=message.from_user.id,
            amount=amount,
            description=f"Подписка VPN на {plan['days']} дней"
        )
        
        if not transaction:
            await message.answer("❌ Не удалось создать транзакцию. Попробуйте позже.")
            await state.clear()
            return
        
        # Создаем счет на оплату
        prices = [LabeledPrice(label="XTR", amount=stars_amount)]
        
        await message.answer_invoice(
            title=f"Подписка VPN на {plan['days']} дней",
            description=f"Доступ к VPN сервису на {plan['days']} дней",
            prices=prices,
            provider_token="",  # Для Telegram Stars оставляем пустую строку
            payload=f"subscription_{transaction.order_id}",
            currency="XTR",
            reply_markup=payment_keyboard(stars_amount),
        )
        
        # Сохраняем order_id в состоянии
        await state.update_data(order_id=transaction.order_id)
        await state.set_state(PaymentStates.waiting_for_payment_check)
        
    except ValueError:
        await message.answer("❌ Пожалуйста, введите числовое значение (например: 300):")
    except Exception as e:
        logger.error(f"Error processing amount: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")
        await state.clear()


@payment_router.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery):
    """
    Обработчик предпродажной проверки
    У нас есть 10 секунд, чтобы ответить
    """
    try:
        # Здесь можно добавить дополнительную логику проверки
        # Например, проверить, может ли пользователь совершить покупку
        
        # Всегда подтверждаем платеж
        await pre_checkout_query.answer(ok=True)
        logger.info(f"Pre-checkout approved for user {pre_checkout_query.from_user.id}")
        
    except Exception as e:
        logger.error(f"Error in pre-checkout: {e}")
        await pre_checkout_query.answer(
            ok=False,
            error_message="Произошла ошибка при обработке платежа"
        )


@payment_router.message(F.successful_payment)
async def success_payment_handler(message: Message, state: FSMContext):
    """Обработчик успешного платежа"""
    try:
        payment_info = message.successful_payment
        logger.info(f"Successful payment: {payment_info}")
        
        # Получаем данные из состояния
        state_data = await state.get_data()
        order_id = state_data.get('order_id')
        
        if not order_id:
            logger.error("No order_id in state for successful payment")
            await message.answer("❌ Не удалось обработать платеж. Обратитесь к администратору.")
            await state.clear()
            return
        
        # Обновляем транзакцию в базе данных
        transaction_updated = await db_manager.update_transaction_by_order_id(
            order_id=order_id,
            status="completed",
            payment_invoice_id=payment_info.telegram_payment_charge_id
        )
        
        if not transaction_updated:
            logger.error(f"Failed to update transaction {order_id}")
        
        # Активируем подписку
        user = await user_service.get_user(message.from_user.id)
        if user and state_data:
            # Используем payment_service для активации подписки
            success = await payment_service.activate_subscription_after_payment(
                user_id=message.from_user.id,
                order_id=order_id,
                plan_data=state_data
            )
            
            if success:
                from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="📊 Перейти к подписке",
                                callback_data="go_to_subscription"
                            )
                        ]
                    ]
                )
                await message.answer(
                    "✅ <b>Платеж успешно завершен!</b>\n\n"
                    f"Ваша подписка активирована на {state_data.get('days', 30)} дней.",
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
            else:
                await message.answer(
                    "⚠️ <b>Платеж получен, но возникла проблема с активацией подписки.</b>\n\n"
                    "Пожалуйста, обратитесь к администратору для решения проблемы.",
                    parse_mode="HTML"
                )
        else:
            await message.answer(
                "✅ <b>Платеж успешно завершен!</b>\n\n"
                "Спасибо за покупку!",
                parse_mode="HTML"
            )
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Error processing successful payment: {e}")
        await message.answer("❌ Произошла ошибка при обработке платежа. Обратитесь к администратору.")
        await state.clear()


@payment_router.callback_query(F.data.startswith("check_payment_"))
async def check_payment_callback(callback: CallbackQuery, state: FSMContext):
    """Проверка статуса платежа"""
    try:
        order_id = callback.data.replace("check_payment_", "")
        
        # Проверяем статус транзакции
        transaction = await db_manager.get_transaction_by_order_id(order_id)
        
        if not transaction:
            await callback.answer("❌ Транзакция не найдена")
            return
        
        if transaction.status == "completed":
            await callback.answer("✅ Платеж уже подтвержден")
            await callback.message.answer("Ваша подписка уже активирована!")
        elif transaction.status == "pending":
            await callback.answer("⏳ Платеж еще не подтвержден")
            await callback.message.answer(
                "Платеж еще не подтвержден. Пожалуйста, подождите или попробуйте позже."
            )
        else:
            await callback.answer("❌ Платеж не найден или отменен")
            
    except Exception as e:
        logger.error(f"Error checking payment: {e}")
        await callback.answer("❌ Ошибка при проверке платежа")


@payment_router.message(F.text == "💳 Мои платежи")
async def my_payments(message: Message):
    """Показать историю платежей пользователя"""
    try:
        user = await user_service.get_user(message.from_user.id)
        if not user:
            await message.answer("❌ Вы не зарегистрированы. Используйте /start")
            return
        
        # Здесь можно добавить логику получения истории платежей
        await message.answer("📋 <b>История платежей</b>\n\nФункция в разработке...", parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Error showing payments: {e}")
        await message.answer("❌ Не удалось загрузить историю платежей")


@payment_router.message(Command("paysupport"))
async def pay_support_handler(message: Message):
    """
    Команда для информации о возврате средств
    Обязательная команда согласно требованиям Telegram
    """
    await message.answer(
        "📞 <b>Поддержка по платежам</b>\n\n"
        "Если у вас возникли проблемы с оплатой или вам нужен возврат средств:\n\n"
        "1. <b>Возврат средств</b>: Возврат возможен в течение 14 дней с момента оплаты "
        "при условии, что услуга не была использована.\n\n"
        "2. <b>Проблемы с оплатой</b>: Если платеж не прошел, но средства списались, "
        "свяжитесь с поддержкой.\n\n"
        "3. <b>Контакты</b>: Для решения вопросов по платежам обращайтесь к администратору.",
        parse_mode="HTML"
    )


@payment_router.message(F.text == "🔄 Проверить оплату")
async def manual_check_payment(message: Message):
    """Ручная проверка оплаты"""
    await message.answer(
        "Для проверки оплаты введите номер заказа в формате:\n"
        "<code>order_XXXXXXXXXX</code>\n\n"
        "Номер заказа можно найти в истории платежей.",
        parse_mode="HTML"
    )


@payment_router.message(F.text.startswith("order_"))
async def process_manual_check(message: Message):
    """Обработка ручной проверки"""
    try:
        order_id = message.text.strip()
        
        # Проверяем статус транзакции
        transaction = await db_manager.get_transaction_by_order_id(order_id)
        
        if not transaction:
            await message.answer("❌ Транзакция не найдена")
            return
        
        status_text = {
            "pending": "⏳ Ожидает оплаты",
            "completed": "✅ Оплачено",
            "failed": "❌ Ошибка оплаты",
            "refunded": "↩️ Возврат средств"
        }.get(transaction.status, "❓ Неизвестный статус")
        
        await message.answer(
            f"📋 <b>Информация о заказе</b>\n\n"
            f"🆔 Номер: <code>{order_id}</code>\n"
            f"💰 Сумма: {transaction.amount} {transaction.currency}\n"
            f"📊 Статус: {status_text}\n"
            f"📅 Дата: {transaction.created_at.strftime('%d.%m.%Y %H:%M')}",
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Error in manual check: {e}")
        await message.answer("❌ Ошибка при проверке заказа")


@payment_router.message(F.text == "🔄 Продлить подписку")
async def renew_subscription_payment(message: Message, state: FSMContext):
    """Продлить существующую подписку"""
    try:
        user = await user_service.get_user(message.from_user.id)
        if not user:
            await message.answer("❌ Вы не зарегистрированы. Используйте /start")
            return
        
        # Проверяем текущую подписку
        subscription_info = await user_service.get_subscription_info(message.from_user.id)
        
        if not subscription_info or subscription_info.status != "active":
            await message.answer("❌ У вас нет активной подписки для продления")
            return
        
        # Показываем тарифы для продления
        text = (
            "🔄 <b>Продление подписки</b>\n\n"
            "Доступные варианты продления:\n"
        )
        
        for plan_id, plan in settings.SUBSCRIPTION_PLANS.items():
            stars = rub_to_stars(plan["price"])
            text += f"🔹 {plan['price']}₽ ({stars} ⭐️) - +{plan['days']} дней\n"
        
        text += "\nВведите сумму для продления (например: 300):"
        
        await message.answer(text, parse_mode="HTML")
        await state.set_state(PaymentStates.waiting_for_amount)
        
    except Exception as e:
        logger.error(f"Error starting renewal: {e}")
        await message.answer("❌ Не удалось начать процесс продления")


@payment_router.callback_query(F.data.startswith("start_payment_"))
async def start_payment_from_callback(callback: CallbackQuery, state: FSMContext):
    """Начать процесс оплаты из callback (при выборе плана)"""
    try:
        plan_id = callback.data.replace("start_payment_", "")
        
        if plan_id not in settings.SUBSCRIPTION_PLANS:
            await callback.answer("❌ Неверный план", show_alert=True)
            return
        
        plan = settings.SUBSCRIPTION_PLANS[plan_id]
        amount = plan["price"]
        
        # Проверяем, включены ли Telegram Stars
        if not settings.TELEGRAM_STARS_ENABLED:
            await callback.answer("❌ Платежная система временно недоступна", show_alert=True)
            return
        
        # Проверяем регистрацию пользователя
        user = await user_service.get_user(callback.from_user.id)
        if not user:
            await callback.answer("❌ Вы не зарегистрированы. Используйте /start", show_alert=True)
            return
        
        # Сохраняем данные в состоянии
        await state.update_data(
            amount=amount,
            stars_amount=rub_to_stars(amount),
            plan_id=plan_id,
            days=plan["days"]
        )
        
        # Создаем транзакцию в базе данных
        transaction = await db_manager.create_transaction(
            user_id=user.id,
            telegram_id=callback.from_user.id,
            amount=amount,
            description=f"Подписка VPN на {plan['days']} дней"
        )
        
        if not transaction:
            await callback.answer("❌ Не удалось создать транзакцию", show_alert=True)
            return
        
        # Создаем счет на оплату
        prices = [LabeledPrice(label="XTR", amount=rub_to_stars(amount))]
        
        # Отправляем инвойс
        await callback.message.answer_invoice(
            title=f"Подписка VPN на {plan['days']} дней",
            description=f"Доступ к VPN сервису на {plan['days']} дней",
            prices=prices,
            provider_token="",  # Для Telegram Stars оставляем пустую строку
            payload=f"subscription_{transaction.order_id}",
            currency="XTR",
            reply_markup=payment_keyboard(rub_to_stars(amount)),
        )
        
        # Сохраняем order_id в состоянии
        await state.update_data(order_id=transaction.order_id)
        await state.set_state(PaymentStates.waiting_for_payment_check)
        
        # Удаляем предыдущее сообщение с кнопками
        await callback.message.delete()
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error starting payment from callback: {e}")
        await callback.answer("❌ Произошла ошибка при начале оплаты", show_alert=True)