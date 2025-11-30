from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import json
import uuid
import logging
import sys
import os
import asyncio
import time

# Добавляем путь для импортов
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.connection_manager import ConnectionManager

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CONNECTION_TIMEOUT = 60

@asynccontextmanager
async def lifespan(_: FastAPI):
    # Startup
    logging.info("Starting Bridge server...")
    cleanup_task = asyncio.create_task(periodic_cleanup())
    yield
    # Shutdown
    logging.info("Shutting down Bridge server...")
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass

app = FastAPI(
    title="Bridge API",
    description="Backend for Bridge App",
    lifespan=lifespan
)

# CORS для разработки
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


manager = ConnectionManager()


async def periodic_cleanup():
    """Периодическая очистка неактивных соединений"""
    while True:
        await asyncio.sleep(60)  # Проверяем каждую минуту
        try:
            await manager.cleanup_inactive_connections()
            logging.info(f"Cleanup completed. Active: {len(manager.active_connections)}, Waiting: {manager.get_waiting_queue_size()}")
        except Exception as e:
            logging.error(f"Cleanup error: {e}")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # Принимаем соединение
    await websocket.accept()

    user_id = str(uuid.uuid4())
    current_user = {}
    logger.info(f"🔵 NEW WEBSOCKET CONNECTION: {user_id}")

    try:
        # Ждем первоначальные данные от пользователя
        data = await websocket.receive_text()
        user_data = json.loads(data)
        user_data["user_id"] = user_id
        current_user = user_data

        logger.info(f"🔵 CLIENT {user_id} FROM {user_data.get('country')} CONNECTED")

        # Подключаем пользователя
        await manager.connect(websocket, user_id, user_data)

        # Отправляем подтверждение подключения
        await manager.send_personal_message(
            json.dumps({
                "type": "connection_established",
                "user_id": user_id,
                "message": "Successfully connected to Bridge server"
            }),
            user_id
        )
        logger.info(f"🔵 CLIENT {user_id} SENT connection_established")

        # Пытаемся найти пару
        partner = await manager.find_partner(user_data)

        if partner:
            logger.info(
                f"🟢 MATCH: {user_id} ({user_data.get('country')}) <-> {partner['user_id']} ({partner.get('country')})")

            # Сохраняем информацию о паре в объектах пользователей
            if user_id in manager.active_connections:
                manager.active_connections[user_id]["partner_id"] = partner['user_id']
            if partner['user_id'] in manager.active_connections:
                manager.active_connections[partner['user_id']]["partner_id"] = user_id

            # ПЕРЕВОДИМ ПЕРВОГО КЛИЕНТА В РЕЖИМ ЧАТА
            await manager.move_to_chat_mode(partner['user_id'], user_id)

            # Уведомляем каждого пользователя о ПАРТНЕРЕ (разные сообщения!)
            # ОТПРАВЛЯЕМ ПЕРВОМУ ПОЛЬЗОВАТЕЛЮ
            logger.info(f"📤 SENDING match_found to {user_id}")
            await manager.send_personal_message(
                json.dumps({
                    "type": "match_found",
                    "message": "Partner found! Ready to start conversation.",
                    "partner_country": partner.get('country', 'Unknown'),
                    "partner_language": partner.get('language', 'Unknown'),
                    "your_country": user_data.get('country', 'Unknown')
                }),
                user_id
            )

            # ОТПРАВЛЯЕМ ВТОРОМУ ПОЛЬЗОВАТЕЛЮ
            logger.info(f"📤 SENDING match_found to {partner['user_id']}")
            await manager.send_personal_message(
                json.dumps({
                    "type": "match_found",
                    "message": "Partner found! Ready to start conversation.",
                    "partner_country": user_data.get('country', 'Unknown'),
                    "partner_language": user_data.get('language', 'Unknown'),
                    "your_country": partner.get('country', 'Unknown')
                }),
                partner['user_id']
            )

            logger.info(f"🎯 BOTH USERS MOVED TO CHAT MODE")
            logger.info(f"🎯 STARTING CHAT SESSIONS")
            logger.info(f"🎯 {user_id} partner_id: {manager.active_connections[user_id].get('partner_id')}")
            logger.info(
                f"🎯 {partner['user_id']} partner_id: {manager.active_connections[partner['user_id']].get('partner_id')}")

            # Проверим, оба ли пользователя перешли в режим чата
            if manager.active_connections[user_id].get("partner_id") != partner['user_id']:
                logger.error(
                    f"❌ USER {user_id} HAS WRONG PARTNER_ID: {manager.active_connections[user_id].get('partner_id')}")
            if manager.active_connections[partner['user_id']].get("partner_id") != user_id:
                logger.error(
                    f"❌ PARTNER {partner['user_id']} HAS WRONG PARTNER_ID: {manager.active_connections[partner['user_id']].get('partner_id')}")

            logger.info(f"🟢 ENTERING CHAT LOOP for {user_id}")

            # ОСНОВНОЙ ЦИКЛ ОБРАБОТКИ СООБЩЕНИЙ ДЛЯ ЭТОЙ ПАРЫ
            try:
                logger.info(f"🟢 USER {user_id} ENTERED MAIN CHAT LOOP")

                while True:
                    data = await websocket.receive_text()
                    message_data = json.loads(data)
                    logger.info(f"📨 MESSAGE FROM {user_id}: {message_data}")

                    if message_data.get("type") == "chat_message":
                        partner_id = manager.active_connections[user_id].get("partner_id")
                        logger.info(f"🔍 Looking for partner {partner_id} for user {user_id}")

                        if partner_id and partner_id in manager.active_connections:
                            chat_message = json.dumps({
                                "type": "chat_message",
                                "text": message_data.get("text", ""),
                                "from_user": user_id
                            })
                            logger.info(f"📤 FORWARDING from {user_id} to {partner_id}: {message_data.get('text')}")
                            await manager.send_personal_message(chat_message, partner_id)
                            logger.info(f"✅ MESSAGE FORWARDED SUCCESSFULLY")

                    # Обрабатываем heartbeat
                    elif message_data.get("type") == "heartbeat":
                        manager.update_activity(user_id)
                        logger.debug(f"💓 Heartbeat from {user_id}")

            except WebSocketDisconnect:
                logger.info(f"🔴 USER {user_id} DISCONNECTED FROM CHAT - WebSocketDisconnect")
                # Уведомляем партнера об отключении
                partner_id = manager.active_connections[user_id].get("partner_id")
                if partner_id and partner_id in manager.active_connections:
                    await manager.send_personal_message(
                        json.dumps({
                            "type": "partner_disconnected",
                            "message": "Your conversation partner has disconnected"
                        }),
                        partner_id
                    )
                    # Очищаем partner_id у партнера
                    manager.active_connections[partner_id]["partner_id"] = None
                raise  # Повторно вызываем исключение для обработки во внешнем блоке

            except Exception as e:
                logger.error(f"🔴 USER {user_id} CRITICAL ERROR IN CHAT LOOP: {e}")

        else:
            # Код для пользователя в очереди ожидания
            logger.info(f"🟡 {user_id} ADDED TO WAITING QUEUE")
            await manager.send_personal_message(
                json.dumps({
                    "type": "waiting",
                    "message": "Looking for a conversation partner...",
                    "queue_position": manager.get_waiting_queue_size()
                }),
                user_id
            )

            # Цикл ожидания
            try:
                chat_mode_activated = False
                while not chat_mode_activated:
                    # Проверяем, не нашли ли нам пару
                    if user_id in manager.active_connections and manager.active_connections[user_id].get("partner_id"):
                        logger.info(f"🟢 USER {user_id} TRANSITIONING FROM WAITING TO CHAT")
                        chat_mode_activated = True
                        break

                    # Ждем сообщения с таймаутом
                    try:
                        data = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                        message_data = json.loads(data)
                        logger.info(f"⏳ WAITING USER {user_id} SENT: {message_data}")

                        if message_data.get("type") == "chat_message":
                            logger.info(f"❌ WAITING USER {user_id} TRIED TO SEND MESSAGE")
                            await manager.send_personal_message(
                                json.dumps({
                                    "type": "error",
                                    "message": "You are still waiting for a partner"
                                }),
                                user_id
                            )

                        elif message_data.get("type") == "heartbeat":
                            manager.update_activity(user_id)
                            logger.debug(f"💓 Heartbeat from WAITING user {user_id}")

                    except asyncio.TimeoutError:
                        # Таймаут - проверяем состояние снова
                        continue

                # ЕСЛИ ВЫШЛИ ИЗ ЦИКЛА ОЖИДАНИЯ - ПЕРЕХОДИМ В РЕЖИМ ЧАТА
                if chat_mode_activated:
                    logger.info(f"🟢 USER {user_id} ENTERING CHAT MODE AFTER WAITING")

                    while True:
                        data = await websocket.receive_text()
                        message_data = json.loads(data)
                        logger.info(f"📨 MESSAGE FROM {user_id} (FROM WAITING): {message_data}")

                        if message_data.get("type") == "chat_message":
                            partner_id = manager.active_connections[user_id].get("partner_id")
                            if partner_id and partner_id in manager.active_connections:
                                chat_message = json.dumps({
                                    "type": "chat_message",
                                    "text": message_data.get("text", ""),
                                    "from_user": user_id
                                })
                                await manager.send_personal_message(chat_message, partner_id)

                        elif message_data.get("type") == "heartbeat":
                            manager.update_activity(user_id)
                            logger.debug(f"💓 Heartbeat from CHAT user {user_id}")

            except WebSocketDisconnect:
                logger.info(f"🔴 {user_id} DISCONNECTED FROM WAITING")


    except WebSocketDisconnect:
        logger.info(f"User {user_id} disconnected")
        # Уведомляем партнера если он есть
        if user_id in manager.active_connections:
            partner_id = manager.active_connections[user_id].get("partner_id")
            if partner_id and partner_id in manager.active_connections:
                await manager.send_personal_message(
                    json.dumps({
                        "type": "partner_disconnected",
                        "message": "Your conversation partner has disconnected"
                    }),
                    partner_id
                )
        manager.disconnect(user_id)
    except Exception as e:
        logger.error(f"Error with user {user_id}: {str(e)}")
        manager.disconnect(user_id)


