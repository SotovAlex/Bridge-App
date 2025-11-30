import asyncio
import websockets
import json
from threading import Thread
from kivy.clock import Clock
from kivy.logger import Logger
import sys
import os

# Добавляем путь для импортов если нужно
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class BridgeClient:
    def __init__(self):
        self.websocket = None
        self.connected = False
        self.user_id = None
        self.on_message_callback = None
        self.on_status_callback = None

    def set_callbacks(self, message_callback, status_callback):
        """Устанавливаем callback-функции для обновления UI"""
        self.on_message_callback = message_callback
        self.on_status_callback = status_callback

    async def _listen_messages(self):
        """Прослушиваем сообщения от сервера"""
        try:
            async for message in self.websocket:
                await self._handle_message(message)
        except websockets.exceptions.ConnectionClosed as e:
            Logger.error(f"BridgeClient: Connection closed: {e}")
            self._update_status("Connection closed")
            self.connected = False
        except Exception as e:
            Logger.error(f"BridgeClient: Listen error: {e}")
            self.connected = False
            self._update_status("Connection error")

    async def _handle_message(self, message):
        """Обрабатываем входящие сообщения"""
        try:
            data = json.loads(message)
            Logger.info(f"BridgeClient: Received message type: {data.get('type')}")
            Logger.info(f"BridgeClient: Full message: {data}")

            if data["type"] == "connection_established":
                self.user_id = data.get("user_id")
                self._update_status("Connected to server")
                Logger.info(f"BridgeClient: Connection established, user_id: {self.user_id}")

            elif data["type"] == "match_found":
                partner_country = data.get("partner_country", "unknown country")
                your_country = data.get("your_country", "unknown")
                Logger.info(f"BridgeClient: MATCH FOUND! You: {your_country}, Partner: {partner_country}")
                self._update_status(f"Connected with partner from {partner_country}!")
                self._show_message(f"System: You are connected! You from {your_country}, partner from {partner_country}")

            elif data["type"] == "waiting":
                queue_pos = data.get("queue_position", 0)
                Logger.info(f"BridgeClient: Still waiting... queue position: {queue_pos}")
                self._update_status(f"Looking for partner... Queue position: {queue_pos}")

            elif data["type"] == "chat_message":
                text = data.get("text", "")
                from_user = data.get("from_user", "")
                Logger.info(f"BridgeClient: Received chat message from {from_user}: {text}")
                display_text = f"Partner: {text}" if from_user != self.user_id else f"You: {text}"
                self._show_message(display_text)
                Logger.info(f"BridgeClient: Displaying chat message: {display_text}")

            elif data["type"] == "partner_disconnected":
                Logger.info("BridgeClient: Partner disconnected")
                self._show_message("System: Your partner has disconnected")
                self._update_status("Partner disconnected")

            elif data["type"] == "error":
                error_msg = data.get("message", "Unknown error")
                Logger.error(f"BridgeClient: Server error: {error_msg}")
                self._show_message(f"Error: {error_msg}")

        except json.JSONDecodeError as e:
            Logger.error(f"BridgeClient: JSON decode error: {e}")
        except Exception as e:
            Logger.error(f"BridgeClient: Message handling error: {e}")

    async def send_message(self, text):
        """Отправляем текстовое сообщение"""
        if self.connected and self.websocket:
            try:
                message_data = {
                    "type": "chat_message",
                    "text": text,
                    "user_id": self.user_id
                }
                Logger.info(f"BridgeClient: Sending message: {text}")
                await self.websocket.send(json.dumps(message_data))
                # НЕ добавляем сообщение здесь - ждем подтверждения от сервера
            except Exception as e:
                Logger.error(f"BridgeClient: Send message error: {e}")
                self._show_message(f"Error sending message: {e}")

    async def disconnect(self):
        """Отключаемся от сервера"""
        if self.websocket:
            await self.websocket.close()
        self.connected = False
        self._update_status("Disconnected")

    def _update_status(self, status):
        """Обновляем статус через callback (безопасно для Kivy)"""
        if self.on_status_callback:
            Clock.schedule_once(lambda dt: self.on_status_callback(status))

    def _show_message(self, message):
        """Показываем сообщение через callback"""
        if self.on_message_callback:
            Clock.schedule_once(lambda dt: self.on_message_callback(message))

    async def _heartbeat(self):
        """Отправляем heartbeat сообщения"""
        while self.connected and self.websocket:
            try:
                await asyncio.sleep(15)  # Каждые 15 секунд (меньше чем таймаут 30s)
                if self.connected and self.websocket:
                    heartbeat_msg = json.dumps({"type": "heartbeat"})
                    await self.websocket.send(heartbeat_msg)
                    Logger.debug("BridgeClient: Heartbeat sent")
            except Exception as e:
                Logger.error(f"BridgeClient: Heartbeat error: {e}")
                break

    async def connect(self, country="Russia", language="en"):
        """Подключаемся к WebSocket серверу"""
        try:
            self._update_status("Connecting to server...")

            self.websocket = await websockets.connect("ws://localhost:8000/ws", ping_interval=20, ping_timeout=10)
            self.connected = True
            self.in_chat_mode = False  # Сбрасываем флаг чата

            # Отправляем данные пользователя
            user_data = {
                "country": country,
                "language": language
            }
            await self.websocket.send(json.dumps(user_data))
            self._update_status("Waiting for partner...")

            # Запускаем heartbeat в фоне
            asyncio.create_task(self._heartbeat())

            # Запускаем прослушивание сообщений
            await self._listen_messages()

        except Exception as e:
            self._update_status(f"Connection error: {str(e)}")
            self.connected = False


# Глобальный экземпляр клиента
client = BridgeClient()


def run_async_task(coro):
    """Запускаем асинхронную задачу в отдельном потоке"""

    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(coro)

    Thread(target=run, daemon=True).start()