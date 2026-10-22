import httpx
import os

api_key=os.environ.get("DASHSCOPE_API_KEY")


url="https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
headers={"Authorization":f"Bearer {api_key}"}
body={"model":"qwen-plus","messages":[{"role": "user", "content": "用一句话介绍FastAPI"}]}


r=httpx.post(url,headers=headers,json=body)

answer=r.json()["choices"][0]["message"]["content"]
print(answer)