@app.get("/")
async def root():
    return {"message": "Bridge API is running!", "status": "OK"}


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "active_connections": len(manager.active_connections),
        "waiting_users": manager.get_waiting_queue_size()
    }


@app.get("/stats")
async def get_stats():
    """Получаем статистику сервера"""
    active_pairs = 0
    for user_data in manager.active_connections.values():
        if user_data.get("partner_id"):
            active_pairs += 1
    active_pairs = active_pairs // 2  # Каждая пара учитывается дважды

    return {
        "active_connections": len(manager.active_connections),
        "waiting_users": manager.get_waiting_queue_size(),
        "active_conversations": active_pairs
    }


@app.get("/debug/state")
async def debug_state():
    """Подробная отладочная информация"""
    state = {
        "active_connections": {},
        "waiting_users": [],
        "issues": []
    }

    # Информация о активных соединениях
    for user_id, data in manager.active_connections.items():
        partner_id = data.get("partner_id")
        partner_info = "None"
        if partner_id and partner_id in manager.active_connections:
            partner_info = f"{partner_id} ({manager.active_connections[partner_id]['user_data'].get('country')})"

        state["active_connections"][user_id] = {
            "country": data["user_data"].get("country"),
            "partner_id": partner_id,
            "partner_info": partner_info,
            "in_waiting": any(u.get('user_id') == user_id for u in manager.waiting_users)
        }

        # Проверяем проблемы
        if partner_id and partner_id not in manager.active_connections:
            state["issues"].append(f"User {user_id} has invalid partner {partner_id}")

    # Информация о очереди ожидания
    state["waiting_users"] = [
        {"user_id": u.get("user_id"), "country": u.get("country")}
        for u in manager.waiting_users
    ]

    return state

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)