# 基础镜像：Python 3.11 精简版
FROM python:3.11-slim

# 容器内工作目录
WORKDIR /app

# 先复制依赖清单并安装（用清华源加速），依赖不变时 Docker 会复用这一层缓存
COPY requirements.txt ./
RUN pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制项目代码、静态页面与数据库文件
COPY . .

# 对外端口
EXPOSE 8000

# 启动命令：监听 0.0.0.0，供容器外部访问
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]