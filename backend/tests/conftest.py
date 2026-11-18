import sys
from pathlib import Path

# 让测试在 backend 目录下直接 import app 包
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
