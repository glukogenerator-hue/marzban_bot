"""
Сервис для работы с платежами через Telegram Stars
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from schemas.schemas import TransactionCreateSchema, TransactionResponseSchema
from database.db_manager import db_manager
from services.marzban_service import MarzbanService
from services.user_service import UserService
from utils.logger import logger
from utils.retry_handler import retry
from config import settings


class PaymentService:
    """Сервис для работы с платежами через Telegram Stars"""
    
    def __init__(self):
        self.marzban_service = MarzbanService()
        self.user_service = UserService()
    
    async def get_payment_providers(self) -> Dict[str, bool]:
        """
        Получить список доступных платежных провайдеров
        
        Returns:
            Dict[str, bool]: Словарь с доступными провайдерами
        """
        providers = {}
        
        # Telegram Stars всегда доступен, если включен в настройках
        if settings.TELEGRAM_STARS_ENABLED and settings.BOT_TOKEN:
            providers['telegram_stars'] = True
        
        return providers
    
    async def activate_subscription_after_payment(
        self,
        user_id: int,
        order_id: str,
        plan_data: Dict[str, Any]
    ) -> bool:
        """
        Активировать подписку после успешной оплаты
        
        Args:
            user_id: ID пользователя в Telegram
            order_id: ID заказа/транзакции
            plan_data: Данные о тарифном плане
            
        Returns:
            bool: Успешность активации
        """
        try:
            # Получаем пользователя
            user = await self.user_service.get_user(user_id)
            if not user:
                logger.error(f"User {user_id} not found for subscription activation")
                return False
            
            # Получаем информацию о плане
            days = plan_data.get('days', 30)
            
            # Определяем дату окончания новой подписки
            now = datetime.now()
            
            if user.is_active and user.expire_date and user.expire_date > now:
                # Подписка активна, прибавляем дни к следующему дню после окончания
                # Используем max чтобы избежать ситуаций, когда expire_date в прошлом
                base_date = max(user.expire_date, now)
                new_expire_date = base_date + timedelta(days=days)
                logger.info(f"Active subscription found. Extending from {user.expire_date} to {new_expire_date}")
            else:
                # Нет активной подписки, начинаем с текущей даты
                new_expire_date = now + timedelta(days=days)
                logger.info(f"No active subscription. Setting new expire date: {new_expire_date}")
            
            # Передаем timestamp новой даты окончания (Marzban сам преобразует в дни)
            expire_timestamp = int(new_expire_date.timestamp())
            
            # Обновляем пользователя в Marzban - устанавливаем безлимитный трафик (0) и новую дату окончания
            success = await self.marzban_service.update_user(
                username=user.marzban_username,
                update_data={
                    "expire": expire_timestamp,  # передаем timestamp
                    "data_limit": 0  # безлимитный трафик для платной подписки
                }
            )
            
            if success:
                logger.info(f"Subscription activated for user {user_id}, order {order_id}")
                
                # Обновляем информацию о пользователе в локальной БД
                await self.user_service.update_user(
                    telegram_id=user_id,
                    update_data={
                        "expire_date": new_expire_date,
                        "is_active": True,
                        "data_limit": 0  # безлимитный трафик
                    }
                )
                
                return True
            else:
                logger.error(f"Failed to update Marzban user {user.marzban_username}")
                return False
                
        except Exception as e:
            logger.error(f"Error activating subscription: {e}")
            return False
    
    async def refund_payment(self, user_id: int, order_id: str) -> bool:
        """
        Инициировать возврат средств
        
        Args:
            user_id: ID пользователя в Telegram
            order_id: ID заказа/транзакции
            
        Returns:
            bool: Успешность инициации возврата
        """
        try:
            # Получаем транзакцию
            transaction = await db_manager.get_transaction_by_order_id(order_id)
            if not transaction:
                logger.error(f"Transaction {order_id} not found for refund")
                return False
            
            # Проверяем, что транзакция принадлежит пользователю
            if transaction.telegram_id != user_id:
                logger.error(f"Transaction {order_id} doesn't belong to user {user_id}")
                return False
            
            # Проверяем статус транзакции
            if transaction.status != "completed":
                logger.error(f"Transaction {order_id} is not completed, status: {transaction.status}")
                return False
            
            # Проверяем, прошло ли меньше 14 дней с момента оплаты
            days_since_payment = (datetime.now() - transaction.created_at).days
            if days_since_payment > 14:
                logger.error(f"Transaction {order_id} is too old for refund: {days_since_payment} days")
                return False
            
            # Здесь должна быть логика вызова API Telegram для возврата средств
            # Временно просто отмечаем транзакцию как возвращенную
            await db_manager.update_transaction_by_order_id(
                order_id=order_id,
                status="refunded",
                refund_date=datetime.now()
            )
            
            logger.info(f"Refund initiated for transaction {order_id}, user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error processing refund: {e}")
            return False
    
    async def get_payment_history(self, user_id: int, limit: int = 10) -> list:
        """
        Получить историю платежей пользователя
        
        Args:
            user_id: ID пользователя в Telegram
            limit: Максимальное количество записей
            
        Returns:
            list: Список транзакций
        """
        try:
            # Здесь должна быть логика получения истории платежей из БД
            # Временно возвращаем пустой список
            return []
            
        except Exception as e:
            logger.error(f"Error getting payment history: {e}")
            return []
    
    async def check_payment_status(self, order_id: str) -> Dict[str, Any]:
        """
        Проверить статус платежа
        
        Args:
            order_id: ID заказа/транзакции
            
        Returns:
            Dict[str, Any]: Информация о статусе платежа
        """
        try:
            transaction = await db_manager.get_transaction_by_order_id(order_id)
            
            if not transaction:
                return {
                    "status": "not_found",
                    "message": "Транзакция не найдена"
                }
            
            return {
                "status": transaction.status,
                "amount": transaction.amount,
                "currency": transaction.currency,
                "created_at": transaction.created_at,
                "payment_id": transaction.payment_id
            }
            
        except Exception as e:
            logger.error(f"Error checking payment status: {e}")
            return {
                "status": "error",
                "message": str(e)
            }


# Создаем глобальный экземпляр сервиса
payment_service = PaymentService()