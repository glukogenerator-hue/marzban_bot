import qrcode
from io import BytesIO
from datetime import datetime
from typing import Optional

def format_bytes(bytes_value: Optional[int]) -> str:
    """Форматировать байты в человекочитаемый формат"""
    if bytes_value is None:
        bytes_value = 0
    
    # Преобразуем в int для безопасности
    try:
        bytes_value = int(bytes_value)
    except (ValueError, TypeError):
        bytes_value = 0
    
    for unit in ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.2f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.2f} ПБ"

def format_date(date: Optional[datetime]) -> str:
    """Форматировать дату"""
    if not date:
        return "Не указано"
    return date.strftime("%d.%m.%Y %H:%M")

def generate_qr_code(data: str) -> BytesIO:
    """Генерировать QR код"""
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    bio = BytesIO()
    bio.name = 'qrcode.png'
    img.save(bio, 'PNG')
    bio.seek(0)
    return bio

def generate_username(telegram_id: int) -> str:
    """Генерировать уникальное имя пользователя"""
    return f"user_{telegram_id}_{int(datetime.utcnow().timestamp())}"

def calculate_expire_days(expire_date: Optional[datetime]) -> int:
    """Рассчитать количество дней до истечения"""
    if not expire_date:
        return 0
    delta = expire_date - datetime.utcnow()
    return max(0, delta.days)

def get_traffic_percentage(used: Optional[int], limit: Optional[int]) -> float:
    """Получить процент использованного трафика"""
    # Обработка None значений
    if used is None:
        used = 0
    if limit is None or limit == 0:
        return 0.0
    
    # Преобразуем в int
    try:
        used = int(used)
        limit = int(limit)
    except (ValueError, TypeError):
        return 0.0
    
    return (used / limit) * 100

def extract_telegram_id_from_username(username: str) -> Optional[int]:
    """
    Извлечь telegram_id из имени пользователя в формате user_telegram_id_timestamp
    Пример: user_124094154_1771011293 -> 124094154
    """
    if not username.startswith("user_"):
        return None
    
    try:
        # Разделяем по нижнему подчеркиванию
        parts = username.split("_")
        if len(parts) < 3:
            return None
        
        # Вторая часть должна быть telegram_id
        telegram_id_str = parts[1]
        return int(telegram_id_str)
    except (ValueError, IndexError):
        return None
