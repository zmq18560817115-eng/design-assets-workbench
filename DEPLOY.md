# 内网部署指南

本项目提供两种部署方式：**Docker Compose（推荐，一键）** 与 **手动部署**。

---

## 一、Docker Compose 部署（推荐）

内网服务器（Linux/Windows 均可，需装 Docker + Docker Compose）上：

```bash
git clone https://github.com/zmq18560817115-eng/linggan-agent.git
cd linggan-agent
docker compose up -d --build
```

- 前端： http://<服务器IP>:3000
- 后端接口文档： http://<服务器IP>:8000/docs

停止 / 查看日志：

```bash
docker compose down          # 停止
docker compose logs -f       # 查看日志
```

数据（上传的图片、SQLite 数据库）持久化在命名卷 `backend_uploads`、`backend_data` 中，
`docker compose down` 不会丢失；如需彻底清除数据加 `-v`。

### 内网/国内网络构建加速

若服务器拉取 pip / npm 依赖慢，编辑 `docker-compose.yml`，取消对应 `args` 注释即可切国内镜像：

```yaml
  backend:
    build:
      args:
        PIP_INDEX_URL: https://mirrors.aliyun.com/pypi/simple/
  frontend:
    build:
      args:
        NPM_REGISTRY: https://registry.npmmirror.com
```

### 完全离线的内网（服务器无外网）

在一台有外网的机器上构建并导出镜像，再拷贝到内网导入：

```bash
# 有外网的机器
docker compose build
docker save linggan-backend linggan-frontend -o linggan-images.tar

# 拷贝 linggan-images.tar 到内网服务器后
docker load -i linggan-images.tar
docker compose up -d          # 直接用已加载镜像，不再联网构建
```

---

## 二、手动部署（不使用 Docker）

### 后端

```bash
cd backend
pip install -r requirements.txt
# 生产建议不加 --reload，可用多进程
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 前端

```bash
cd frontend
npm ci
npm run build
# 指向后端地址后启动
BACKEND_URL=http://<后端IP>:8000 npm run start   # 监听 3000
```

Windows PowerShell 下设置环境变量：

```powershell
$env:BACKEND_URL="http://127.0.0.1:8000"; npm run start
```

#### 用 standalone 产物部署（不带 node_modules，体积小）

项目启用了 `output: "standalone"`。`npm run build` 后会自动（postbuild 脚本）把
`.next/static` 与 `public` 拷入 `.next/standalone`，因此可直接运行：

```bash
npm run build
BACKEND_URL=http://<后端IP>:8000 npm run start:standalone   # = node .next/standalone/server.js
```

> ⚠️ 常见坑：**直接 `node .next/standalone/server.js` 却没有静态资源** → 页面能打开但
> 样式(CSS)全丢。原因是 Next 的 standalone 输出默认不含 `.next/static` 与 `public`。
> 本项目已用 postbuild 脚本自动补齐；若你手工拷贝 standalone 到别处，记得把这两个目录
> 一起带上：
>
> ```
> .next/standalone/
>   ├── server.js
>   ├── .next/static/   ← 必须
>   └── public/         ← 必须
> ```

---

## 三、关键配置项（环境变量）

| 变量 | 作用 | 默认值 |
|------|------|--------|
| `BACKEND_URL` | 前端把 `/api`、`/uploads` 代理到的后端地址 | `http://127.0.0.1:8000` |
| `DATABASE_URL` | 后端数据库连接串（可换 PostgreSQL/Supabase） | SQLite 本地文件 |
| `CORS_ORIGINS` | 后端允许的跨域来源（逗号分隔） | localhost:3000 |
| `VISION_PROVIDER` | 视觉分析方式：`mock`/`openai`/`qwen` | `mock` |
| `VISION_API_KEY` / `VISION_BASE_URL` / `VISION_MODEL` | 接入真实视觉大模型的凭证 | 空 |

> 未配置 `VISION_*` 时使用内置的离线启发式分析器，开箱即用、无需任何外部 API。

---

## 四、反向代理（可选）

生产环境通常在最前面加 Nginx，把 80/443 转发到前端 3000，示例：

```nginx
server {
    listen 80;
    server_name linggan.example.com;
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

前端 Node 服务会自行把 `/api`、`/uploads` 反代到后端，因此只需暴露前端一个入口即可。

> ⚠️ 「AI 生成设计方法论」等大模型接口是长耗时请求（可能 1~2 分钟）。若前面加了 Nginx，
> 请调高读超时，避免 504：`proxy_read_timeout 300s; proxy_send_timeout 300s;`。
