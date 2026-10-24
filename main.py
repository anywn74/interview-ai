from fastapi import FastAPI,HTTPException,Response
from pydantic import BaseModel,Field
from sqlalchemy import create_engine,Column,Integer,String,func
from sqlalchemy import event,text
from sqlalchemy.orm import declarative_base,sessionmaker
from sqlalchemy.exc import IntegrityError
from passlib.context import CryptContext
import os
import httpx
import json
import time
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse,StreamingResponse
from prometheus_client import Counter,Histogram,make_asgi_app
import sqlite_vec


# 数据库路径支持环境变量覆盖：pytest 由 conftest.py 设置 TEST_DATABASE 指向独立的测试库，
# 测试产生的数据全部落在 test_app.db，不再污染真实的 app.db；正常启动服务时不设置该变量
DATABASE_URL = os.environ.get("TEST_DATABASE", "sqlite:///./app.db")
engine = create_engine(DATABASE_URL)
Base = declarative_base()

# 每个新建的 SQLite 连接都要加载 sqlite-vec 扩展，向量表才能正常建表和查询
@event.listens_for(engine,"connect")
def load_sqlite_vec(dbapi_conn,connection_record):
    dbapi_conn.enable_load_extension(True)
    sqlite_vec.load(dbapi_conn)
    dbapi_conn.enable_load_extension(False)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer,primary_key=True)
    username = Column(String,unique=True)
    password = Column(String)

class Question(Base):
    __tablename__="questions"
    id = Column(Integer,primary_key=True)
    title = Column(String,unique=True)
    category = Column(String)
    difficulty = Column(String)
    answer = Column(String)
    tags = Column(String,default="")

class AnswerRecord(Base):
    __tablename__="records"
    id = Column(Integer,primary_key=True)
    question_id = Column(Integer)
    question_title = Column(String)
    user_answer = Column(String)
    correct = Column(Integer)
    score = Column(String)
    comment = Column(String)
    user_id = Column(Integer)


Base.metadata.create_all(bind=engine)
# 向量表：一题一行，存放题目的文本向量（1024 维），按余弦距离计算相似度，供 RAG 检索使用
EMBEDDING_DIM=1024
with engine.begin() as conn:
    conn.execute(text("CREATE VIRTUAL TABLE IF NOT EXISTS vec_questions USING vec0(id INTEGER PRIMARY KEY, embedding float[1024] distance_metric=cosine)"))
SessionLocal=sessionmaker(bind=engine)
pwd_context=CryptContext(schemes=["bcrypt"],deprecated="auto")

class UserIn(BaseModel):
    username:str=Field(...,min_length=1)
    password:str=Field(...,min_length=1)


class QuestionIn(BaseModel):
    title:str=Field(...,min_length=1)
    category:str=Field(...,min_length=1)
    difficulty:str=Field(...,min_length=1)
    answer:str=Field(...,min_length=1)
    tags:str=""

class AskIn(BaseModel):
    messages:list[dict]=Field(...,min_length=1)

class AskQuestionIn(BaseModel):
    topic:str=Field(...,min_length=1)

class AskQuestionsIn(BaseModel):
    job_title:str=Field(...,min_length=1)
    jd:str=Field(...,min_length=1)
    count:int=Field(5,ge=1,le=10)

class GradeIn(BaseModel):
    question_id:int
    answer:str=Field(...,min_length=1)
    user_id:int=None

class InterviewIn(BaseModel):
    job_title:str=Field(...,min_length=1)
    messages:list[dict]=Field(...,min_length=1)

class InterviewSummaryIn(BaseModel):
    job_title:str=Field(...,min_length=1)
    messages:list[dict]=Field(...,min_length=1)

class QuizGradeIn(BaseModel):
    answers:list[dict]=Field(...,min_length=1)
    user_id:int=None

class ChangePasswordIn(BaseModel):
    username:str=Field(...,min_length=1)
    old_password:str=Field(...,min_length=1)
    new_password:str=Field(...,min_length=1)


