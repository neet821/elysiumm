#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试数据库和API连接"""

print("=" * 50)
print("开始测试...")
print("=" * 50)

# 测试1: 导入模块
try:
    print("\n1. 测试导入模块...")
    from database import engine, SessionLocal
    import models, crud
    print("✓ 模块导入成功")
except Exception as e:
    print(f"✗ 模块导入失败: {e}")

# 测试2: 数据库连接
try:
    print("\n2. 测试数据库连接...")
    from database import engine
    conn = engine.connect()
    print("✓ 数据库连接成功")
    conn.close()
except Exception as e:
    print(f"✗ 数据库连接失败: {e}")
    print("   请确保MySQL服务正在运行")
    print("   数据库: blue_local_db")
    print("   用户: root")
    print("   密码: (空)")

# 测试3: 检查表
try:
    print("\n3. 检查数据库表...")
    from database import engine
    from sqlalchemy import inspect
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"✓ 找到 {len(tables)} 个表:")
    for table in tables:
        print(f"   - {table}")
except Exception as e:
    print(f"✗ 检查表失败: {e}")

# 测试4: 测试API端口
try:
    print("\n4. 测试API端口...")
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', 8000))
    sock.close()
    if result == 0:
        print("✓ 端口8000可访问")
    else:
        print("✗ 端口8000不可访问 - 后端服务可能未启动")
except Exception as e:
    print(f"✗ 端口测试失败: {e}")

print("\n" + "=" * 50)
print("测试完成")
print("=" * 50)
