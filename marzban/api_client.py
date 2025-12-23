import aiohttp
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
    
    async def _get_token(self) -> str:
        """Получить токен авторизации"""
        if self.token and self.token_expires and datetime.utcnow() < self.token_expires:
            return self.token
        
        async with aiohttp.ClientSession() as session:
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
                    logger.error(f"Failed to get token: {error_text}")
                    raise Exception(f"Failed to authenticate: {resp.status}")
    
    async def _make_request(self, method: str, endpoint: str, 
                           data: Dict = None, params: Dict = None) -> Dict[str, Any]:
        """Выполнить запрос к API"""
        token = await self._get_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        async with aiohttp.ClientSession() as session:
            async with session.request(
                method,
                f"{self.base_url}{endpoint}",
                headers=headers,
                json=data,
                params=params
            ) as resp:
                if resp.status in [200, 201]:
                    return await resp.json()
                else:
                    error_text = await resp.text()
                    logger.error(f"API request failed: {method} {endpoint} - {error_text}")
                    raise Exception(f"API request failed: {resp.status} - {error_text}")
    
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
