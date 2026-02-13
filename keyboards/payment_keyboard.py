"""
Клавиатуры для платежей через Telegram Stars
"""
from aiogram.utils.keyboard import InlineKeyboardBuilder


def payment_keyboard(amount_stars: int):
    """
    Создать клавиатуру для оплаты через Telegram Stars
    
    Args:
        amount_stars: Количество звезд для оплаты
        
    Returns:
        InlineKeyboardMarkup: Клавиатура с кнопкой оплаты
    """
    builder = InlineKeyboardBuilder()
    builder.button(text=f"Оплатить {amount_stars} ⭐️", pay=True)
    
    return builder.as_markup()


def payment_with_cancel_keyboard(amount_stars: int):
    """
    Создать клавиатуру для оплаты с кнопкой отмены
    
    Args:
        amount_stars: Количество звезд для оплаты
        
    Returns:
        InlineKeyboardMarkup: Клавиатура с кнопкой оплаты и отмены
    """
    builder = InlineKeyboardBuilder()
    builder.button(text=f"Оплатить {amount_stars} ⭐️", pay=True)
    builder.button(text="❌ Отмена", callback_data="cancel_payment")
    builder.adjust(1)
    
    return builder.as_markup()