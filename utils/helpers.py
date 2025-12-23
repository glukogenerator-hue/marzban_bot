import qrcode
from io import BytesIO
from datetime import datetime
from typing import Optional

def format_bytes(bytes_value: int) -> str:
    """Форматировать байты в человекочитаемый формат"""
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

def get_traffic_percentage(used: int, limit: int) -> float:
    """Получить процент использованного трафика"""
    if limit == 0:
        return 0
    return (used / limit) * 100
