# Vercel 前端与 Python 后端

## 当前边界

前端是独立 HTML/CSS/JavaScript，Vercel 构建不安装 Python、不处理 PDF、不计算向量。后端保留本地 BGE 向量 + BM25 检索。没有实时后端时，前端仍能浏览10道题的v4最终评测，并切换查看v3历史失败案例；已保存评测与实时检索明确区分。

本轮只准备部署文件，不创建付费资源。后端平台和费用由你确认后再上线。

## 本机预览

在项目目录运行 `powershell -ExecutionPolicy Bypass -File .\start-web.ps1`，访问 http://127.0.0.1:3000 。需要 Python 3.11 环境和 Node.js 20+（本机脚本也能找到已有的 Codex Node 运行时）。先完成 v4 提取与索引。本机后端绑定 127.0.0.1，只有此模式允许使用仓库之外的已有授权。重启电脑后重新运行脚本。已有旧 Streamlit 页面仍可通过 `run.ps1` 启动。

需要重启本项目服务时，先运行 `stop-web.ps1` 再运行 `start-web.ps1`。停止脚本会校验记录的进程属于本项目，再停止它及 Python 子进程。

## Vercel 操作

1. 将代码推送到自己的 GitHub 仓库。不要提交 `.env`、`deploy-data`、模型缓存和授权文件。
2. 登录 Vercel，Add New → Project，导入这个仓库。
3. Root Directory 选仓库根目录，Framework Preset 选 Other。仓库 `vercel.json` 已指定构建命令 `node frontend/build.mjs`、输出目录 `frontend/dist`。
4. 没有后端时直接部署，即可得到v4评测记录演示页面（尚无实时检索）。
5. 后端上线后，在 Vercel 项目环境变量设置 `RAG_API_URL=https://你的后端域名`，重新部署。这里只填公开地址，不能填 API key、OAuth token 或带凭据的 URL。
6. 将实际 Vercel 生产域名加入后端 `RAG_ALLOWED_ORIGINS`，例如 `https://your-project.vercel.app`。预览域名需要单独加入；禁止随意使用通配符。

官方设置说明：[Vercel 项目配置](https://vercel.com/docs/project-configuration/vercel-json)。

## 后端部署包

索引完成后运行 `python -m financial_rag.package_backend`，生成被 Git 忽略的 `deploy-data/`。该目录只从白名单复制索引和公开 BGE 模型，不复制 `.env` 或授权。财报 PDF 不需上传，引用直接跳转官方原文。

有 Docker 的机器可运行：

```sh
docker build -t financial-report-rag .
docker run --restart unless-stopped -p 8000:8000 \
  -e RAG_ALLOWED_ORIGINS=https://your-project.vercel.app \
  financial-report-rag
```

容器固定监听 8000；托管平台将 HTTP 服务端口设为 8000，并提供 HTTPS 域名。健康检查为 `/health`。使用单进程，避免每个 worker 重复加载模型和索引。运行内存仍需实际容器测量，建议从 2 GB 内存规格评估，构建向量建议 4 GB 以上；不能承诺小内存免费实例可以稳定运行。

GitHub 自动部署的平台不会拥有被忽略的 `deploy-data/`。应在本机或受控构建机生成它，再构建镜像并上传自己的镜像仓库；或由构建机执行下载、提取、索引步骤后构建镜像。不要误以为只导入 GitHub 就具备检索数据。原始年度报告可由 `python -m financial_rag.download` 复现。

镜像运行模式固定为 public；不要给云后端配置作者自己的 `OPENAI_API_KEY`，不要上传作者 OAuth 凭据。镜像构建上下文使用白名单 `.dockerignore`。

## 访客如何使用

默认只检索证据，不调用模型。访客选择 GPT 后，输入自己的 OpenAI API key 与自己有权限的模型；密钥仅在当前页面内存中，提交查询时通过 HTTPS 发到本站后端，再调用固定的 OpenAI 官方地址。后端不把密钥写入记录，也不会回退到作者的本地授权。部署者仍需保证代理、应用和监控系统不记录请求正文；访客应只在信任的部署站点填写 key。

本地 OAuth 使用 Windows DPAPI，不能直接复制到 Linux 云容器。你自己仍可使用本机新页面的“本机已有授权”；公开页面采用访客自带 key。

API key 模式每次最多输出 3,500 tokens；证据超过 60,000 字符时拒绝生成并提示缩小范围，不静默删证据。该限制不能保证固定货币费用，访客仍应在自己的 OpenAI 项目控制预算。模型请求没有自动重试。

## 上线验收

- 未连后端时有明确演示状态，10道v4评测、v3历史失败案例和出处可查看。
- 后端健康接口就绪；Vercel 页面能真实召回 v4 数据并下载记录。
- 仅 BM25、仅向量、混合检索及公司／年度筛选正常。
- 公开模式拒绝 local 授权，缺少访客 key 时不会调用作者账户。
- 官方 PDF 链接页码正确；手机页面正常；仓库及构建产物无秘密。

本机没有 Docker 时，不能据本机 Python 测试声称 Linux 镜像已实际通过；上线前需完成镜像构建和 HTTPS 联调。
