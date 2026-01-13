import aiohttp
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from config import settings
from utils.logger import logger

class MarzbanAPI:
    def __init__(self):
        self.base_url = settings.MARZBAN_URL.rstrip('/')
        self.username = settings.MARZBAN_USERNAME
        self.password = settings.MARZBAN_PASSWORD
        self.token: Optional[str] = None
        self.token_expires: Optional[datetime] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._timeout = aiohttp.ClientTimeout(total=settings.API_TIMEOUT)
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Получить или создать сессию с connection pooling"""
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=self._timeout
            )
        return self._session
    
    async def close(self):
        """Закрыть сессию"""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def _get_token(self) -> str:
        """Получить токен авторизации с retry логикой"""
        if self.token and self.token_expires and datetime.utcnow() < self.token_expires:
            return self.token
        
        session = await self._get_session()
        
        for attempt in range(settings.API_RETRY_ATTEMPTS):
            try:
                async with session.post(
                    f"{self.base_url}/api/admin/token",
                    data={
                        "username": self.username,
                        "password": self.password
                    }
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self.token = data["access_token"]
                        self.token_expires = datetime.utcnow() + timedelta(hours=1)
                        logger.info("Marzban token obtained")
                        return self.token
                    else:
                        error_text = await resp.text()
                        logger.error(f"Failed to get token (attempt {attempt + 1}): {error_text}")
                        if attempt < settings.API_RETRY_ATTEMPTS - 1:
                            await asyncio.sleep(settings.API_RETRY_DELAY * (attempt + 1))
                        else:
                            raise Exception(f"Failed to authenticate: {resp.status}")
            except Exception as e:
                if attempt < settings.API_RETRY_ATTEMPTS - 1:
                    await asyncio.sleep(settings.API_RETRY_DELAY * (attempt + 1))
                else:
                    logger.error(f"Failed to get token after {settings.API_RETRY_ATTEMPTS} attempts: {e}")
                    raise
    
    async def _make_request(self, method: str, endpoint: str, 
                           data: Dict = None, params: Dict = None) -> Dict[str, Any]:
        """Выполнить запрос к API с retry логикой"""
        token = await self._get_token()
        headers = {"Authorization": f"Bearer {token}"}
        session = await self._get_session()
        
        for attempt in range(settings.API_RETRY_ATTEMPTS):
            try:
                async with session.request(
                    method,
                    f"{self.base_url}{endpoint}",
                    headers=headers,
                    json=data,
                    params=params
                ) as resp:
                    if resp.status in [200, 201]:
                        return await resp.json()
                    elif resp.status == 401:
                        # Token expired, refresh it
                        self.token = None
                        token = await self._get_token()
                        headers = {"Authorization": f"Bearer {token}"}
                        if attempt < settings.API_RETRY_ATTEMPTS - 1:
                            continue
                    
                    error_text = await resp.text()
                    logger.error(f"API request failed (attempt {attempt + 1}): {method} {endpoint} - {error_text}")
                    if attempt < settings.API_RETRY_ATTEMPTS - 1:
                        await asyncio.sleep(settings.API_RETRY_DELAY * (attempt + 1))
                    else:
                        raise Exception(f"API request failed: {resp.status} - {error_text}")
            except asyncio.TimeoutError:
                if attempt < settings.API_RETRY_ATTEMPTS - 1:
                    await asyncio.sleep(settings.API_RETRY_DELAY * (attempt + 1))
                else:
                    logger.error(f"API request timeout after {settings.API_RETRY_ATTEMPTS} attempts: {method} {endpoint}")
                    raise Exception(f"API request timeout: {method} {endpoint}")
            except Exception as e:
                if attempt < settings.API_RETRY_ATTEMPTS - 1:
                    await asyncio.sleep(settings.API_RETRY_DELAY * (attempt + 1))
                else:
                    raise
    
    async def create_user(self, username: str, data_limit: int, 
                         expire_days: int) -> Dict[str, Any]:
        """Создать пользователя в Marzban"""
        expire_date = int((datetime.utcnow() + timedelta(days=expire_days)).timestamp())
        
        data = {
            "username": username,
            "proxies": {
                
                "vless": {}
            },
            "data_limit": data_limit,
            "expire": expire_date,
            "status": "active"
        }
        
        result = await self._make_request("POST", "/api/user", data=data)
        logger.info(f"Marzban user created: {username}")
        return result
    
    async def get_user(self, username: str) -> Dict[str, Any]:
        """Получить информацию о пользователе"""
        return await self._make_request("GET", f"/api/user/{username}")
    
    async def update_user(self, username: str, data_limit: int = None,
                         expire_days: int = None, status: str = None) -> Dict[str, Any]:
        """Обновить пользователя"""
        data = {}
        
        if data_limit is not None:
            data["data_limit"] = data_limit
        
        if expire_days is not None:
            expire_date = int((datetime.utcnow() + timedelta(days=expire_days)).timestamp())
            data["expire"] = expire_date
        
        if status:
            data["status"] = status
        
        result = await self._make_request("PUT", f"/api/user/{username}", data=data)
        logger.info(f"Marzban user updated: {username}")
        return result
    
    async def delete_user(self, username: str) -> bool:
        """Удалить пользователя"""
        try:
            await self._make_request("DELETE", f"/api/user/{username}")
            logger.info(f"Marzban user deleted: {username}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete user {username}: {e}")
            return False
    
    async def get_user_usage(self, username: str) -> Dict[str, Any]:
        """Получить использование трафика пользователем"""
        user_data = await self.get_user(username)
        return {
            "used_traffic": user_data.get("used_traffic", 0),
            "data_limit": user_data.get("data_limit", 0),
            "expire": user_data.get("expire", 0),
            "status": user_data.get("status", "unknown")
        }

marzban_api = MarzbanAPI()
