import time
import json
import pytest
from main import app,engine
from sqlalchemy import text
from fastapi.testclient import TestClient

client=TestClient(app)

# 测试环境默认禁止真实网络请求：防止未 mock 的用例误连大模型；需要模拟上游的用例会在测试内部自己替换
def fake_post_offline(url,headers=None,json=None,timeout=None):
    raise Exception("测试环境禁止真实网络请求")

# 离线版假 Client：拦截一切流式请求（call_llm_stream 走 Client.send），防止漏 mock 时误连真实网络
class FakeClientOffline:
    def __init__(self,timeout=None):
        pass
    def build_request(self,method,url,headers=None,json=None):
        raise Exception("测试环境禁止真实网络请求")
    def close(self):
        pass

@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    monkeypatch.setattr("main.httpx.post",fake_post_offline)
    monkeypatch.setattr("main.httpx.Client",FakeClientOffline)


def test_root():
    response=client.get("/")
    assert response.status_code==200
    assert "AI 智能面试助手" in response.text

def test_hello():
    response=client.get("/hello/alex")
    assert response.status_code==200
    assert response.json()=={"hello":"alex"}

def test_greet():
    response=client.get("/greet",params={"name":"alex"})
    assert response.status_code==200
    assert response.json()=={"greet":"alex"}

    response=client.get("/greet")
    assert response.status_code==200
    assert response.json()=={"greet":"world"}

def test_register():
    username=f"user_{time.time()}"
    r=client.post("/register",json={"username":username,"password":"123"})
    assert r.status_code==200
    assert r.json()["ok"]==True
    assert "id" in r.json()

def test_register_duplicate():
    username=f"user_{time.time()}"
    r1=client.post("/register",json={"username":username,"password":"123"})
    assert r1.status_code==200
    r2=client.post("/register",json={"username":username,"password":"123"})
    assert r2.status_code==409
    assert r2.json()["detail"]=="用户名已存在"

def test_register_invalid():
    r1=client.post("/register",json={"username":"x"})
    assert r1.status_code==422

    r2=client.post("/register",json={"username":"","password":"x"})
    assert r2.status_code==422


def test_login():
    username=f"user_{time.time()}"
    r1=client.post("/register",json={"username":username,"password":"123"})
    assert r1.status_code==200
    r2=client.post("/login",json={"username":username,"password":"123"})
    assert r2.status_code==200
    assert r2.json()["ok"]==True
    assert "id" in r2.json()

def test_login_wrong_password():
    username=f"user_{time.time()}"
    r1=client.post("/register",json={"username":username,"password":"123"})
    assert r1.status_code==200
    r2=client.post("/login",json={"username":username,"password":"xx"})
    assert r2.status_code==401

def test_login_user_not_found():
    r=client.post("/login",json={"username":f"user_{time.time()}","password":"123"})
    assert r.status_code==401


def test_create_question():
    title=f"title_{time.time()}"
    r=client.post("/questions",json={"title":title,"category":"Python","difficulty":"简单","answer":"装饰器是..."})
    assert r.status_code==200
    assert r.json()["ok"]==True
    assert "id" in r.json()

def test_create_question_duplicate():
    title=f"title_{time.time()}"
    r1=client.post("/questions",json={"title":title,"category":"Python","difficulty":"简单","answer":"装饰器是..."})
    assert r1.status_code==200
    r2=client.post("/questions",json={"title":title,"category":"Python","difficulty":"简单","answer":"装饰器是..."})
    assert r2.status_code==409

def test_create_question_invalid():
    title=f"title_{time.time()}"
    r1=client.post("/questions",json={"title":title,"category":"Python","difficulty":"简单"})
    assert r1.status_code==422
    r2=client.post("/questions",json={"title":"","category":"Python","difficulty":"简单","answer":"装饰器是..."})
    assert r2.status_code==422

def test_get_questions():
    title=f"title_{time.time()}"
    r1=client.post("/questions",json={"title":title,"category":"Python","difficulty":"简单","answer":"装饰器是..."})
    assert r1.status_code==200
    r2=client.get("/questions")
    titles=[q["title"] for q in r2.json()]
    assert title in titles

def test_get_question():
    title=f"title_{time.time()}"
    r1=client.post("/questions",json={"title":title,"category":"Python","difficulty":"简单","answer":"装饰器是..."})
    assert r1.status_code==200
    qid=r1.json()["id"]
    r2=client.get(f"/questions/{qid}")
    assert r2.json()["title"]==title

#自造自删
def test_get_question_not_found():
    title=f"title_{time.time()}"
    r1=client.post("/questions",json={"title":title,"category":"Python","difficulty":"简单","answer":"装饰器是..."})
    assert r1.status_code==200
    qid=r1.json()["id"]
    r2=client.delete(f"/questions/{qid}")
    assert r2.status_code==200
    r3=client.get(f"/questions/{qid}")
    assert r3.status_code==404

