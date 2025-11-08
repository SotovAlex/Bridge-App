import json
import logging
from typing import Dict, List, Optional


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Dict] = {}
        self.waiting_users: List[Dict] = []

    async def connect(self, websocket, user_id: str, user_data: Dict):
        """Добавляем пользователя в активные соединения"""
        self.active_connections[user_id] = {
            "websocket": websocket,
            "user_data": user_data
        }
        logging.info(f"User {user_id} connected. Total active: {len(self.active_connections)}")

    def disconnect(self, user_id: str):
        """Удаляем пользователя при отключении"""
        if user_id in self.active_connections:
            del self.active_connections[user_id]

        # Также удаляем из очереди ожидания
        self.waiting_users = [user for user in self.waiting_users if user.get('user_id') != user_id]
        logging.info(f"User {user_id} disconnected")

    async def find_partner(self, current_user: Dict) -> Optional[Dict]:
        """Ищем подходящего партнера для пользователя"""
        user_id = current_user.get('user_id')
        user_country = current_user.get('country')
        user_language = current_user.get('language')

        logging.info(f"Finding partner for user {user_id} from {user_country}")

        for waiting_user in self.waiting_users:
            # Ищем пользователя из ДРУГОЙ страны
            if (waiting_user.get('country') != user_country and
                    waiting_user.get('user_id') != user_id):
                # Нашли пару! Удаляем из очереди ожидания
                self.waiting_users.remove(waiting_user)
                logging.info(f"Matched user {user_id} with {waiting_user.get('user_id')}")
                return waiting_user

        # Если пару не нашли, добавляем текущего пользователя в очередь
        if not any(user.get('user_id') == user_id for user in self.waiting_users):
            self.waiting_users.append(current_user)
            logging.info(f"User {user_id} added to waiting list. Queue size: {len(self.waiting_users)}")

        return None

    async def send_personal_message(self, message: str, user_id: str):
        """Отправляем сообщение конкретному пользователю"""
        if user_id in self.active_connections:
            connection = self.active_connections[user_id]["websocket"]
            await connection.send_text(message)

    def get_waiting_queue_size(self) -> int:
        """Возвращает размер очереди ожидания (для тестирования)"""
        return len(self.waiting_users)