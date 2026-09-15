#!/usr/bin/env sh
set -e

echo "Running database migrations..."
# 迁移失败必须中止启动（set -e）：旧 schema 上跑新代码会把故障推迟到运行时。
python -m app.db.migrate

# 在线 Demo：注入/复用「林小满」演示账号（demo@zhijizhibi.app）。
# seed_demo 本身幂等（已存在则跳过），且强制 AI_PROVIDER=mock，绝不联网、零费用。
# 用 SEED_DEMO 开关闸住，避免影响 docker-compose / 本地等非 Demo 环境。
if [ "${SEED_DEMO:-0}" = "1" ]; then
  echo "Seeding demo user..."
  python -m app.db.seed_demo
fi

echo "Starting API..."
# 云平台（Render 等）通过 PORT 注入监听端口；本地 / docker-compose 缺省仍为 8000。
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