app = FastAPI()

# Prometheus 监控指标：按接口统计请求总数与请求耗时（秒）
REQUEST_COUNT = Counter("http_requests_total","HTTP 请求总数",["method","path"])
REQUEST_LATENCY = Histogram("http_request_duration_seconds","HTTP 请求耗时（秒）",["method","path"])

# 监控中间件：每个请求结束时记录一次；路径取路由模板（如 /questions/{question_id}），避免每个 id 各占一个指标
@app.middleware("http")
async def prometheus_middleware(request,call_next):
    start=time.perf_counter()
    response=await call_next(request)
    route=request.scope.get("route")
    path=route.path if route is not None else request.url.path
    REQUEST_COUNT.labels(request.method,path).inc()
    REQUEST_LATENCY.labels(request.method,path).observe(time.perf_counter()-start)
    return response

# 监控数据端点，供 Prometheus 定期拉取
app.mount("/metrics", make_asgi_app())

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/page")
def page():
    return FileResponse("static/index.html")

@app.get("/login")
def login_page():
    return FileResponse("static/login.html")

@app.get("/register")
def register_page():
    return FileResponse("static/register.html")

@app.get("/bank")
def bank_page():
    return FileResponse("static/questions.html")

@app.get("/bank/new")
def new_question_page():
    return FileResponse("static/questions_new.html")

@app.get("/records")
def records_page():
    return FileResponse("static/records.html")

@app.get("/interview")
def interview_page():
    return FileResponse("static/interview.html")

@app.get("/quiz")
def quiz_page():
    return FileResponse("static/quiz.html")

@app.get("/stats")
def stats_page():
    return FileResponse("static/stats.html")

@app.get("/profile")
def profile_page():
    return FileResponse("static/profile.html")


