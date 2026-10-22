# AI 智能面试助手（interview-ai）

基于大语言模型的智能面试辅导系统：集题库管理、AI 问答、AI 出题、模拟面试、模拟测试、答题记录与统计于一体的 Web 应用，同时作为毕业设计《基于大语言模型的智能面试辅导系统的设计与实现》的实现项目。

## 功能特性

- 用户系统：注册 / 登录 / 修改密码 / 个人中心，密码 bcrypt 加密存储
- 题库管理：增删改查、按分类/难度/关键词搜索筛选、标签、分页、按数量随机组卷
- AI 问答：多轮对话记忆，SSE 流式逐字输出（/ask/stream）
- AI 出题：按主题出题自动落库；按岗位 JD 批量出题（RAG 检索增强，重复标题自动跳过）
- 模拟面试：面试官人设点评追问 + 面试总结报告，流式输出（/interview/stream）
- 模拟测试：随机组卷、整卷 AI 批改、得分统计
- 答题记录：题库单题 AI 评分点评、错题本筛选、数据按用户隔离
- 数据统计：总览卡片 + 分类柱状图 + 难度饼图（Chart.js）
- RAG 检索增强：sqlite-vec 向量库，题目自动向量化，按题目库检索增强出题
- 可观测性：Prometheus 指标（/metrics）+ 请求计数与耗时直方图
- 部署：Docker Compose 一键拉起应用 + Prometheus

## 技术栈

- 后端：Python / FastAPI / SQLAlchemy / SQLite / sqlite-vec / Pydantic / passlib(bcrypt) / httpx / prometheus-client
- 前端：原生 HTML/CSS/JS + Bootstrap 5 + Chart.js（CDN）
- 大模型：阿里云百炼（DashScope）OpenAI 兼容接口，qwen-plus（对话）+ text-embedding-v3（向量）
- 测试：pytest + TestClient（接口 mock 测试）、Playwright（UI 自动化）、Allure（测试报告）
- 部署：Docker / Docker Compose / Prometheus

## 快速开始

### 1. 环境准备

- Python 3.11（推荐 conda 环境 `ctfd`）
- 安装依赖（清华源）：

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 2. 配置大模型密钥

设置环境变量 `DASHSCOPE_API_KEY`（阿里云百炼 API Key，Windows PowerShell）：

```powershell
setx DASHSCOPE_API_KEY "你的密钥"
```

> 修改环境变量后需重启 uvicorn 服务进程才能生效。

### 3. 启动服务

```bash
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

浏览器访问 http://127.0.0.1:8000/

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /register | 注册（重复用户名 409，非法参数 422） |
| POST | /login | 登录（错误 401） |
| POST | /change-password | 修改密码 |
| GET | /questions | 题目列表（支持 category/difficulty/q 筛选、limit/offset 分页、random/count 随机取题） |
| POST | /questions | 新建题目（重复标题 409） |
| GET | /questions/{id} | 题目详情 |
| PUT | /questions/{id} | 更新题目 |
| DELETE | /questions/{id} | 删除题目 |
| POST | /ask | AI 问答（一次性返回完整回答） |
| POST | /ask/stream | AI 问答（SSE 流式逐字返回） |
| POST | /ask-question | AI 按主题出 1 道题 |
| POST | /ask-questions | AI 按岗位 JD 批量出题（RAG 检索增强自动落库） |
| POST | /interview | 模拟面试官提问（一次性返回） |
| POST | /interview/stream | 模拟面试官提问（SSE 流式返回） |
| POST | /interview-summary | 生成面试总结报告 |
| POST | /quiz-grade | 模拟测试整卷批改 |
| POST | /grade | 题库单题 AI 评分点评 |
| GET | /api/records | 我的答题记录（支持 wrong 筛选错题） |
| GET | /api/stats | 我的答题统计 |
| GET | /rag-search | RAG 相似题目检索 |
| GET | /metrics | Prometheus 监控指标 |
| GET | /hello/{name}、/greet | 入门教学示例接口 |

## 页面路由

| 路径 | 页面 |
|------|------|
| / | AI 问答主页 |
| /login、/register | 登录 / 注册 |
| /bank | 题库列表 |
| /bank/new | 添加题目 / AI 出题 |
| /interview | 模拟面试 |
| /quiz | 模拟测试 |
| /stats | 数据统计 |
| /records | 答题记录 |
| /profile | 个人中心 |

## 运行测试

接口自动化测试（不依赖大模型与真实网络，全部 mock）：

```bash
conda run -n ctfd python -m pytest test_main.py -q
```

UI 自动化测试（Playwright 真实浏览器，自动拉起 8100 端口服务）：

```bash
conda run -n ctfd python -m pytest test_ui.py -q --alluredir=allure-results
```

生成 Allure HTML 报告（需便携版工具，E:\CODE\tools\jre 与 allure-2.33.0）：

```powershell
$env:JAVA_HOME="E:\CODE\tools\jre\jdk-17.0.20.1+1-jre"; $env:PATH="$env:JAVA_HOME\bin;E:\CODE\tools\allure-2.33.0\bin;"+$env:PATH
allure generate allure-results -o allure-report --clean
```

## Docker 部署

```bash
docker compose up --build
```

- 应用：http://localhost:8000
- Prometheus：http://localhost:9090
- 停止：`docker compose down`

## 项目结构

```
interview-ai/
├── main.py            # FastAPI 单文件后端（ORM 模型、全部接口、RAG、SSE、监控）
├── test_main.py       # 接口自动化测试（pytest + TestClient + mock）
├── test_ui.py         # UI 自动化测试（Playwright）
├── conftest.py        # 测试 fixture（UI 测试自动拉起服务）
├── requirements.txt   # Python 依赖清单
├── Dockerfile         # 应用镜像
├── docker-compose.yml # 应用 + Prometheus 编排
├── prometheus.yml     # Prometheus 抓取配置
├── .dockerignore      # 镜像构建忽略清单
├── app.db             # SQLite 数据库（users/questions/records/vec_questions）
└── static/            # 前端页面（Bootstrap 5 + 原生 JS）
```

## 许可证

教学与毕业设计用途。