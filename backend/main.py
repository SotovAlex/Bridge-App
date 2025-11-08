"""
Основной модуль бэкенд сервера Bridge-App
"""
from flask import Flask
from flask_restful import Api
import os

def create_app():
    app = Flask(__name__)
    api = Api(app)
    
    # Конфигурация
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
    
    # Здесь будут регистрироваться роуты
    # from backend.api.routes import SomeResource
    # api.add_resource(SomeResource, '/api/some-endpoint')
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5000)
