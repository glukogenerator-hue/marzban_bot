from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def get_admin_keyboard() -> ReplyKeyboardMarkup:
    """Главное меню админа"""
    keyboard = [
        [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="👥 Пользователи")],
        [KeyboardButton(text="📨 Рассылка"), KeyboardButton(text="💬 Сообщения")],
        [KeyboardButton(text="⚙️ Управление"), KeyboardButton(text="📋 Логи")],
        [KeyboardButton(text="👤 Режим пользователя")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_user_management_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    """Клавиатура управления пользователем"""
    keyboard = [
        [InlineKeyboardButton(text="✏️ Изменить подписку", callback_data=f"admin_edit_{telegram_id}")],
        [InlineKeyboardButton(text="⏸️ Приостановить", callback_data=f"admin_suspend_{telegram_id}")],
        [InlineKeyboardButton(text="✅ Активировать", callback_data=f"admin_activate_{telegram_id}")],
        [InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"admin_delete_{telegram_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_subscription_edit_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    """Клавиатура редактирования подписки"""
    keyboard = [
        [InlineKeyboardButton(text="➕ Продлить на 7 дней", callback_data=f"admin_extend_{telegram_id}_7")],
        [InlineKeyboardButton(text="➕ Продлить на 30 дней", callback_data=f"admin_extend_{telegram_id}_30")],
        [InlineKeyboardButton(text="➕ Продлить на 90 дней", callback_data=f"admin_extend_{telegram_id}_90")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data=f"admin_user_{telegram_id}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_broadcast_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура рассылки"""
    keyboard = [
        [InlineKeyboardButton(text="📤 Отправить всем", callback_data="broadcast_all")],
        [InlineKeyboardButton(text="✅ Активным", callback_data="broadcast_active")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_cancel")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_message_keyboard(user_telegram_id: int, message_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для сообщения от пользователя"""
    keyboard = [
        [InlineKeyboardButton(text="💬 Ответить", callback_data=f"reply_to_{user_telegram_id}_{message_id}")],
        [InlineKeyboardButton(text="✅ Прочитано", callback_data=f"mark_read_{message_id}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_users_list_keyboard(users_buttons: list, has_more: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура списка пользователей"""
    keyboard = users_buttons.copy()
    
    # Добавляем кнопки навигации
    if has_more:
        keyboard.append([
            InlineKeyboardButton(text="🔄 Обновить список", callback_data="admin_users_refresh")
        ])
    
    keyboard.append([
        InlineKeyboardButton(text="🔍 Поиск по ID", callback_data="admin_search_user")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)