def test_get_question_invalid():
    r=client.get("/questions/abc")
    assert r.status_code==422

def test_update_question():
    title=f"title_{time.time()}"
    r1=client.post("/questions",json={"title":title,"category":"Python","difficulty":"简单","answer":"装饰器是..."})
    assert r1.status_code==200
    qid=r1.json()["id"]
    new_title=f"title_{time.time()}"
    r2=client.put(f"/questions/{qid}",json={"title":new_title,"category":"Python","difficulty":"简单","answer":"装饰器是..."})
    assert r2.status_code==200
    assert r2.json()["title"]==new_title

def test_update_question_not_found():
    title=f"title_{time.time()}"
    r1=client.post("/questions",json={"title":title,"category":"Python","difficulty":"简单","answer":"装饰器是..."})
    assert r1.status_code==200
    qid=r1.json()["id"]
    r2=client.delete(f"/questions/{qid}")
    assert r2.status_code==200
    new_title=f"title_{time.time()}"
    r3=client.put(f"/questions/{qid}",json={"title":new_title,"category":"Python","difficulty":"简单","answer":"装饰器是..."})
    assert r3.status_code==404

def test_update_question_duplicate():
    title_A=f"title_{time.time()}"
    r1=client.post("/questions",json={"title":title_A,"category":"Python","difficulty":"简单","answer":"装饰器是..."})
    assert r1.status_code==200
    title_B=f"title_{time.time()}"
    r2=client.post("/questions",json={"title":title_B,"category":"Python","difficulty":"简单","answer":"装饰器是..."})
    assert r2.status_code==200
    qid=r1.json()["id"]
    r3=client.put(f"/questions/{qid}",json={"title":title_B,"category":"Python","difficulty":"简单","answer":"装饰器是..."})
    assert r3.status_code==409

def test_update_question_invalid():
    title=f"title_{time.time()}"
    r1=client.post("/questions",json={"title":title,"category":"Python","difficulty":"简单","answer":"装饰器是..."})
    assert r1.status_code==200
    qid=r1.json()["id"]
    new_title=f"title_{time.time()}"
    r2=client.put(f"/questions/{qid}",json={"title":new_title,"category":"Python","difficulty":"简单"})
    assert r2.status_code==422

def test_delete_question():
    title=f"title_{time.time()}"
    r1=client.post("/questions",json={"title":title,"category":"Python","difficulty":"简单","answer":"装饰器是..."})
    assert r1.status_code==200
    qid=r1.json()["id"]
    r2=client.delete(f"/questions/{qid}")
    assert r2.status_code==200
    r3=client.get(f"/questions/{qid}")
    assert r3.status_code==404

def test_delete_question_not_found():
    title=f"title_{time.time()}"
    r1=client.post("/questions",json={"title":title,"category":"Python","difficulty":"简单","answer":"装饰器是..."})
    assert r1.status_code==200
    qid=r1.json()["id"]
    r2=client.delete(f"/questions/{qid}")
    assert r2.status_code==200
    r3=client.delete(f"/questions/{qid}")
    assert r3.status_code==404

def test_delete_question_invalid():
    r2=client.delete("/questions/abc")
    assert r2.status_code==422

class FakeResponse:
    def __init__(self):
        self.status_code=200
    def json(self):
        c={"content":"这是假答案"}
        m={"message":c}
        r={"choices":[m]}
        return r



last_request={}

def fake_post(url,headers=None,json=None,timeout=None):
    last_request["json"]=json
    return FakeResponse()

