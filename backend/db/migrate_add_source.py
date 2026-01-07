# -*- coding: utf-8 -*-
"""
数据库迁移：为 snapshots 表添加 source 字段
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from db.database import engine


def migrate():
    """执行迁移：添加 source 字段"""
    with engine.connect() as conn:
        # 检查数据库类型
        dialect = engine.dialect.name
        
        if dialect == "sqlite":
            # SQLite: 检查字段是否已存在
            result = conn.execute(text(
                "SELECT COUNT(*) FROM pragma_table_info('snapshots') WHERE name='source'"
            ))
            if result.scalar() == 0:
                # 添加 source 字段，默认值为 variational
                conn.execute(text(
                    "ALTER TABLE snapshots ADD COLUMN source VARCHAR(20) DEFAULT 'variational'"
                ))
                conn.commit()
                print("成功添加 source 字段")
            else:
                print("source 字段已存在")
        
        elif dialect == "postgresql":
            # PostgreSQL: 检查字段是否已存在
            result = conn.execute(text("""
                SELECT COUNT(*) FROM information_schema.columns 
                WHERE table_name='snapshots' AND column_name='source'
            """))
            if result.scalar() == 0:
                conn.execute(text(
                    "ALTER TABLE snapshots ADD COLUMN source VARCHAR(20) DEFAULT 'variational'"
                ))
                conn.commit()
                print("成功添加 source 字段")
            else:
                print("source 字段已存在")
        
        else:
            print(f"不支持的数据库类型: {dialect}")


def rollback():
    """回滚迁移：删除 source 字段（谨慎使用）"""
    with engine.connect() as conn:
        dialect = engine.dialect.name
        
        if dialect == "sqlite":
            # SQLite 不支持直接删除列，需要重建表
            print("SQLite 不支持删除列，请手动处理")
        
        elif dialect == "postgresql":
            conn.execute(text(
                "ALTER TABLE snapshots DROP COLUMN IF EXISTS source"
            ))
            conn.commit()
            print("成功删除 source 字段")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="数据库迁移工具")
    parser.add_argument("--rollback", action="store_true", help="回滚迁移")
    args = parser.parse_args()
    
    if args.rollback:
        rollback()
    else:
        migrate()
