"""
Тесты для бэкенд функциональности
"""
import pytest
import sys
import os

# Добавляем путь к backend в sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend'))

def test_sample():
    """Пример теста"""
    assert 1 + 1 == 2

# Здесь будут реальные тесты для бэкенда