def test_ask_success(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY","假密钥")
    monkeypatch.setattr("main.httpx.post",fake_post)
    r=client.post("/ask",json={"messages":[{"role":"user","content":"测试问题"}]})
    assert r.status_code==200
    assert r.json()["answer"]=="这是假答案"
    # 确认完整历史确实被转发给了大模型
    assert last_request["json"]["messages"][-1]["content"]=="测试问题"

class FakeBadResponse:
    def __init__(self):
        self.status_code=401

def fake_post_bad(url,headers=None,json=None,timeout=None):
    return FakeBadResponse()

def test_ask_upstream_error(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY","假密钥")
    monkeypatch.setattr("main.httpx.post",fake_post_bad)
    r=client.post("/ask",json={"messages":[{"role":"user","content":"测试问题"}]})
    assert r.status_code==502
    assert r.json()["detail"]=="模型服务返回错误"

def fake_post_broken(url,headers=None,json=None,timeout=None):
    raise Exception("网络断了")

def test_ask_network_error(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY","假密钥")
    monkeypatch.setattr("main.httpx.post",fake_post_broken)
    r=client.post("/ask",json={"messages":[{"role":"user","content":"测试问题"}]})
    assert r.status_code==502
    assert r.json()["detail"]=="调用大模型服务失败"

def test_ask_missing_key(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY",raising=False)
    r=client.post("/ask",json={"messages":[{"role":"user","content":"测试问题"}]})
    assert r.status_code==500
    assert r.json()["detail"]=="未配置API密钥"

def test_ask_invalid():
    r=client.post("/ask",json={"messages":[]})
    assert r.status_code==422

# ---- /ask-question 的 mock 测试 ----
content_holder={}

class FakeContentResponse:
    def __init__(self):
        self.status_code=200
    def json(self):
        return {"choices":[{"message":{"content":content_holder["content"]}}]}

def fake_post_content(url,headers=None,json=None,timeout=None):
    last_request["json"]=json
    return FakeContentResponse()

def test_ask_question_success(monkeypatch):
    title=f"ai_title_{time.time()}"
    content_holder["content"]='```json\n'+json.dumps({"title":title,"category":"Python","difficulty":"中等","answer":"参考答案"},ensure_ascii=False)+'\n```'
    monkeypatch.setenv("DASHSCOPE_API_KEY","假密钥")
    monkeypatch.setattr("main.httpx.post",fake_post_content)
    r=client.post("/ask-question",json={"topic":"出一道 Python 题"})
    assert r.status_code==200
    assert r.json()["title"]==title
    # 复查题目确实写进了题库
    r2=client.get("/questions")
    titles=[q["title"] for q in r2.json()]
    assert title in titles

def test_ask_question_bad_format(monkeypatch):
    content_holder["content"]="今天天气不错"
    monkeypatch.setenv("DASHSCOPE_API_KEY","假密钥")
    monkeypatch.setattr("main.httpx.post",fake_post_content)
    r=client.post("/ask-question",json={"topic":"出一道 Python 题"})
    assert r.status_code==502
    assert r.json()["detail"]=="模型未按格式返回"

def test_ask_question_duplicate(monkeypatch):
    title=f"ai_title_{time.time()}"
    r1=client.post("/questions",json={"title":title,"category":"Python","difficulty":"简单","answer":"答案"})
    assert r1.status_code==200
    content_holder["content"]=json.dumps({"title":title,"category":"Python","difficulty":"简单","answer":"答案"},ensure_ascii=False)
    monkeypatch.setenv("DASHSCOPE_API_KEY","假密钥")
    monkeypatch.setattr("main.httpx.post",fake_post_content)
    r2=client.post("/ask-question",json={"topic":"出一道 Python 题"})
    assert r2.status_code==409
    assert r2.json()["detail"]=="题目已存在"

def test_ask_question_missing_key(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY",raising=False)
    r=client.post("/ask-question",json={"topic":"出一道 Python 题"})
    assert r.status_code==500
    assert r.json()["detail"]=="未配置API密钥"

def test_ask_question_invalid():
    r=client.post("/ask-question",json={"topic":""})
    assert r.status_code==422

# ---- /grade 与答题记录的 mock 测试 ----
def test_grade_success(monkeypatch):
    title=f"title_{time.time()}"
    r1=client.post("/questions",json={"title":title,"category":"Python","difficulty":"简单","answer":"标准答案"})
    assert r1.status_code==200
    qid=r1.json()["id"]
    content_holder["content"]=json.dumps({"correct":True,"score":"8/10","comment":"思路清晰"},ensure_ascii=False)
    monkeypatch.setenv("DASHSCOPE_API_KEY","假密钥")
    monkeypatch.setattr("main.httpx.post",fake_post_content)
    r2=client.post("/grade",json={"question_id":qid,"answer":"我的答案"})
    assert r2.status_code==200
    assert r2.json()["correct"]==1
    assert r2.json()["score"]=="8/10"
    # 复查记录确实写进了答题记录表
    r3=client.get("/api/records")
    titles=[x["question_title"] for x in r3.json()]
    assert title in titles

def test_grade_not_found(monkeypatch):
    title=f"title_{time.time()}"
    r1=client.post("/questions",json={"title":title,"category":"Python","difficulty":"简单","answer":"答案"})
    assert r1.status_code==200
    qid=r1.json()["id"]
    r2=client.delete(f"/questions/{qid}")
    assert r2.status_code==200
    monkeypatch.setenv("DASHSCOPE_API_KEY","假密钥")
    r3=client.post("/grade",json={"question_id":qid,"answer":"答案"})
    assert r3.status_code==404

def test_grade_bad_format(monkeypatch):
    title=f"title_{time.time()}"
    r1=client.post("/questions",json={"title":title,"category":"Python","difficulty":"简单","answer":"答案"})
    assert r1.status_code==200
    qid=r1.json()["id"]
    content_holder["content"]="随便说点什么"
    monkeypatch.setenv("DASHSCOPE_API_KEY","假密钥")
    monkeypatch.setattr("main.httpx.post",fake_post_content)
    r2=client.post("/grade",json={"question_id":qid,"answer":"答案"})
    assert r2.status_code==502
    assert r2.json()["detail"]=="模型未按格式返回"

def test_grade_invalid():
    r=client.post("/grade",json={"question_id":1})
    assert r.status_code==422
    r2=client.post("/grade",json={"question_id":1,"answer":""})
    assert r2.status_code==422

def test_records_wrong_filter(monkeypatch):
    title=f"title_{time.time()}"
    r1=client.post("/questions",json={"title":title,"category":"Python","difficulty":"简单","answer":"标准"})
    assert r1.status_code==200
    qid=r1.json()["id"]
    monkeypatch.setenv("DASHSCOPE_API_KEY","假密钥")
    monkeypatch.setattr("main.httpx.post",fake_post_content)
    content_holder["content"]=json.dumps({"correct":True,"score":"8/10","comment":"对"},ensure_ascii=False)
    client.post("/grade",json={"question_id":qid,"answer":"对"})
    content_holder["content"]=json.dumps({"correct":False,"score":"2/10","comment":"错"},ensure_ascii=False)
    client.post("/grade",json={"question_id":qid,"answer":"错"})
    r3=client.get("/api/records",params={"wrong":1})
    wrongs=[x for x in r3.json() if x["question_title"]==title]
    assert len(wrongs)==1
    assert wrongs[0]["correct"]==0

# ---- 题库搜索与筛选（f1）测试 ----
def test_filter_questions_by_category():
    cat=f"测试分类_{time.time()}"
    title=f"title_{time.time()}"
    r1=client.post("/questions",json={"title":title,"category":cat,"difficulty":"中等","answer":"答案内容","tags":"筛选"})
    assert r1.status_code==200
    r2=client.get("/questions",params={"category":cat})
    assert r2.status_code==200
    titles=[q["title"] for q in r2.json()]
    assert title in titles
    for q in r2.json():
        assert q["category"]==cat

def test_filter_questions_by_difficulty():
    dif="困难"
    title=f"title_{time.time()}"
    r1=client.post("/questions",json={"title":title,"category":"Python","difficulty":dif,"answer":"答案内容"})
    assert r1.status_code==200
    r2=client.get("/questions",params={"difficulty":dif})
    for q in r2.json():
        assert q["difficulty"]==dif

def test_search_questions_by_title():
    title=f"搜索命中_{time.time()}"
    r1=client.post("/questions",json={"title":title,"category":"Python","difficulty":"简单","answer":"答案内容"})
    assert r1.status_code==200
    r2=client.get("/questions",params={"q":title})
    titles=[q["title"] for q in r2.json()]
    assert title in titles

def test_search_questions_by_tags():
    tag=f"标签_{time.time()}"
    title=f"title_{time.time()}"
    r1=client.post("/questions",json={"title":title,"category":"Python","difficulty":"简单","answer":"答案内容","tags":tag})
    assert r1.status_code==200
    r2=client.get("/questions",params={"q":tag})
    titles=[q["title"] for q in r2.json()]
    assert title in titles

def test_filter_questions_no_match():
    r=client.get("/questions",params={"q":f"绝不存在的关键词_{time.time()}"})
    assert r.status_code==200
    assert r.json()==[]

def test_question_tags_field():
    title=f"title_{time.time()}"
    r1=client.post("/questions",json={"title":title,"category":"Python","difficulty":"简单","answer":"答案内容","tags":"列表,生成器"})
    assert r1.status_code==200
    qid=r1.json()["id"]
    r2=client.get(f"/questions/{qid}")
    assert r2.json()["tags"]=="列表,生成器"

# ---- /ask-questions 按岗位批量出题（f2）测试 ----
def test_ask_questions_success(monkeypatch):
    t1=f"ai批量_{time.time()}_1"
    t2=f"ai批量_{time.time()}_2"
    content_holder["content"]=json.dumps([
        {"title":t1,"category":"Python","difficulty":"中等","answer":"答案1","tags":"批量"},
        {"title":t2,"category":"Python","difficulty":"困难","answer":"答案2","tags":"批量"}
    ],ensure_ascii=False)
    monkeypatch.setenv("DASHSCOPE_API_KEY","假密钥")
    monkeypatch.setattr("main.httpx.post",fake_post_content)
    r=client.post("/ask-questions",json={"job_title":"Python工程师","jd":"熟悉FastAPI","count":2})
    assert r.status_code==200
    assert r.json()["ok"]==True
    assert len(r.json()["created"])==2
    assert r.json()["skipped"]==[]
    r2=client.get("/questions")
    titles=[q["title"] for q in r2.json()]
    assert t1 in titles
    assert t2 in titles

def test_ask_questions_skip_duplicate(monkeypatch):
    title_old=f"ai批量_{time.time()}"
    r1=client.post("/questions",json={"title":title_old,"category":"Python","difficulty":"简单","answer":"已有答案"})
    assert r1.status_code==200
    title_new=f"ai批量_{time.time()}_新"
    content_holder["content"]=json.dumps([
        {"title":title_old,"category":"Python","difficulty":"简单","answer":"重复"},
        {"title":title_new,"category":"Python","difficulty":"简单","answer":"新题"}
    ],ensure_ascii=False)
    monkeypatch.setenv("DASHSCOPE_API_KEY","假密钥")
    monkeypatch.setattr("main.httpx.post",fake_post_content)
    r=client.post("/ask-questions",json={"job_title":"Python工程师","jd":"熟悉FastAPI"})
    assert r.status_code==200
    assert len(r.json()["created"])==1
    assert title_old in r.json()["skipped"]
    r2=client.get("/questions")
    titles=[q["title"] for q in r2.json()]
    assert title_new in titles

def test_ask_questions_bad_format(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY","假密钥")
    monkeypatch.setattr("main.httpx.post",fake_post_content)
    # 格式一：不是 JSON
    content_holder["content"]="今天天气不错"
    r1=client.post("/ask-questions",json={"job_title":"Python工程师","jd":"熟悉FastAPI"})
    assert r1.status_code==502
    assert r1.json()["detail"]=="模型未按格式返回"
    # 格式二：是 JSON 但不是数组
    content_holder["content"]=json.dumps({"title":"单独一道题"},ensure_ascii=False)
    r2=client.post("/ask-questions",json={"job_title":"Python工程师","jd":"熟悉FastAPI"})
    assert r2.status_code==502
    assert r2.json()["detail"]=="模型未按格式返回"

def test_ask_questions_invalid():
    r1=client.post("/ask-questions",json={"job_title":"","jd":"熟悉FastAPI"})
    assert r1.status_code==422
    r2=client.post("/ask-questions",json={"job_title":"Python工程师","jd":"熟悉FastAPI","count":99})
    assert r2.status_code==422

# ---- 模拟面试（f3）测试 ----
def test_interview_success(monkeypatch):
    content_holder["content"]="请先做个自我介绍吧"
    monkeypatch.setenv("DASHSCOPE_API_KEY","假密钥")
    monkeypatch.setattr("main.httpx.post",fake_post_content)
    r=client.post("/interview",json={"job_title":"Python工程师","messages":[{"role":"user","content":"面试开始"}]})
    assert r.status_code==200
    assert r.json()["answer"]=="请先做个自我介绍吧"
    # 确认服务端确实给模型注入了面试官人设（system 角色在最前面）
    assert last_request["json"]["messages"][0]["role"]=="system"
    assert "面试官" in last_request["json"]["messages"][0]["content"]

def test_interview_summary_success(monkeypatch):
    content_holder["content"]=json.dumps({"score":"中等偏上","strengths":"基础扎实","weaknesses":"深度不足","advice":"多练习项目"},ensure_ascii=False)
    monkeypatch.setenv("DASHSCOPE_API_KEY","假密钥")
    monkeypatch.setattr("main.httpx.post",fake_post_content)
    r=client.post("/interview-summary",json={"job_title":"Python工程师","messages":[{"role":"user","content":"你好"},{"role":"assistant","content":"请做个自我介绍"}]})
    assert r.status_code==200
    assert r.json()["score"]=="中等偏上"
    assert r.json()["strengths"]=="基础扎实"
    assert r.json()["weaknesses"]=="深度不足"
    assert r.json()["advice"]=="多练习项目"

def test_interview_summary_bad_format(monkeypatch):
    content_holder["content"]="这不是 JSON"
    monkeypatch.setenv("DASHSCOPE_API_KEY","假密钥")
    monkeypatch.setattr("main.httpx.post",fake_post_content)
    r=client.post("/interview-summary",json={"job_title":"Python工程师","messages":[{"role":"user","content":"你好"}]})
    assert r.status_code==502
    assert r.json()["detail"]=="模型未按格式返回"

def test_interview_invalid():
    r1=client.post("/interview",json={"job_title":"","messages":[]})
    assert r1.status_code==422
    r2=client.post("/interview-summary",json={"job_title":"Python工程师","messages":[]})
    assert r2.status_code==422

# ---- 组卷模拟测试与统计（f4）测试 ----
def test_get_questions_random_and_count():
    titles=[f"组卷_{time.time()}_{i}" for i in range(3)]
    for t in titles:
        r=client.post("/questions",json={"title":t,"category":"Python","difficulty":"简单","answer":"答案"})
        assert r.status_code==200
    r2=client.get("/questions",params={"random":1,"count":2})
    assert r2.status_code==200
    assert len(r2.json())==2

def test_quiz_grade_success(monkeypatch):
    qs=[]
    for i in range(2):
        t=f"quiz_{time.time()}_{i}"
        r1=client.post("/questions",json={"title":t,"category":"Python","difficulty":"简单","answer":"标准答案"+str(i)})
        assert r1.status_code==200
        qs.append((r1.json()["id"],t))
    content_holder["content"]=json.dumps([
        {"correct":True,"score":"9/10","comment":"回答很好"},
        {"correct":False,"score":"3/10","comment":"答得不对"}
    ],ensure_ascii=False)
    monkeypatch.setenv("DASHSCOPE_API_KEY","假密钥")
    monkeypatch.setattr("main.httpx.post",fake_post_content)
    r=client.post("/quiz-grade",json={"answers":[{"question_id":qs[0][0],"answer":"我的答案1"},{"question_id":qs[1][0],"answer":"我的答案2"}]})
    assert r.status_code==200
    assert r.json()["ok"]==True
    assert r.json()["correct_count"]==1
    assert r.json()["total"]==2
    assert len(r.json()["results"])==2
    # 复查答题记录确实连写了 2 条
    r3=client.get("/api/records")
    titles=[x["question_title"] for x in r3.json()]
    assert qs[0][1] in titles
    assert qs[1][1] in titles

def test_quiz_grade_skip_missing_question():
    title=f"quiz_{time.time()}"
    r1=client.post("/questions",json={"title":title,"category":"Python","difficulty":"简单","answer":"答案"})
    assert r1.status_code==200
    qid=r1.json()["id"]
    r2=client.delete(f"/questions/{qid}")
    assert r2.status_code==200
    # 题目已删除，接口应跳过而不是报错，且无需真实调用大模型
    r3=client.post("/quiz-grade",json={"answers":[{"question_id":qid,"answer":"答案"}]})
    assert r3.status_code==200
    assert r3.json()["results"]==[]
    assert qid in r3.json()["skipped"]

def test_quiz_grade_bad_format(monkeypatch):
    title=f"quiz_{time.time()}"
    r1=client.post("/questions",json={"title":title,"category":"Python","difficulty":"简单","answer":"答案"})
    assert r1.status_code==200
    qid=r1.json()["id"]
    content_holder["content"]="这不是 JSON"
    monkeypatch.setenv("DASHSCOPE_API_KEY","假密钥")
    monkeypatch.setattr("main.httpx.post",fake_post_content)
    r2=client.post("/quiz-grade",json={"answers":[{"question_id":qid,"answer":"我的答案"}]})
    assert r2.status_code==502
    assert r2.json()["detail"]=="模型未按格式返回"

def test_quiz_grade_invalid():
    r=client.post("/quiz-grade",json={"answers":[]})
    assert r.status_code==422

def test_stats_endpoint(monkeypatch):
    title=f"stats_{time.time()}"
    r1=client.post("/questions",json={"title":title,"category":"Python","difficulty":"简单","answer":"标准"})
    assert r1.status_code==200
    qid=r1.json()["id"]
    content_holder["content"]=json.dumps({"correct":True,"score":"8/10","comment":"对"},ensure_ascii=False)
    monkeypatch.setenv("DASHSCOPE_API_KEY","假密钥")
    monkeypatch.setattr("main.httpx.post",fake_post_content)
    r2=client.post("/grade",json={"question_id":qid,"answer":"对"})
    assert r2.status_code==200
    r3=client.get("/api/stats")
    assert r3.status_code==200
    data=r3.json()
    assert data["total"]>=1
    assert "correct_rate" in data
    by_cat={x["name"]:x for x in data["by_category"]}
    assert "Python" in by_cat
    assert by_cat["Python"]["answered"]>=1

# ---- /questions 分页（limit/offset + X-Total-Count）测试 ----
def test_questions_pagination():
    ids=[]
    for i in range(3):
        r=client.post("/questions",json={"title":f"分页测试_{time.time()}_{i}","category":"Python","difficulty":"简单","answer":"答案"})
        assert r.status_code==200
        ids.append(r.json()["id"])
    try:
        r1=client.get("/questions",params={"limit":2,"offset":0})
        assert r1.status_code==200
        assert len(r1.json())==2
        total=int(r1.headers.get("x-total-count","0"))
        assert total>=3
        r2=client.get("/questions",params={"limit":2,"offset":2})
        page1_ids=[x["id"] for x in r1.json()]
        page2_ids=[x["id"] for x in r2.json()]
        assert not set(page1_ids)&set(page2_ids)
        r3=client.get("/questions",params={"limit":2,"offset":10000})
        assert len(r3.json())==0
        r4=client.get("/questions")
        assert len(r4.json())>=3
    finally:
        for qid in ids:
            client.delete(f"/questions/{qid}")

# ---- 个人中心（改密码）与记录归属测试 ----
def test_change_password_success():
    username=f"cp_{time.time()}"
    r1=client.post("/register",json={"username":username,"password":"old123"})
    assert r1.status_code==200
    uid=r1.json()["id"]
    r2=client.post("/change-password",json={"username":username,"old_password":"old123","new_password":"new456"})
    assert r2.status_code==200
    # 旧密码应登录失败，新密码应登录成功且 id 不变
    r3=client.post("/login",json={"username":username,"password":"old123"})
    assert r3.status_code==401
    r4=client.post("/login",json={"username":username,"password":"new456"})
    assert r4.status_code==200
    assert r4.json()["id"]==uid

def test_change_password_wrong_old():
    username=f"cpw_{time.time()}"
    r1=client.post("/register",json={"username":username,"password":"old123"})
    assert r1.status_code==200
    r2=client.post("/change-password",json={"username":username,"old_password":"wrong123","new_password":"new456"})
    assert r2.status_code==401

def test_change_password_user_not_found():
    r=client.post("/change-password",json={"username":f"nobody_{time.time()}","old_password":"a","new_password":"b"})
    assert r.status_code==401

def test_change_password_invalid():
    r=client.post("/change-password",json={"username":"x"})
    assert r.status_code==422

def test_grade_records_belong_to_user(monkeypatch):
    title=f"belong_{time.time()}"
    r1=client.post("/questions",json={"title":title,"category":"Python","difficulty":"简单","answer":"标准"})
    assert r1.status_code==200
    qid=r1.json()["id"]
    username=f"belong_{time.time()}"
    r2=client.post("/register",json={"username":username,"password":"p123"})
    assert r2.status_code==200
    uid=r2.json()["id"]
    content_holder["content"]=json.dumps({"correct":True,"score":"8/10","comment":"对"},ensure_ascii=False)
    monkeypatch.setenv("DASHSCOPE_API_KEY","假密钥")
    monkeypatch.setattr("main.httpx.post",fake_post_content)
    try:
        # 批改请求带上 user_id，记录应归属该用户
        r3=client.post("/grade",json={"question_id":qid,"answer":"对","user_id":uid})
        assert r3.status_code==200
        records=client.get("/api/records",params={"user_id":uid}).json()
        qids=[x["question_id"] for x in records]
        assert qid in qids
        stats=client.get("/api/stats",params={"user_id":uid}).json()
        assert stats["total"]>=1
        # 另一个从未答题的用户记录应为空
        r_no=client.post("/register",json={"username":f"empty_{time.time()}","password":"p123"})
        uid_no=r_no.json()["id"]
        stats_no=client.get("/api/stats",params={"user_id":uid_no}).json()
        assert stats_no["total"]==0
    finally:
        client.delete(f"/questions/{qid}")

# ---- RAG 检索增强测试 ----
class FakeEmbeddingResponse:
    def __init__(self):
        self.status_code=200
    def json(self):
        return {"data":[{"embedding":[0.5]*1024}]}

# 一个假请求函数同时扮演两个上游：/embeddings 返回假向量，其他请求返回 content_holder 里的假内容
last_chat_request={}
def fake_post_rag(url,headers=None,json=None,timeout=None):
    if "/embeddings" in url:
        return FakeEmbeddingResponse()
    last_chat_request["json"]=json
    return FakeContentResponse()

def test_rag_search_returns_matches(monkeypatch):
    # 清空向量表，保证本次测试的检索结果只来自自己造的题
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM vec_questions"))
    t1=f"rag_{time.time()}_装饰器"
    t2=f"rag_{time.time()}_列表推导"
    monkeypatch.setenv("DASHSCOPE_API_KEY","假密钥")
    monkeypatch.setattr("main.httpx.post",fake_post_rag)
    r1=client.post("/questions",json={"title":t1,"category":"Python","difficulty":"简单","answer":"装饰器用于增强函数"})
    assert r1.status_code==200
    qid1=r1.json()["id"]
    r2=client.post("/questions",json={"title":t2,"category":"Python","difficulty":"简单","answer":"列表推导式用于生成列表"})
    assert r2.status_code==200
    qid2=r2.json()["id"]
    try:
        r3=client.get("/rag-search",params={"q":"Python 装饰器怎么用"})
        assert r3.status_code==200
        assert r3.json()["ok"]==True
        titles=[x["title"] for x in r3.json()["results"]]
        assert t1 in titles
        assert t2 in titles
    finally:
        client.delete(f"/questions/{qid1}")
        client.delete(f"/questions/{qid2}")

def test_rag_referenced_in_batch(monkeypatch):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM vec_questions"))
    t_ref=f"rag_ref_{time.time()}"
    monkeypatch.setenv("DASHSCOPE_API_KEY","假密钥")
    monkeypatch.setattr("main.httpx.post",fake_post_rag)
    r0=client.post("/questions",json={"title":t_ref,"category":"Python","difficulty":"简单","answer":"参考题目答案"})
    assert r0.status_code==200
    qid=r0.json()["id"]
    t_new=f"ai批量RAG_{time.time()}"
    content_holder["content"]=json.dumps([
        {"title":t_new,"category":"Python","difficulty":"中等","answer":"新题参考答案","tags":"rag"}
    ],ensure_ascii=False)
    try:
        r=client.post("/ask-questions",json={"job_title":"Python工程师","jd":"熟悉FastAPI框架","count":1})
        assert r.status_code==200
        assert r.json()["ok"]==True
        ref_titles=[x["title"] for x in r.json()["referenced"]]
        assert t_ref in ref_titles
        # 发给大模型的提示词里必须带上了检索增强的参考上下文
        assert "检索" in last_chat_request["json"]["messages"][0]["content"]
        # 生成的新题应正常写入题库
        r2=client.get("/questions",params={"q":t_new})
        assert len(r2.json())==1
    finally:
        client.delete(f"/questions/{qid}")
        r_del=client.get("/questions",params={"q":t_new})
        for q in r_del.json():
            if q["title"]==t_new:
                client.delete(f"/questions/{q['id']}")

def test_rag_search_no_results():
    r=client.get("/rag-search",params={"q":"任何查询内容"})
    assert r.status_code==200
    assert r.json()["ok"]==True
    assert r.json()["results"]==[]

def test_rag_search_empty_query():
    r=client.get("/rag-search",params={"q":""})
    assert r.status_code==200
    assert r.json()["ok"]==True
    assert r.json()["results"]==[]

# ---- SSE 流式接口（/ask/stream、/interview/stream）测试 ----
stream_holder={}
last_stream_request={}

# 假流式响应：iter_lines 逐行吐出 SSE 数据行，末尾跟 [DONE]，模拟大模型流式返回
class FakeStreamResponse:
    def __init__(self,chunks):
        self.status_code=200
        self._chunks=chunks
    def iter_lines(self):
        for c in self._chunks:
            yield "data: "+json.dumps({"choices":[{"delta":{"content":c}}]},ensure_ascii=False)
        yield "data: [DONE]"
    def close(self):
        pass

class FakeStreamBadResponse:
    def __init__(self):
        self.status_code=401
    def close(self):
        pass

# 假流式 Client：build_request 时记录请求体，send 时返回假流式响应
class FakeStreamClient:
    def __init__(self,timeout=None):
        pass
    def build_request(self,method,url,headers=None,json=None):
        last_stream_request["json"]=json
        return {"method":method,"url":url}
    def send(self,request,stream=None):
        last_stream_request["stream"]=stream
        return FakeStreamResponse(stream_holder["chunks"])
    def close(self):
        pass

class FakeStreamBadClient:
    def __init__(self,timeout=None):
        pass
    def build_request(self,method,url,headers=None,json=None):
        return {"method":method,"url":url}
    def send(self,request,stream=None):
        return FakeStreamBadResponse()
    def close(self):
        pass

# 把 SSE 响应文本解析成 data 字段列表，便于断言
def parse_sse(text):
    events=[]
    for line in text.strip().split("\n"):
        line=line.strip()
        if line.startswith("data:"):
            events.append(line[5:].strip())
    return events

def test_ask_stream_success(monkeypatch):
    stream_holder["chunks"]=["你好","，","我是AI助手"]
    monkeypatch.setenv("DASHSCOPE_API_KEY","假密钥")
    monkeypatch.setattr("main.httpx.Client",FakeStreamClient)
    r=client.post("/ask/stream",json={"messages":[{"role":"user","content":"测试问题"}]})
    assert r.status_code==200
    assert r.headers["content-type"].startswith("text/event-stream")
    events=parse_sse(r.text)
    contents=[json.loads(e)["content"] for e in events if e!="[DONE]"]
    # 多个 data 块拼接后应还原成完整回复
    assert "".join(contents)=="你好，我是AI助手"
    assert events[-1]=="[DONE]"
    # 确认确实是按流式模式请求的上游（stream=True）
    assert last_stream_request["stream"]==True

def test_ask_stream_upstream_error(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY","假密钥")
    monkeypatch.setattr("main.httpx.Client",FakeStreamBadClient)
    r=client.post("/ask/stream",json={"messages":[{"role":"user","content":"测试问题"}]})
    assert r.status_code==502
    assert r.json()["detail"]=="模型服务返回错误"

def test_ask_stream_missing_key(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY",raising=False)
    r=client.post("/ask/stream",json={"messages":[{"role":"user","content":"测试问题"}]})
    assert r.status_code==500
    assert r.json()["detail"]=="未配置API密钥"

def test_ask_stream_invalid():
    r=client.post("/ask/stream",json={"messages":[]})
    assert r.status_code==422

def test_interview_stream_success(monkeypatch):
    stream_holder["chunks"]=["请先","做个自我介绍吧"]
    monkeypatch.setenv("DASHSCOPE_API_KEY","假密钥")
    monkeypatch.setattr("main.httpx.Client",FakeStreamClient)
    r=client.post("/interview/stream",json={"job_title":"Python工程师","messages":[{"role":"user","content":"面试开始"}]})
    assert r.status_code==200
    events=parse_sse(r.text)
    contents=[json.loads(e)["content"] for e in events if e!="[DONE]"]
    assert "".join(contents)=="请先做个自我介绍吧"
    # 确认流式版同样注入了面试官人设（system 角色在最前面）
    assert last_stream_request["json"]["messages"][0]["role"]=="system"
    assert "面试官" in last_stream_request["json"]["messages"][0]["content"]

