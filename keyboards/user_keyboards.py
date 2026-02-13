from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def get_main_keyboard(has_subscription: bool = False) -> ReplyKeyboardMarkup:
    """Главное меню пользователя
    
    Args:
        has_subscription: True если у пользователя есть активная подписка
    """
    keyboard = [
        [KeyboardButton(text="📊 Моя подписка")],
    ]
    
    # Показываем разные кнопки в зависимости от наличия подписки
    if has_subscription:
        keyboard.append([KeyboardButton(text="🔄 Продлить подписку")])
    else:
        keyboard.append([KeyboardButton(text="💳 Купить подписку")])
    
    keyboard.extend([
        [KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="💬 Написать админу")],
        [KeyboardButton(text="ℹ️ Помощь")]
    ])
    
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_settings_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура настроек"""
    keyboard = [
        [InlineKeyboardButton(text="🔔 Уведомления", callback_data="settings_notifications")],
        [InlineKeyboardButton(text="⏰ Уведомления об истечении", callback_data="settings_expire")],
        [InlineKeyboardButton(text="📊 Уведомления о трафике", callback_data="settings_traffic")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="settings_back")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_subscription_keyboard(has_trial: bool, has_active_subscription: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура подписки"""
    keyboard = []
    
    if not has_trial:
        keyboard.append([InlineKeyboardButton(text="🎁 Получить тестовый доступ", callback_data="get_trial")])
    
    if has_active_subscription:
        keyboard.append([InlineKeyboardButton(text="⚙️ Настройка подключения", callback_data="connection_settings")])
    
    keyboard.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh_subscription")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_plans_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура тарифных планов"""
    from config import settings
    keyboard = []
    
    for plan_id, plan in settings.SUBSCRIPTION_PLANS.items():
        months = plan['days'] // 30
        keyboard.append([
            InlineKeyboardButton(
                text=f"{months} месяц(а/ев) - {plan['price']}₽",
                callback_data=f"buy_plan_{plan_id}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="plans_back")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_connection_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подключения"""
    keyboard = [
        [InlineKeyboardButton(text="📱 QR код", callback_data="get_qr")],
        [InlineKeyboardButton(text="🔗 Скопировать ссылку", callback_data="copy_link")],
        [InlineKeyboardButton(text="📖 Инструкции", callback_data="instructions")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
