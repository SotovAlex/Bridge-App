from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import json
import uuid
import logging
import sys
import os

# Добавляем путь к корневой директории проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.connection_manager import ConnectionManager

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Bridge API", description="Backend for Bridge App")

# CORS для разработки
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

manager = ConnectionManager()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # Принимаем соединение
    await websocket.accept()

    user_id = str(uuid.uuid4())
    user_data = {}

    try:
        # Ждем первоначальные данные от пользователя
        data = await websocket.receive_text()
        user_data = json.loads(data)
        user_data["user_id"] = user_id

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

        # Пытаемся найти пару
        partner = await manager.find_partner(user_data)

        if partner:
            # Уведомляем обоих пользователей о успешном сопоставлении
            match_message = json.dumps({
                "type": "match_found",
                "message": "Partner found! Ready to start conversation.",
                "partner_country": partner.get('country', 'Unknown'),
                "partner_language": partner.get('language', 'Unknown')
            })

            await manager.send_personal_message(match_message, user_id)
            await manager.send_personal_message(match_message, partner['user_id'])

            logger.info(f"Successfully matched {user_id} with {partner['user_id']}")
        else:
            # Сообщаем о ожидании
            await manager.send_personal_message(
                json.dumps({
                    "type": "waiting",
                    "message": "Looking for a conversation partner...",
                    "queue_position": manager.get_waiting_queue_size()
                }),
                user_id
            )

        # Бесконечный цикл для поддержания соединения и обработки сообщений
        while True:
            data = await websocket.receive_text()
            # Здесь в будущем будет обработка сообщений чата
            logger.info(f"Message from {user_id}: {data}")

    except WebSocketDisconnect:
        logger.info(f"User {user_id} disconnected")
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
