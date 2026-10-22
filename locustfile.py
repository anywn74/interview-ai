import time
import uuid
from locust import HttpUser, task, between

# 接口性能压测：模拟真实用户访问核心页面与接口，统计 QPS 与响应时间
# 运行方式：conda run -n ctfd python -m locust -f locustfile.py --host http://127.0.0.1:8100 --headless --users 50 --spawn-rate 10 --run-time 60s --html locust-report.html
class InterviewUser(HttpUser):
    wait_time = between(1, 2)

    @task(3)
    def home_page(self):
        # 主页（静态页面 + 前端资源走 /static）
        self.client.get("/")

    @task(2)
    def question_list(self):
        # 题库分页列表（数据库真实查询）
        self.client.get("/questions", params={"limit": 10, "offset": 0})

    @task(1)
    def register_and_login(self):
        # 注册 + 登录（压测产生的 load_ 开头用户需在压测后清理）
        username = "load_" + uuid.uuid4().hex[:12]
        self.client.post("/register", json={"username": username, "password": "load123456"})
        self.client.post("/login", json={"username": username, "password": "load123456"})