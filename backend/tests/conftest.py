import sys
from pathlib import Path

# 让测试在 backend 目录下直接 import app 包
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402

# 既有接口用例默认关闭鉴权；鉴权行为在 test_auth.py 里显式打开
settings.auth_enabled = False
