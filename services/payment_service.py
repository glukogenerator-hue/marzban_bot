"""
Сервис для работы с платежными системами
"""
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from decimal import Decimal
import hashlib
import hmac
import json

from schemas.schemas import TransactionCreateSchema, TransactionResponseSchema
from database.db_manager import db_manager
from utils.logger import logger
from utils.retry_handler import retry
from config import settings


class PaymentProvider:
    """Базовый класс для платежных провайдеров"""
    
    async def create_invoice(
        self,
        amount: float,
        description: str,
        order_id: str,
        currency: str = "RUB"
    ) -> Dict[str, Any]:
        """Создать счет на оплату"""
        raise NotImplementedError
    
    async def check_payment(self, invoice_id: str) -> Dict[str, Any]:
        """Проверить статус платежа"""
        raise NotImplementedError
    
    async def refund(self, invoice_id: str, amount: float) -> bool:
        """Возврат средств"""
        raise NotImplementedError


class YookassaProvider(PaymentProvider):
    """Интеграция с ЮKassa"""
    
    def __init__(self, shop_id: str, secret_key: str):
        self.shop_id = shop_id
        self.secret_key = secret_key
        self.base_url = "https://api.yookassa.ru/v3"
    
    @retry(max_attempts=3, exceptions=(Exception,))
    async def create_invoice(
        self,
        amount: float,
        description: str,
        order_id: str,
        currency: str = "RUB"
    ) -> Dict[str, Any]:
        """Создать счет в ЮKassa"""
        import aiohttp
        
        payload = {
            "amount": {
                "value": str(amount),
                "currency": currency
            },
            "confirmation": {
                "type": "redirect",
                "return_url": f"{settings.BOT_URL}/success"
            },
            "capture": True,
            "description": description,
            "metadata": {
                "order_id": order_id
            }
        }
        
        auth = aiohttp.BasicAuth(self.shop_id, self.secret_key)
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/payments",
                json=payload,
                auth=auth
            ) as resp:
                if resp.status == 201:
                    data = await resp.json()
                    return {
                        "invoice_id": data["id"],
                        "payment_url": data["confirmation"]["confirmation_url"],
                        "status": data["status"]
                    }
                else:
                    error_text = await resp.text()
                    raise Exception(f"Yookassa error: {error_text}")
    
    @retry(max_attempts=3, exceptions=(Exception,))
    async def check_payment(self, invoice_id: str) -> Dict[str, Any]:
        """Проверить статус платежа в ЮKassa"""
        import aiohttp
        
        auth = aiohttp.BasicAuth(self.shop_id, self.secret_key)
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/payments/{invoice_id}",
                auth=auth
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        "status": data["status"],
                        "paid": data.get("paid", False),
                        "amount": float(data["amount"]["value"]) if data.get("amount") else 0
                    }
                else:
                    raise Exception(f"Failed to check payment: {resp.status}")


