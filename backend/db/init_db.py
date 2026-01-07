# -*- coding: utf-8 -*-
"""
数据库初始化脚本
"""
import sys
import os

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import engine
from db.models import Base


def init_database():
    """初始化数据库，创建所有表"""
    print("正在初始化数据库...")
    Base.metadata.create_all(bind=engine)
    print("数据库初始化完成！")


def drop_all_tables():
    """删除所有表（谨慎使用）"""
    print("正在删除所有表...")
    Base.metadata.drop_all(bind=engine)
    print("所有表已删除！")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="数据库初始化工具")
    parser.add_argument("--drop", action="store_true", help="删除所有表后重建")
    args = parser.parse_args()
    
    if args.drop:
        drop_all_tables()
    
    init_database()
