# 使用 Docker 接收并运行 My Agent Next 镜像

本文面向收到 My Agent Next Docker 镜像的用户。接收方不需要创建 Python 虚拟环境，也不需要手动安装 Python 依赖，但必须安装 Docker，并准备自己的配置和持久化目录。

## 1. 接收方需要准备什么

- Windows：安装 Docker Desktop，并使用 Linux containers/WSL2 后端。
- Linux：安装 Docker Engine。
- macOS：安装 Docker Desktop。
- 至少准备一个未占用的本机端口，默认使用 `19845`。
- 准备模型 API Key；不要使用镜像制作者的私人密钥。

验证 Docker：

```bash
docker --version
docker run --rm hello-world
```

看到 `Hello from Docker!` 表示 Docker 可以正常运行 Linux 容器。

## 2. 推荐的交付内容

镜像制作者应交付：

```text
my-agent-next-package/
├─ my-agent-next.tar       # 离线镜像（使用仓库分发时不需要）
├─ docker-compose.yml
├─ .env.example
├─ data/                   # 持久化数据库、附件和运行日志
└─ skills/                 # 可持续修改的 Skill
```

不要把包含真实 API Key 的 `.env` 交付给其他用户。

## 3. 方式一：接收离线镜像文件

假设收到的镜像文件名为：

```text
my-agent-next.tar
```

进入交付目录并导入镜像：

```bash
docker load -i my-agent-next.tar
```

查看导入后的镜像：

```bash
docker image ls
```

本文后续假设镜像名称为：

```text
my-agent-next:latest
```

如果 `docker load` 显示了不同名称，请在 Compose 文件中使用实际名称。

## 4. 方式二：从镜像仓库下载

如果镜像已经推送到 Docker Hub 或私有仓库：

```bash
docker pull <仓库账号>/my-agent-next:latest
```

私有仓库需要先登录：

```bash
docker login <仓库地址>
```

不要把仓库密码或访问令牌写进 Compose 文件。

## 5. 创建运行目录

Linux/macOS：

```bash
mkdir -p my-agent-next-runtime/data/attachments
mkdir -p my-agent-next-runtime/data/agent-runs
mkdir -p my-agent-next-runtime/skills
cd my-agent-next-runtime
```

Windows PowerShell：

```powershell
New-Item -ItemType Directory -Force my-agent-next-runtime\data\attachments
New-Item -ItemType Directory -Force my-agent-next-runtime\data\agent-runs
New-Item -ItemType Directory -Force my-agent-next-runtime\skills
Set-Location my-agent-next-runtime
```

如果交付包已经包含 `data` 和 `skills`，直接使用交付包中的目录，不要重新创建或覆盖。

## 6. 创建自己的 `.env`

把 `.env.example` 复制为 `.env`：

Linux/macOS：

```bash
cp .env.example .env
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

编辑 `.env`，填入自己的密钥，例如：

```dotenv
OPENAI_API_KEY=your-openai-key
DEEPSEEK_API_KEY=your-deepseek-key
```

不要把 `.env` 上传到 Git、网盘公开链接或聊天记录。

## 7. 使用 Compose 启动

接收方使用的 `docker-compose.yml` 示例：

```yaml
services:
  backend:
    image: my-agent-next:latest
    container_name: my-agent-next-backend
    restart: unless-stopped
    ports:
      - "19845:19845"
    env_file:
      - ./.env
    volumes:
      - ./data:/app/my_agent_next/data
      - ./skills:/app/my_agent_next/skills
      - ./.env:/app/my_agent_next/.env
    extra_hosts:
      - "host.docker.internal:host-gateway"
    healthcheck:
      test:
        - CMD
        - python
        - -c
        - "import urllib.request; urllib.request.urlopen('http://127.0.0.1:19845/api/health', timeout=5)"
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 20s
```

如果镜像来自仓库，把 `image` 改为完整名称：

```yaml
image: <仓库账号>/my-agent-next:latest
```

启动：

```bash
docker compose up -d
```

第一次启动后检查：

```bash
docker compose ps
docker compose logs --tail 100 backend
```

状态应最终变为 `healthy`。

## 8. 打开应用

浏览器访问：

```text
http://127.0.0.1:19845
```

局域网其他设备需要使用运行 Docker 的电脑 IP，例如：

```text
http://192.168.1.20:19845
```

开放局域网访问前应检查操作系统防火墙。不要在缺少认证和反向代理保护时直接暴露到公网。

## 9. 验证健康接口

Linux/macOS：

```bash
curl http://127.0.0.1:19845/api/health
```

Windows PowerShell：

```powershell
Invoke-RestMethod http://127.0.0.1:19845/api/health
```

预期结果：

```json
{"status":"ok"}
```

## 10. Ollama 连接方式

容器中的 `127.0.0.1` 代表容器自身，不是 Windows 或 Linux 宿主机。Ollama 运行在宿主机时，应用中的 Ollama Base URL 应设置为：

```text
http://host.docker.internal:11434
```

宿主机 Ollama 必须允许来自 Docker 网络的连接。如果 Ollama 也使用 Compose 运行，应把两个服务放入同一个 Compose 网络，并使用 Ollama 的服务名连接，例如：

```text
http://ollama:11434
```

## 11. 常用管理命令

查看状态：

```bash
docker compose ps
```

查看实时日志：

```bash
docker compose logs -f backend
```

重启：

```bash
docker compose restart backend
```

停止并删除容器：

```bash
docker compose down
```

`docker compose down` 不会删除这里使用的 `data`、`skills` 和 `.env` 宿主机文件。

更新仓库镜像：

```bash
docker compose pull
docker compose up -d
```

离线镜像更新时，重新执行：

```bash
docker load -i my-agent-next.tar
docker compose up -d --force-recreate
```

## 12. 备份和迁移数据

停止容器后备份运行目录：

```bash
docker compose down
```

需要保留：

```text
data/app.db          # Agent、对话、工作流和其他持久化记录
data/attachments/    # 图片附件
data/agent-runs/     # Agent 运行日志
skills/              # Skill 内容
.env                 # 本机密钥，只能安全保存
```

将这些内容复制到另一台机器的相同运行目录，再启动同一版本镜像即可恢复。

## 13. 常见错误

### 端口已经被占用

把 Compose 中宿主机侧的端口改为其他值：

```yaml
ports:
  - "19846:19845"
```

然后访问 `http://127.0.0.1:19846`。

### API 返回 401

检查 `.env` 中的 API Key 是否正确，以及 Agent 绑定的模型配置是否使用了对应的环境变量。

### API 返回 402

检查模型供应商账户余额。该错误不是 Docker 引起的。

### Ollama 返回 Connection refused

不要在容器中使用 `http://127.0.0.1:11434` 连接宿主机 Ollama，改用 `http://host.docker.internal:11434`，并检查 Ollama 是否正在运行和监听外部连接。

### Skill 或对话在重建容器后消失

检查 `data` 和 `skills` 是否正确挂载。没有挂载的容器内部文件会随容器删除。

## 14. 验收清单

- [ ] Docker 可以运行 `hello-world`
- [ ] 镜像已经通过 `docker load` 或 `docker pull` 获取
- [ ] `.env` 使用接收方自己的密钥
- [ ] `data` 和 `skills` 已挂载到宿主机
- [ ] `docker compose ps` 显示 `healthy`
- [ ] `/api/health` 返回 `{"status":"ok"}`
- [ ] 浏览器可以打开工作台
- [ ] 已完成数据库、附件和 Skill 备份
