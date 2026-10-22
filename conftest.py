import os
import socket
import sys
import time
import subprocess
import pytest

# 系统测试的服务进程：测试开始前拉起 uvicorn 监听 127.0.0.1:8100（避开开发时常用的 8000 端口），
# 全部测试结束后自动关闭；只有 UI 测试用到这个 fixture，普通接口测试不受影响
@pytest.fixture(scope="session")
def server():
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8100"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # 轮询端口直到服务就绪，最多等 30 秒
    deadline = time.time() + 30
    ready = False
    while time.time() < deadline:
        try:
            s = socket.create_connection(("127.0.0.1", 8100), timeout=1)
            s.close()
            ready = True
            break
        except OSError:
            time.sleep(0.5)
    assert ready, "系统测试服务启动失败（uvicorn 8100 端口未就绪）"
    yield "http://127.0.0.1:8100"
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()