class CryptoBotProvider(PaymentProvider):
    """Интеграция с CryptoBot (crypt.bot)"""
    
    def __init__(self, api_token: str):
        self.api_token = api_token
        self.base_url = "https://pay.crypt.bot/api"
    
    @retry(max_attempts=3, exceptions=(Exception,))
    async def create_invoice(
        self,
        amount: float,
        description: str,
        order_id: str,
        currency: str = "USD"
    ) -> Dict[str, Any]:
        """Создать счет в CryptoBot"""
        import aiohttp
        
        payload = {
            "amount": amount,
            "asset": currency,
            "description": description,
            "order_id": order_id,
            "allow_anonymous": False
        }
        
        headers = {
            "Crypto-Pay-API-Token": self.api_token
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/createInvoice",
                json=payload,
                headers=headers
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("ok"):
                        invoice = data["result"]
                        return {
                            "invoice_id": invoice["invoice_id"],
                            "payment_url": invoice["pay_url"],
                            "status": invoice["status"]
                        }
                    else:
                        raise Exception(f"CryptoBot error: {data.get('error', 'Unknown')}")
                else:
                    raise Exception(f"CryptoBot HTTP error: {resp.status}")
    
    @retry(max_attempts=3, exceptions=(Exception,))
    async def check_payment(self, invoice_id: str) -> Dict[str, Any]:
        """Проверить статус платежа в CryptoBot"""
        import aiohttp
        
        headers = {
            "Crypto-Pay-API-Token": self.api_token
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/getInvoices?invoice_ids={invoice_id}",
                headers=headers
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("ok"):
                        invoices = data["result"]["items"]
                        if invoices:
                            invoice = invoices[0]
                            return {
                                "status": invoice["status"],
                                "paid": invoice.get("paid", False),
                                "amount": invoice.get("amount", 0)
                            }
                    raise Exception("Invoice not found")
                else:
                    raise Exception(f"CryptoBot HTTP error: {resp.status}")


class PaymentService:
    """Сервис для работы с платежами"""
    
    def __init__(self):
        self.providers = {}
        self._init_providers()
    
    def _init_providers(self):
        """Инициализация платежных провайдеров"""
        # ЮKassa
        if hasattr(settings, 'YOOKASSA_SHOP_ID') and settings.YOOKASSA_SHOP_ID:
            self.providers['yookassa'] = YookassaProvider(
                settings.YOOKASSA_SHOP_ID,
                settings.YOOKASSA_SECRET_KEY
            )
        
        # CryptoBot
        if hasattr(settings, 'CRYPTOBOT_TOKEN') and settings.CRYPTOBOT_TOKEN:
            self.providers['cryptobot'] = CryptoBotProvider(settings.CRYPTOBOT_TOKEN)
    
    async def create_payment(
        self,
        user_id: int,
        amount: float,
        description: str,
        provider: str = "yookassa"
    ) -> Optional[Dict[str, Any]]:
        """
        Создать платеж
        
        Args:
            user_id: ID пользователя
            amount: Сумма платежа
            description: Описание
            provider: Провайдер (yookassa/cryptobot)
        
        Returns:
            Данные для оплаты или None
        """
        if provider not in self.providers:
            logger.error(f"Provider {provider} not configured")
            return None
        
        # Генерируем уникальный order_id
        order_id = f"order_{user_id}_{int(datetime.utcnow().timestamp())}"
        
        try:
            # Создаем счет у провайдера
            payment_data = await self.providers[provider].create_invoice(
                amount=amount,
                description=description,
                order_id=order_id
            )
            
            # Сохраняем транзакцию в БД
            transaction = await db_manager.create_transaction(
                user_id=user_id,
                telegram_id=user_id,
                amount=amount,
                description=description
            )
            
            # Обновляем order_id в транзакции
            await db_manager.update_transaction(
                transaction.id,
                order_id=order_id,
                payment_provider=provider,
                payment_invoice_id=payment_data['invoice_id']
            )
            
            logger.info(f"Created payment for user {user_id}: {order_id}")
            
            return {
                "order_id": order_id,
                "invoice_id": payment_data['invoice_id'],
                "payment_url": payment_data['payment_url'],
                "amount": amount,
                "provider": provider
            }
            
        except Exception as e:
            logger.error(f"Failed to create payment: {e}")
            return None
    
    async def check_payment_status(
        self,
        order_id: str,
        provider: str = "yookassa"
    ) -> Optional[Dict[str, Any]]:
        """
        Проверить статус платежа
        
        Args:
            order_id: ID заказа
            provider: Провайдер
        
        Returns:
            Статус платежа или None
        """
        if provider not in self.providers:
            return None
        
        try:
            # Получаем транзакцию из БД
            transaction = await db_manager.get_transaction_by_order_id(order_id)
            if not transaction:
                return None
            
            # Проверяем статус у провайдера
            payment_data = await self.providers[provider].check_payment(
                transaction.payment_invoice_id
            )
            
            # Обновляем статус в БД
            if payment_data['paid']:
                await db_manager.update_transaction(
                    transaction.id,
                    status="completed"
                )
                
                # Активируем подписку пользователя
                await self._activate_subscription(transaction.user_id, transaction.amount)
                
                logger.info(f"Payment completed: {order_id}")
            
            return payment_data
            
        except Exception as e:
            logger.error(f"Failed to check payment status: {e}")
            return None
    
    async def _activate_subscription(self, user_id: int, amount: float):
        """Активировать подписку после успешной оплаты"""
        from services import user_service
        
        # Определяем тариф по сумме
        plans = {
            300: {"days": 30, "data_limit": 107374182400},    # 100 GB
            750: {"days": 90, "data_limit": 322122547200},    # 300 GB
            1000: {"days": 180, "data_limit": 644245094400},  # 600 GB
            2000: {"days": 365, "data_limit": 1288490188800}  # 1.2 TB
        }
        
        plan = plans.get(int(amount))
        if not plan:
            logger.warning(f"No plan found for amount {amount}")
            return
        
        # Продляем подписку
        try:
            await user_service.renew_subscription(
                user_id,
                days=plan['days'],
                data_limit=plan['data_limit']
            )
            logger.info(f"Subscription activated for user {user_id}")
        except Exception as e:
            logger.error(f"Failed to activate subscription: {e}")
    
    async def get_payment_providers(self) -> Dict[str, bool]:
        """Получить доступные платежные провайдеры"""
        return {
            name: True for name in self.providers.keys()
        }


# Глобальный экземпляр сервиса
payment_service = PaymentService()