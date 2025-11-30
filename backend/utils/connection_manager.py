import json
import logging
import time
from typing import Dict, List, Optional, Any


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Dict[str, Any]] = {}
        self.waiting_users: List[Dict[str, Any]] = []
        self.last_activity: Dict[str, float] = {}  # Отслеживаем активность

    async def connect(self, websocket, user_id: str, user_data: Dict[str, Any]):
        """Добавляем пользователя в активные соединения"""
        self.active_connections[user_id] = {
            "websocket": websocket,
            "user_data": user_data,
            "partner_id": None
        }
        self.last_activity[user_id] = time.time()  # Записываем время подключения
        logging.info(f"User {user_id} connected. Total active: {len(self.active_connections)}")

    def update_activity(self, user_id: str):
        """Обновляем время последней активности"""
        if user_id in self.last_activity:
            self.last_activity[user_id] = time.time()
            logging.debug(f"Activity updated for user {user_id}")

    async def cleanup_inactive_connections(self):
        """Очищаем неактивные соединения"""
        current_time = time.time()
        inactive_users = []

        for user_id, last_active in self.last_activity.items():
            time_since_active = current_time - last_active
            if current_time - last_active > 30:  # 30 секунд таймаут
                inactive_users.append(user_id)
                logging.info(f"User {user_id} inactive for {time_since_active:.1f}s")

        for user_id in inactive_users:
            logging.warning(f"Cleaning up inactive connection: {user_id}")
            await self.force_disconnect(user_id)

    async def force_disconnect(self, user_id: str):
        """Принудительно отключаем пользователя"""
        if user_id in self.active_connections:
            # Уведомляем партнера если есть
            partner_id = self.active_connections[user_id].get("partner_id")
            if partner_id and partner_id in self.active_connections:
                try:
                    await self.send_personal_message(
                        json.dumps({
                            "type": "partner_disconnected",
                            "message": "Your conversation partner has disconnected"
                        }),
                        partner_id
                    )
                    # Очищаем partner_id у партнера
                    self.active_connections[partner_id]["partner_id"] = None
                except:
                    pass

            # Удаляем из всех списков
            if user_id in self.active_connections:
                del self.active_connections[user_id]
            if user_id in self.last_activity:
                del self.last_activity[user_id]

            # Удаляем из очереди ожидания
            self.waiting_users = [user for user in self.waiting_users if user.get('user_id') != user_id]

            logging.info(f"Force disconnected user {user_id}")

    def disconnect(self, user_id: str):
        """Удаляем пользователя при отключении"""
        if user_id in self.active_connections:
            del self.active_connections[user_id]

        # Также удаляем из очереди ожидания
        self.waiting_users = [user for user in self.waiting_users if user.get('user_id') != user_id]
        logging.info(f"User {user_id} disconnected")

    async def find_partner(self, current_user: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Ищем подходящего партнера для пользователя"""
        user_id = current_user.get('user_id')
        user_country = current_user.get('country')
        user_language = current_user.get('language')

        logging.info(f"Finding partner for user {user_id} from {user_country}")
        logging.info(f"Current waiting queue: {len(self.waiting_users)} users: {[user.get('country') for user in self.waiting_users]}")

        # Сначала удаляем текущего пользователя из очереди (если он там есть)
        self.waiting_users = [user for user in self.waiting_users if user.get('user_id') != user_id]

        for i, waiting_user in enumerate(self.waiting_users):
            logging.info(f"Checking user {i}: {waiting_user.get('country')} (ID: {waiting_user.get('user_id')})")

            # Ищем пользователя из ДРУГОЙ страны
            if (waiting_user.get('country') != user_country and
                waiting_user.get('user_id') != user_id):

                # Нашли пару! Удаляем из очереди ожидания
                self.waiting_users.remove(waiting_user)
                logging.info(f"✅ Matched user {user_id} from {user_country} with {waiting_user.get('user_id')} from {waiting_user.get('country')}")
                logging.info(f"✅ Queue after match: {len(self.waiting_users)} users")
                return waiting_user

        # Если пару не нашли, добавляем текущего пользователя в очередь
        if not any(user.get('user_id') == user_id for user in self.waiting_users):
            self.waiting_users.append(current_user)
            logging.info(f"⏳ User {user_id} from {user_country} added to waiting list. Queue size: {len(self.waiting_users)}")

        return None

    async def send_personal_message(self, message: str, user_id: str):
        """Отправляем сообщение конкретному пользователю"""
        if user_id in self.active_connections:
            connection = self.active_connections[user_id]["websocket"]
            await connection.send_text(message)

    def get_waiting_queue_size(self) -> int:
        """Возвращает размер очереди ожидания (для тестирования)"""
        return len(self.waiting_users)


    async def move_to_chat_mode(self, user_id: str, partner_id: str):
        """Переводим пользователя в режим чата"""
        if user_id in self.active_connections:
            self.active_connections[user_id]["partner_id"] = partner_id
            # Удаляем из очереди ожидания
            self.waiting_users = [user for user in self.waiting_users if user.get('user_id') != user_id]
            logging.info(f"User {user_id} moved to chat mode with partner {partner_id}")