import pytest
import json
import sys
import os
import asyncio

# Добавляем путь к backend
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from backend.utils.connection_manager import ConnectionManager

class MockWebSocket:
    """Mock объект для тестирования WebSocket"""
    async def send_text(self, message):
        pass

@pytest.fixture
def manager():
    return ConnectionManager()

@pytest.mark.asyncio
async def test_connection_manager(manager):
    """Тестируем логику сопоставления пользователей"""
    # Создаем mock WebSocket соединения
    ws1, ws2 = MockWebSocket(), MockWebSocket()
    
    user1 = {"user_id": "user1", "country": "Russia", "language": "ru"}
    user2 = {"user_id": "user2", "country": "USA", "language": "en"}
    
    # Подключаем пользователей
    await manager.connect(ws1, "user1", user1)
    await manager.connect(ws2, "user2", user2)
    
    # user1 ищет пару - должен быть добавлен в очередь
    partner1 = await manager.find_partner(user1)
    assert partner1 is None
    assert manager.get_waiting_queue_size() == 1
    
    # user2 ищет пару - должен найти user1
    partner2 = await manager.find_partner(user2)
    assert partner2 is not None
    assert partner2["user_id"] == "user1"
    assert manager.get_waiting_queue_size() == 0

@pytest.mark.asyncio
async def test_same_country_no_match(manager):
    """Тестируем, что пользователи из одной страны не сопоставляются"""
    ws1, ws2 = MockWebSocket(), MockWebSocket()
    
    user1 = {"user_id": "user1", "country": "Russia", "language": "ru"}
    user2 = {"user_id": "user2", "country": "Russia", "language": "en"}  # Та же страна!
    
    await manager.connect(ws1, "user1", user1)
    await manager.connect(ws2, "user2", user2)
    
    # user1 ищет пару
    partner1 = await manager.find_partner(user1)
    assert partner1 is None
    assert manager.get_waiting_queue_size() == 1
    
    # user2 ищет пару - не должен найти user1 (та же страна)
    partner2 = await manager.find_partner(user2)
    assert partner2 is None
    assert manager.get_waiting_queue_size() == 2

@pytest.mark.asyncio
async def test_send_message(manager):
    """Тестируем отправку сообщений"""
    test_messages = []
    
    class RecordingWebSocket:
        async def send_text(self, message):
            test_messages.append(message)
    
    ws = RecordingWebSocket()
    user_data = {"user_id": "test_user", "country": "Test", "language": "test"}
    
    await manager.connect(ws, "test_user", user_data)
    await manager.send_personal_message("Hello, test!", "test_user")
    
    # Даем немного времени для асинхронной обработки
    await asyncio.sleep(0.1)
    
    assert len(test_messages) == 1
    assert "Hello, test!" in test_messages[0]

def test_disconnect(manager):
    """Тестируем отключение пользователя"""
    class SyncWebSocket:
        async def send_text(self, message):
            pass
    
    # Используем asyncio для запуска асинхронных операций в синхронном тесте
    async def run_test():
        ws = SyncWebSocket()
        user_data = {"user_id": "test_user", "country": "Test", "language": "test"}
        
        await manager.connect(ws, "test_user", user_data)
        await manager.find_partner(user_data)
        
        assert manager.get_waiting_queue_size() == 1
        manager.disconnect("test_user")
        assert manager.get_waiting_queue_size() == 0
    
    # Запускаем асинхронный код в синхронном тесте
    asyncio.run(run_test())