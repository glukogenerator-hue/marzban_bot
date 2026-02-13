"""
Централизованная обработка ошибок
"""
import asyncio
import logging
from typing import Optional, Union, Any
from aiogram.types import Message, CallbackQuery
from schemas.schemas import ErrorResponseSchema
from utils.logger import logger
import sqlalchemy.exc


class BotErrorHandler:
    """Обработчик ошибок для бота"""
    
    @staticmethod
    def log_error(error: Exception, context: str = "", user_id: Optional[int] = None):
        """Логирование ошибки с контекстом"""
        error_msg = f"{context}: {type(error).__name__}: {error}"
        if user_id:
            error_msg = f"User {user_id}: {error_msg}"
        
        logger.error(error_msg)
    
    @staticmethod
    def is_retryable(error: Exception) -> bool:
        """Проверить, можно ли повторить операцию"""
        import aiohttp
        retryable = (
            aiohttp.ClientError,
            ConnectionError,
            TimeoutError,
            asyncio.TimeoutError
        )
        return isinstance(error, retryable)
    
    @staticmethod
    def format_user_message(error: Exception) -> str:
        """Форматировать ошибку для показа пользователю"""
        import aiohttp
        import sqlalchemy.exc
        
        error_type = type(error)
        
        # Сетевые ошибки
        if isinstance(error, aiohttp.ClientError):
            return "❌ Сервис временно недоступен. Попробуйте позже."
        elif isinstance(error, (asyncio.TimeoutError, TimeoutError)):
            return "⏰ Превышено время ожидания. Попробуйте еще раз."
        elif isinstance(error, ConnectionError):
            return "🔌 Проблема с подключением. Проверьте интернет."
        
        # Ошибки базы данных
        elif isinstance(error, sqlalchemy.exc.OperationalError):
            return "🗄️ Ошибка базы данных. Попробуйте позже."
        elif isinstance(error, sqlalchemy.exc.IntegrityError):
            return "🗄️ Ошибка целостности данных. Возможно, запись уже существует."
        
        # Бизнес-логика
        elif isinstance(error, ValueError):
            # Берем только первую строку сообщения об ошибке
            error_msg = str(error).split('\n')[0]
            return f"❌ Ошибка в данных: {error_msg[:100]}"
        elif isinstance(error, PermissionError):
            return "❌ Недостаточно прав для выполнения операции."
        elif isinstance(error, FileNotFoundError):
            return "📁 Файл не найден."
        elif isinstance(error, ImportError):
            return "🔧 Ошибка загрузки модуля."
        
        # Общие ошибки
        else:
            # Для неизвестных ошибок показываем общее сообщение
            error_name = error_type.__name__
            if "marzban" in error_name.lower() or "api" in error_name.lower():
                return "🌐 Ошибка API сервиса. Попробуйте позже."
            return "❌ Произошла ошибка. Попробуйте позже или обратитесь к администратору."
    
    @staticmethod
    async def handle_error(
        event: Union[Message, CallbackQuery],
        error: Exception,
        context: str = "",
        send_to_user: bool = True
    ) -> ErrorResponseSchema:
        """
        Обработать ошибку и отправить сообщение пользователю
        
        Returns:
            ErrorResponseSchema: Стандартизированный ответ об ошибке
        """
        user_id = event.from_user.id if hasattr(event, 'from_user') else None
        
        # Логируем ошибку
        BotErrorHandler.log_error(error, context, user_id)
        
        # Формируем ответ
        error_response = ErrorResponseSchema(
            error=str(error),
            details=BotErrorHandler.format_user_message(error),
            code=type(error).__name__
        )
        
        # Отправляем сообщение пользователю
        if send_to_user:
            user_message = BotErrorHandler.format_user_message(error)
            try:
                if isinstance(event, CallbackQuery):
                    await event.answer(user_message, show_alert=True)
                else:
                    await event.answer(user_message)
            except Exception as send_error:
                logger.error(f"Failed to send error message to user: {send_error}")
        
        return error_response
    
    @staticmethod
    async def handle_validation_error(
        event: Union[Message, CallbackQuery],
        field: str,
        message: str,
        value: Optional[str] = None
    ) -> ErrorResponseSchema:
        """Обработка ошибок валидации"""
        user_id = event.from_user.id if hasattr(event, 'from_user') else None
        
        error_msg = f"Validation error in field '{field}': {message}"
        logger.warning(f"User {user_id}: {error_msg}")
        
        error_response = ErrorResponseSchema(
            error="Validation error",
            details=f"Поле '{field}': {message}",
            code="VALIDATION_ERROR"
        )
        
        user_message = f"❌ Ошибка в поле '{field}': {message}"
        if value:
            user_message += f"\nПолучено: {value}"
        
        try:
            if isinstance(event, CallbackQuery):
                await event.answer(user_message, show_alert=True)
            else:
                await event.answer(user_message)
        except Exception as e:
            logger.error(f"Failed to send validation error: {e}")
        
        return error_response
    
    @staticmethod
    async def handle_permission_error(
        event: Union[Message, CallbackQuery],
        required_role: str = "admin"
    ) -> ErrorResponseSchema:
        """Обработка ошибок доступа"""
        user_id = event.from_user.id if hasattr(event, 'from_user') else None
        
        logger.warning(f"Permission denied for user {user_id}, required: {required_role}")
        
        error_response = ErrorResponseSchema(
            error="Permission denied",
            details=f"Требуются права {required_role}",
            code="PERMISSION_DENIED"
        )
        
        user_message = "❌ У вас нет прав для выполнения этой операции"
        
        try:
            if isinstance(event, CallbackQuery):
                await event.answer(user_message, show_alert=True)
            else:
                await event.answer(user_message)
        except Exception as e:
            logger.error(f"Failed to send permission error: {e}")
        
        return error_response
    
    @staticmethod
    async def handle_not_found_error(
        event: Union[Message, CallbackQuery],
        entity: str,
        identifier: str
    ) -> ErrorResponseSchema:
        """Обработка ошибок 'не найдено'"""
        user_id = event.from_user.id if hasattr(event, 'from_user') else None
        
        logger.warning(f"Entity not found for user {user_id}: {entity} = {identifier}")
        
        error_response = ErrorResponseSchema(
            error=f"{entity} not found",
            details=f"{entity} с идентификатором '{identifier}' не найден",
            code="NOT_FOUND"
        )
        
        user_message = f"❌ {entity} не найден"
        
        try:
            if isinstance(event, CallbackQuery):
                await event.answer(user_message, show_alert=True)
            else:
                await event.answer(user_message)
        except Exception as e:
            logger.error(f"Failed to send not found error: {e}")
        
        return error_response


# Удобные функции-обертки
async def handle_error(
    event: Union[Message, CallbackQuery],
    error: Exception,
    context: str = ""
) -> ErrorResponseSchema:
    """Быстрая обработка ошибки"""
    return await BotErrorHandler.handle_error(event, error, context)


async def handle_validation(
    event: Union[Message, CallbackQuery],
    field: str,
    message: str,
    value: Optional[str] = None
) -> ErrorResponseSchema:
    """Быстрая обработка валидации"""
    return await BotErrorHandler.handle_validation_error(event, field, message, value)


async def require_permission(
    event: Union[Message, CallbackQuery],
    has_permission: bool,
    required_role: str = "admin"
) -> bool:
    """Проверка прав доступа"""
    if not has_permission:
        await BotErrorHandler.handle_permission_error(event, required_role)
        return False
    return True


async def require_exists(
    event: Union[Message, CallbackQuery],
    entity: Any,
    entity_name: str,
    identifier: str
) -> bool:
    """Проверка существования сущности"""
    if entity is None:
        await BotErrorHandler.handle_not_found_error(event, entity_name, identifier)
        return False
    return True