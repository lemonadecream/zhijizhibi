#!/usr/bin/env sh
set -e

echo "Running database migrations..."
# 迁移失败必须中止启动（set -e）：旧 schema 上跑新代码会把故障推迟到运行时。
python -m app.db.migrate

echo "Starting API..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
