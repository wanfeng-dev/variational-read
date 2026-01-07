# -*- coding: utf-8 -*-
"""
数据库连接与会话管理
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

import sys
sys.path.append("..")
from config import DATABASE_URL

# 创建数据库引擎
# SQLite 需要 check_same_thread=False 以支持多线程
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, echo=False)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """
    获取数据库会话的依赖注入函数
    用于 FastAPI 的 Depends
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