@app.post("/register")
def register(u:UserIn):
    db=SessionLocal()
    user=User(username=u.username,password=pwd_context.hash(u.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        db.close()
        raise HTTPException(status_code=409,detail="用户名已存在")
    user_id = user.id
    db.close()
    return{"ok":True,"id":user_id}

@app.post("/login")
def login(u:UserIn):
    db=SessionLocal()
    user=db.query(User).filter(User.username==u.username).first()
    if user is None:
        db.close()
        raise HTTPException(status_code=401,detail="用户名或密码错误")
    if not pwd_context.verify(u.password,user.password):
        db.close()
        raise HTTPException(status_code=401,detail="用户名或密码错误")
    db.close()
    return{"ok":True,"id":user.id}

# 修改密码：先校验旧密码是否正确，再保存新密码的哈希
@app.post("/change-password")
def change_password(c:ChangePasswordIn):
    db=SessionLocal()
    user=db.query(User).filter(User.username==c.username).first()
    if user is None:
        db.close()
        raise HTTPException(status_code=401,detail="用户名或密码错误")
    if not pwd_context.verify(c.old_password,user.password):
        db.close()
        raise HTTPException(status_code=401,detail="用户名或密码错误")
    user.password=pwd_context.hash(c.new_password)
    db.commit()
    db.close()
    return {"ok":True}

@app.post("/questions")
def create_question(q:QuestionIn):
    db=SessionLocal()
    question=Question(title=q.title,category=q.category,difficulty=q.difficulty,answer=q.answer,tags=q.tags)
    db.add(question)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        db.close()
        raise HTTPException(status_code=409,detail="题目已存在")
    question_id=question.id
    db.close()
    sync_question_vector(question_id,question_text(q.title,q.category,q.answer,q.tags))
    return{"ok":True,"id":question_id}

# 调用大模型的公共函数：检查密钥、发起请求、三道防线兜底，返回模型文本内容
def call_llm(messages:list):
    api_key=os.environ.get("DASHSCOPE_API_KEY")
    if api_key is None:
        raise HTTPException(status_code=500,detail="未配置API密钥")
    url="https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    headers={"Authorization":f"Bearer {api_key}"}
    body={"model":"qwen-plus","messages":messages}
    try:
        r=httpx.post(url,headers=headers,json=body,timeout=120)
    except Exception as e:
        print("call_llm 请求失败:",type(e).__name__,str(e))
        raise HTTPException(status_code=502,detail="调用大模型服务失败")
    if r.status_code != 200:
        raise HTTPException(status_code=502,detail="模型服务返回错误")
    return r.json()["choices"][0]["message"]["content"]

# 调用大模型的流式版本：流式模式在 httpx 中要用 Client.send 开 stream=True，顶层 httpx.post 不支持该参数
# 返回 (client, 响应对象)：响应读完前 client 必须保持存活，由 sse_generate 在结束时统一关闭
def call_llm_stream(messages:list):
    api_key=os.environ.get("DASHSCOPE_API_KEY")
    if api_key is None:
        raise HTTPException(status_code=500,detail="未配置API密钥")
    url="https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    headers={"Authorization":f"Bearer {api_key}"}
    body={"model":"qwen-plus","messages":messages,"stream":True}
    client=httpx.Client(timeout=120)
    try:
        r=client.send(client.build_request("POST",url,headers=headers,json=body),stream=True)
    except Exception as e:
        client.close()
        print("call_llm_stream 请求失败:",type(e).__name__,str(e))
        raise HTTPException(status_code=502,detail="调用大模型服务失败")
    if r.status_code != 200:
        r.close()
        client.close()
        raise HTTPException(status_code=502,detail="模型服务返回错误")
    return client,r

# 把流式响应逐行解析并转发成 SSE 事件：上游每个 data 块被原样转给前端，断流时报错
def sse_generate(client,r):
    try:
        for line in r.iter_lines():
            if not line:
                continue
            line=line.strip()
            if not line.startswith("data:"):
                continue
            data=line[5:].strip()
            if data=="[DONE]":
                yield "data: [DONE]\n\n"
                break
            try:
                chunk=json.loads(data)
                delta=chunk["choices"][0]["delta"].get("content","") or ""
            except Exception:
                continue
            if delta:
                yield "data: "+json.dumps({"content":delta},ensure_ascii=False)+"\n\n"
    except Exception as e:
        print("流式读取失败:",type(e).__name__,str(e))
        yield "event: error\ndata: "+json.dumps({"detail":"流式读取失败"},ensure_ascii=False)+"\n\n"
    finally:
        try:
            r.close()
        except Exception:
            pass
        try:
            client.close()
        except Exception:
            pass

# 把模型返回的文本解析成 JSON；自动剥掉 ``` 代码围栏，解析失败归为上游格式错误
def parse_llm_json(content:str):
    text=content.strip()
    if text.startswith("```"):
        text=text.strip("`")
        if text.startswith("json"):
            text=text[4:]
        text=text.strip()
    try:
        return json.loads(text)
    except Exception:
        raise HTTPException(status_code=502,detail="模型未按格式返回")

# 调用向量模型：把文本转成 1024 维向量；密钥检查与异常处理方式和 call_llm 保持一致
def call_embedding(text:str):
    api_key=os.environ.get("DASHSCOPE_API_KEY")
    if api_key is None:
        raise HTTPException(status_code=500,detail="未配置API密钥")
    url="https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings"
    headers={"Authorization":f"Bearer {api_key}"}
    body={"model":"text-embedding-v3","input":text}
    try:
        r=httpx.post(url,headers=headers,json=body,timeout=120)
    except Exception as e:
        print("call_embedding 请求失败:",type(e).__name__,str(e))
        raise HTTPException(status_code=502,detail="调用向量模型服务失败")
    if r.status_code != 200:
        raise HTTPException(status_code=502,detail="向量模型服务返回错误")
    return r.json()["data"][0]["embedding"]

# 拼接题目的检索文本：分类、题干、参考答案、标签都参与向量化
def question_text(title:str,category:str,answer:str,tags:str):
    return "分类："+category+" 题目："+title+" 参考答案："+answer+" 标签："+tags

# 同步单道题的向量：先删旧向量再插入新向量；向量服务不可用时静默跳过，不影响主流程
def sync_question_vector(question_id:int,content:str):
    try:
        vec=call_embedding(content)
        vec=[float(x) for x in vec]
        if len(vec)!=EMBEDDING_DIM:
            print("题目",question_id,"向量维度异常，跳过同步")
            return
    except Exception as e:
        print("题目",question_id,"向量化失败，跳过同步:",type(e).__name__,e)
        return
    try:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM vec_questions WHERE id=:id"),{"id":question_id})
            conn.execute(text("INSERT INTO vec_questions(id,embedding) VALUES (:id,:emb)"),{"id":question_id,"emb":json.dumps(vec)})
    except Exception as e:
        print("题目",question_id,"向量写入失败:",type(e).__name__,str(e))

# 题目被删除时同步清理它的向量
def delete_question_vector(question_id:int):
    try:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM vec_questions WHERE id=:id"),{"id":question_id})
    except Exception as e:
        print("题目",question_id,"向量删除失败:",type(e).__name__,str(e))

# 向量检索：查询文本向量化后，在题库向量表中找余弦距离最近的题目；任何一步失败都返回空列表，不阻塞主流程
def rag_search_questions(query_text:str,top_k:int=5):
    try:
        vec=call_embedding(query_text)
        vec=[float(x) for x in vec]
        if len(vec)!=EMBEDDING_DIM:
            print("检索向量维度异常，跳过检索增强")
            return []
    except Exception as e:
        print("检索文本向量化失败，跳过检索增强:",type(e).__name__,e)
        return []
    top_k=max(1,min(top_k,10))
    try:
        with engine.connect() as conn:
            rows=conn.execute(
                text("SELECT id,distance FROM vec_questions WHERE embedding MATCH :emb ORDER BY distance LIMIT "+str(top_k)),
                {"emb":json.dumps(vec)}
            ).fetchall()
    except Exception as e:
        print("向量表查询失败:",type(e).__name__,str(e))
        return []
    if not rows:
        return []
    ids=[row[0] for row in rows]
    db=SessionLocal()
    questions=db.query(Question).filter(Question.id.in_(ids)).all()
    qmap={q.id:q for q in questions}
    db.close()
    result=[]
    for qid,dist in rows:
        q=qmap.get(qid)
        if q is None:
            continue
        result.append({"id":q.id,"title":q.title,"category":q.category,"answer":q.answer,"tags":q.tags,"distance":round(float(dist),4)})
    return result

@app.post("/ask")
def ask_question(a:AskIn):
    answer=call_llm(a.messages)
    return {"answer":answer}

# AI 问答的流式版：逻辑与 /ask 完全一致，只是大模型回复以 SSE 事件流逐块送到前端
@app.post("/ask/stream")
def ask_question_stream(a:AskIn):
    client,r=call_llm_stream(a.messages)
    return StreamingResponse(sse_generate(client,r),media_type="text/event-stream")

@app.post("/ask-question")
def ask_question_ai(q:AskQuestionIn):
    db=SessionLocal()
    try:
        # 最多尝试 3 次：每次把题库已有题目标题注入提示词要求换角度，
        # 若生成的标题撞上「题目全局唯一」约束则回滚重试，3 次都撞才报错
        for attempt in range(3):
            existing=[row[0] for row in db.query(Question.title).all()]
            avoid=(
                "请注意：这道题不能与题库中已有的题目重复，题库已有题目的标题如下："
                +("、".join(existing) if existing else "（暂无）")
                +"。请选择一个不同的考察角度出题。"
            )
            prompt=(
                "你是一名面试出题官，请根据下面的要求出一道面试题。"
                "只输出 JSON，不要输出任何其他文字，格式为："
                '{"title":"题目标题","category":"分类","difficulty":"简单或中等或困难","answer":"参考答案","tags":"标签1,标签2"}。'
                "出题要求："+q.topic+"\n"+avoid
            )
            content=call_llm([{"role":"user","content":prompt}])
            data=parse_llm_json(content)
            title=str(data.get("title","")).strip()
            category=str(data.get("category","")).strip()
            difficulty=str(data.get("difficulty","")).strip()
            answer=str(data.get("answer","")).strip()
            tags=str(data.get("tags","")).strip()
            if not title or not category or not answer:
                raise HTTPException(status_code=502,detail="模型未按格式返回")
            if difficulty not in ("简单","中等","困难"):
                difficulty="简单"
            question=Question(title=title,category=category,difficulty=difficulty,answer=answer,tags=tags)
            db.add(question)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                if attempt<2:
                    continue
                raise HTTPException(status_code=409,detail="连续三次生成的题目都与题库重复，请换个出题方向再试")
            question_id=question.id
            sync_question_vector(question_id,question_text(title,category,answer,tags))
            return {"ok":True,"id":question_id,"title":title,"category":category,"difficulty":difficulty,"answer":answer,"tags":tags}
    finally:
        db.close()

# 按岗位名称+岗位描述批量生成面试题：先用向量检索从题库找相关题目做参考（RAG），再要求模型输出 JSON 数组，逐条落库，重复题目跳过不影响其余题目
@app.post("/ask-questions")
def ask_questions_batch(a:AskQuestionsIn):
    rag=rag_search_questions("岗位名称："+a.job_title+"\n岗位描述："+a.jd)
    prompt=(
        "你是一名面试出题官，请根据岗位名称和岗位描述出 "+str(a.count)+" 道面试题。"
        "只输出 JSON 数组，不要输出任何其他文字，数组中每个元素格式为："
        '{"title":"题目标题","category":"分类","difficulty":"简单或中等或困难","answer":"参考答案","tags":"标签1,标签2"}。'
        "岗位名称："+a.job_title+"\n岗位描述："+a.jd
    )
    if rag:
        ref_lines=["以下是从题库中检索到的相关参考题目，可作风格与难度参考，但不要原样照抄："]
        for item in rag:
            ref_lines.append("- 题目："+item["title"]+"（分类："+item["category"]+"）参考答案："+item["answer"])
        prompt=prompt+"\n"+"\n".join(ref_lines)
    content=call_llm([{"role":"user","content":prompt}])
    data=parse_llm_json(content)
    if not isinstance(data,list) or len(data)==0:
        raise HTTPException(status_code=502,detail="模型未按格式返回")
    created=[]
    skipped=[]
    for item in data[:a.count]:
        if not isinstance(item,dict):
            continue
        title=str(item.get("title","")).strip()
        category=str(item.get("category","")).strip()
        difficulty=str(item.get("difficulty","")).strip()
        answer=str(item.get("answer","")).strip()
        tags=str(item.get("tags","")).strip()
        if not title or not category or not answer:
            continue
        if difficulty not in ("简单","中等","困难"):
            difficulty="简单"
        db=SessionLocal()
        question=Question(title=title,category=category,difficulty=difficulty,answer=answer,tags=tags)
        db.add(question)
        try:
            db.commit()
            created.append({"id":question.id,"title":title})
            sync_question_vector(question.id,question_text(title,category,answer,tags))
        except IntegrityError:
            db.rollback()
            skipped.append(title)
        db.close()
    return {"ok":True,"created":created,"skipped":skipped,"referenced":[{"id":x["id"],"title":x["title"]} for x in rag]}

# 构造面试对话的完整消息列表：服务端注入面试官人设，结合岗位与完整对话历史点评并追问
def interview_messages(job_title:str,messages:list):
    system_prompt=(
        "你是一名专业的面试官，正在面试"+job_title+"岗位的候选人。"
        "规则：一次只问一个问题；先对候选人的上一个回答做简短点评，再继续追问下一个问题；"
        "提问由浅入深，围绕岗位要求展开。"
    )
    return [{"role":"system","content":system_prompt}]+messages

# 模拟面试官：一次调用返回面试官的完整回复
@app.post("/interview")
def interview_turn(i:InterviewIn):
    answer=call_llm(interview_messages(i.job_title,i.messages))
    return {"answer":answer}

# 模拟面试官的流式版：人设与追问逻辑和 /interview 完全一致，仅返回方式改为 SSE 流式
@app.post("/interview/stream")
def interview_turn_stream(i:InterviewIn):
    client,r=call_llm_stream(interview_messages(i.job_title,i.messages))
    return StreamingResponse(sse_generate(client,r),media_type="text/event-stream")

# 根据整场面试对话生成面试总结报告（JSON 格式）
@app.post("/interview-summary")
def interview_summary(i:InterviewSummaryIn):
    # 候选人必须实际回答过至少一题才生成报告，否则模型会把空对话编造出评分与"关键点"
    # 消息流约定：模拟面试页在开始时发送的第一条 user 消息是"面试开始"开场指令，不是回答，
    # 因此只有出现第二条及以上的非空 user 消息，才说明候选人真正作答过
    user_msgs=[m for m in i.messages if m.get("role")=="user" and str(m.get("content","")).strip()]
    if len(user_msgs)<2:
        raise HTTPException(status_code=400,detail="请至少回答一道题目后再结束面试")
    lines=[]
    for m in i.messages:
        role="候选人" if m.get("role")=="user" else "面试官"
        lines.append(role+"："+str(m.get("content","")))
    convo="\n".join(lines)
    prompt=(
        "你是一名面试官，请根据下面的面试对话，对候选人的表现给出总结。"
        "只输出 JSON，不要输出任何其他文字，格式为："
        '{"score":"总分评价","strengths":"优点","weaknesses":"不足","advice":"建议"}。'
        "面试岗位："+i.job_title+"\n面试对话：\n"+convo
    )
    content=call_llm([{"role":"user","content":prompt}])
    data=parse_llm_json(content)
    score=str(data.get("score","")).strip() or "未评分"
    strengths=str(data.get("strengths","")).strip() or "无"
    weaknesses=str(data.get("weaknesses","")).strip() or "无"
    advice=str(data.get("advice","")).strip() or "无"
    return {"score":score,"strengths":strengths,"weaknesses":weaknesses,"advice":advice}

# 组卷模拟测试：一次把整卷答案交给模型统一批改，按顺序逐条写入答题记录
@app.post("/quiz-grade")
def quiz_grade(q:QuizGradeIn):
    db=SessionLocal()
    items=[]
    skipped=[]
    for a in q.answers:
        qid=a.get("question_id")
        answer=str(a.get("answer","")).strip()
        if qid is None or answer=="":
            continue
        question=db.query(Question).filter(Question.id==qid).first()
        if question is None:
            skipped.append(qid)
            continue
        items.append({"qid":qid,"title":question.title,"answer":answer,"std_answer":question.answer})
    db.close()
    if len(items)==0:
        return {"ok":True,"results":[],"correct_count":0,"total":0,"skipped":skipped}
    parts=[]
    for idx,it in enumerate(items):
        parts.append(str(idx+1)+". 题目："+it["title"]+"\n标准答案："+it["std_answer"]+"\n考生答案："+it["answer"])
    prompt=(
        "你是一名面试官，请批改下面这组题目。"
        "只输出 JSON 数组，不要输出任何其他文字，数组长度必须与题目数量相同、顺序一致，"
        '每个元素格式为：{"correct":true或false,"score":"评分","comment":"点评"}。\n'
        +"\n".join(parts)
    )
    content=call_llm([{"role":"user","content":prompt}])
    data=parse_llm_json(content)
    if not isinstance(data,list):
        raise HTTPException(status_code=502,detail="模型未按格式返回")
    results=[]
    correct_count=0
    db=SessionLocal()
    for idx,it in enumerate(items):
        row=data[idx] if idx<len(data) else {}
        if not isinstance(row,dict):
            row={}
        correct_str=str(row.get("correct","")).lower()
        correct=1 if correct_str in ("true","对","1","正确") else 0
        score=str(row.get("score","")).strip() or "未评分"
        comment=str(row.get("comment","")).strip() or "无点评"
        record=AnswerRecord(question_id=it["qid"],question_title=it["title"],user_answer=it["answer"],correct=correct,score=score,comment=comment,user_id=q.user_id)
        db.add(record)
        db.commit()
        correct_count+=correct
        results.append({"question_id":it["qid"],"question_title":it["title"],"correct":correct,"score":score,"comment":comment})
    db.close()
    return {"ok":True,"results":results,"correct_count":correct_count,"total":len(results),"skipped":skipped}

# 答题统计：按分类与难度汇总答题数量与正确数，供统计页画图；user_id 只统计对应用户的记录
@app.get("/api/stats")
def get_stats(user_id:int=0):
    db=SessionLocal()
    query=db.query(AnswerRecord)
    if user_id:
        query=query.filter(AnswerRecord.user_id==user_id)
    records=query.all()
    total=len(records)
    correct=sum(1 for r in records if r.correct==1)
    qids=list(set(r.question_id for r in records))
    qmap={}
    if qids:
        qs=db.query(Question).filter(Question.id.in_(qids)).all()
        qmap={q.id:q for q in qs}
    cat_map={}
    dif_map={}
    for r in records:
        q=qmap.get(r.question_id)
        cat=q.category if q is not None else "未知"
        dif=q.difficulty if q is not None else "未知"
        if cat not in cat_map:
            cat_map[cat]={"answered":0,"correct":0}
        cat_map[cat]["answered"]+=1
        cat_map[cat]["correct"]+=r.correct
        if dif not in dif_map:
            dif_map[dif]={"answered":0,"correct":0}
        dif_map[dif]["answered"]+=1
        dif_map[dif]["correct"]+=r.correct
    db.close()
    by_category=[{"name":k,"answered":v["answered"],"correct":v["correct"]} for k,v in cat_map.items()]
    by_difficulty=[{"name":k,"answered":v["answered"],"correct":v["correct"]} for k,v in dif_map.items()]
    rate=round(correct/total,4) if total>0 else 0
    return {"total":total,"correct":correct,"correct_rate":rate,"by_category":by_category,"by_difficulty":by_difficulty}

@app.post("/grade")
def grade_answer(g:GradeIn):
    db=SessionLocal()
    question=db.query(Question).filter(Question.id==g.question_id).first()
    if question is None:
        db.close()
        raise HTTPException(status_code=404,detail="题目不存在")
    title=question.title
    std_answer=question.answer
    db.close()
    prompt=(
        "你是一名面试官，请批改下面这道题的回答。"
        "只输出 JSON，不要输出任何其他文字，格式为："
        '{"correct":true或false,"score":"评分","comment":"点评"}。'
        "题目："+title+"\n标准答案："+std_answer+"\n考生答案："+g.answer
    )
    content=call_llm([{"role":"user","content":prompt}])
    data=parse_llm_json(content)
    correct_str=str(data.get("correct","")).lower()
    correct=1 if correct_str in ("true","对","1","正确") else 0
    score=str(data.get("score","")).strip() or "未评分"
    comment=str(data.get("comment","")).strip() or "无点评"
    db=SessionLocal()
    record=AnswerRecord(question_id=g.question_id,question_title=title,user_answer=g.answer,correct=correct,score=score,comment=comment,user_id=g.user_id)
    db.add(record)
    db.commit()
    record_id=record.id
    db.close()
    return {"ok":True,"id":record_id,"correct":correct,"score":score,"comment":comment}

@app.get("/api/records")
def get_records(wrong:int=0,user_id:int=0):
    db=SessionLocal()
    query=db.query(AnswerRecord)
    if user_id:
        query=query.filter(AnswerRecord.user_id==user_id)
    if wrong:
        query=query.filter(AnswerRecord.correct==0)
    records=query.order_by(AnswerRecord.id.desc()).all()
    db.close()
    return [{"id":r.id,"question_id":r.question_id,"question_title":r.question_title,"user_answer":r.user_answer,"correct":r.correct,"score":r.score,"comment":r.comment,"user_id":r.user_id} for r in records]




@app.get("/")
def root():
    return FileResponse("static/index.html")

@app.get("/hello/{name}")
def hello(name:str):
    return{"hello":name}

@app.get("/greet")
def greet(name:str="world"):
    return{"greet":name}

# 题库列表：支持分类/难度/关键词筛选；count=组卷随机抽取条数，limit/offset=分页
# 分页时把筛选后的总数放在响应头 X-Total-Count，供前端计算总页数
@app.get("/questions")
def get_questions(response:Response,category:str="",difficulty:str="",q:str="",count:int=0,random:int=0,limit:int=0,offset:int=0):
    db=SessionLocal()
    query=db.query(Question)
    if category:
        query=query.filter(Question.category==category)
    if difficulty:
        query=query.filter(Question.difficulty==difficulty)
    if q:
        query=query.filter((Question.title.contains(q))|(Question.tags.contains(q)))
    if random:
        # 组卷随机抽取：只按随机排序；其余情况固定按 id 排序，保证新题永远排在最后一页
        query=query.order_by(func.random())
    else:
        query=query.order_by(Question.id)
    total=query.count()
    if count>0:
        query=query.limit(count)
    if limit>0:
        query=query.limit(limit).offset(offset)
        response.headers["X-Total-Count"]=str(total)
    question=query.all()
    db.close()
    return question

@app.get("/questions/{question_id}")
def get_question_id(question_id:int):
    db=SessionLocal()
    question=db.query(Question).filter(Question.id==question_id).first()
    if question is None:
        db.close()
        raise HTTPException(status_code=404,detail="题目不存在")
    db.close()
    return {"id":question.id,"title":question.title,"category":question.category,"difficulty":question.difficulty,"answer":question.answer,"tags":question.tags}

@app.put("/questions/{question_id}")
def update_question(question_id:int,q:QuestionIn):
    db=SessionLocal()
    question=db.query(Question).filter(Question.id==question_id).first()
    if question is None:
        db.close()
        raise HTTPException(status_code=404,detail="题目不存在")
    question.title=q.title
    question.category=q.category 
    question.difficulty=q.difficulty
    question.answer=q.answer
    question.tags=q.tags
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        db.close()
        raise HTTPException(status_code=409,detail="题目已存在")
    result={"id":question.id,"title":question.title,"category":question.category,"difficulty":question.difficulty,"answer":question.answer,"tags":question.tags}
    db.close()
    sync_question_vector(question_id,question_text(q.title,q.category,q.answer,q.tags))
    return result


@app.delete("/questions/{question_id}")
def delete_question(question_id:int):
    db=SessionLocal()
    question=db.query(Question).filter(Question.id==question_id).first()
    if question is None:
        db.close()
        raise HTTPException(status_code=404,detail="题目不存在")
    db.delete(question)
    db.commit()
    db.close()
    delete_question_vector(question_id)
    return {"ok":True,"id":question_id}

# RAG 检索演示接口：把查询文本向量化后返回题库中语义最相似的题目，验证向量检索链路
@app.get("/rag-search")
def rag_search_endpoint(q:str="",top_k:int=5):
    query=q.strip()
    if not query:
        return {"ok":True,"query":"","results":[]}
    results=rag_search_questions(query,top_k)
    return {"ok":True,"query":query,"results":results}


