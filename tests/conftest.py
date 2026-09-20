"""
pytest 共享 fixture。

提供测试用 Flask 应用（TestingConfig + 内存 SQLite）与测试客户端。
"""

import pytest

from app import create_app
from config import TestingConfig
from models import db


@pytest.fixture
def app():
    """创建测试用 Flask 应用（内存 SQLite，每用例独立）。"""
    app = create_app(TestingConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """测试 HTTP 客户端。"""
    return app.test_client()
