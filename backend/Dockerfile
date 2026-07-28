# 后端镜像：FastAPI + Uvicorn
FROM python:3.11-slim

# 可选：构建时用国内 pip 镜像加速（内网/国内网络更快）
ARG PIP_INDEX_URL=https://pypi.org/simple
ENV PIP_INDEX_URL=${PIP_INDEX_URL}

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# 上传目录（挂载卷以持久化素材）
RUN mkdir -p uploads

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
