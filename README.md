# 白酒财报问答知识库（课程作业方向 A）

新增独立网页前端与 FastAPI 后端，Vercel 部署步骤见 [DEPLOYMENT.md](DEPLOYMENT.md)。本机新版页面运行 `start-web.ps1` 后访问 `http://127.0.0.1:3000`；原 Streamlit 页面仍可使用。

12 家 A 股白酒公司，2024、2025 两年，共 24 份年度报告全文。资料来自巨潮资讯官方披露，下载链接、发布日期、SHA256 和 PDF 页数见 `data/manifest.json`。

## 本地运行

建议 Python 3.11。首次下载模型和处理 4,408 页报告需要时间；下载、提取、向量计算均有本地缓存。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
# 在本地 .env 填自己的 API key；不要上传 .env
.\.venv\Scripts\python.exe -m financial_rag.download
.\.venv\Scripts\python.exe -m financial_rag.extract
.\.venv\Scripts\python.exe -m financial_rag.retrieval
.\.venv\Scripts\python.exe -m streamlit run app.py
```

默认 `AUTH_MODE=api_key`，使用运行者自己的 OpenAI API key；运行者自行承担 API 费用。没有 key 也可取消“使用 GPT”复选框，查看真实检索结果。向量由本地 BGE 模型计算，不调用收费的 embedding API。

本项目还支持经过验证的官方 ChatGPT 授权模式：Windows 上运行 `python -m financial_rag.oauth`，在官方浏览器页面授权；将本地 `.env` 的 `AUTH_MODE` 设为 `chatgpt_oauth`、`CHAT_MODEL` 留空。模型从账户返回的可用列表选取，凭据由 Windows DPAPI 加密，保存在用户目录 `.financial-report-rag`，不会写入仓库。额度用尽时停止，不自动转用收费 API。该官方预览能力受账户资格、模型和计划额度限制，不保证所有账户都能使用。

本机环境已经建立索引时，可用 `run.ps1` 启动页面，或运行上述 Streamlit 命令。

官方授权说明：[登录流程](https://developers.openai.com/siwc/token-sharing-open-source/sign-in)、[模型和推理](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference)、[预览限制](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations)。项目不读取 Codex、ChatGPT 或其他应用的已有认证文件。

## 方法

- PDF 原始文本逐页提取；用严格线段识别还原表格，保留列名、列号、单元格值及原始行。合并单元格留空，不猜测数值。同行不拆开，相邻行按约 800 字打包。叙述按 800 字、120 字重叠切分。
- 每块含公司、股票代码、年报年度、章节、PDF 页码及块 ID。页码是 PDF 文件从 1 开始的物理页码。
- 同页多个章节并列标注，后续页继承最后一个标题。原始 v3 实验曾保留构建时 `embedding_text` 快照；新 v4 库使用当前提取内容重新计算向量，并以模型名称和文本内容指纹隔离缓存，避免复用旧向量。
- v4 修复续表首行金额误作表头：识别多行表头；只有相邻页、列数、表格位置与财务报表标题对应时继承年度列。不能确认的表头明确标记“未识别列”，保留首行及原始值，不猜测口径。该修复不等于全库逐单元格校验。
- 本地 `BAAI/bge-small-zh-v1.5` 512 维向量，余弦相似度；jieba 分词 + BM25；RRF 融合两类召回。
- 普通问题可按公司和年度筛选。全景模式逐公司召回，避免全局 top-k 只覆盖少数公司。覆盖公司数代表有块被召回，不代表答案必然完整、正确。
- 默认启用混合检索增强：展开“归母”等术语、按公司及年度分别召回，单公司题补全最相关页面上的其他块。对照实验另保留未增强的三种索引模式，并分别记录增强效果。
- v4 增强检索额外按表格的年度列、指标行名及前25页位置识别年度指标表，优先补入相关原文行。该规则不读取参考答案文件；不能确认年度列时仍依赖常规检索，可能遗漏或发生口径错误。
- GPT 仅根据召回证据作答，每项事实标引用编号，可展开原文并跳转官方 PDF。

## 实验与交付

`output/questions.json`：10道题，含2道12公司全景题。`output/financial_facts.json`：由原始PDF核对的年度指标参考数据。

当前交付使用 **v4**：`output/evaluation_v4/`保存10份实际回答、完整召回块、原自动诊断及人工复核；`output/evaluation_records_v4.md`逐题说明。2026-10-10增强混合检索实测，模型`gpt-6-luna`，本地已有授权，10次调用，输入62,810 / 输出1,916 tokens。人工复核10/10；自动诊断9/10。Q03题意为约数，65.8%符合实际比值65.768690%，自动检查要求65.77%而漏判，原诊断完整保留。复核由助手完成，不是教师评分。

这10题用于开发和调试，不是独立留出测试，不能外推总体准确率。v3与v4的模型、提取及检索流程均有变化，不能将结果差异归因于某一个改动。

历史v3实验保留于`output/evaluation/`、`output/manual_review.json`和`output/evaluation_records.md`，共42份实际结果。向量4/10、BM25 3/10、混合5/10、增强混合7/10，模型`gpt-5.6-luna`。失败包括全景信息遗漏、现金流计算、把净流出称为亏损；两次模型目录请求超时记录另存`evaluation_attempts/`。历史回答和拒答没有改写。

交付文件：`output/pdf/conclusion.pdf`（已验证一页、当前v4结论）；`output/screenshots/v4_*.png`（当前问答页面）；`output/submission.txt`（上传后填写仓库地址）。前端默认v4评测，可切换v3历史实验，保存记录不会冒充实时生成。

生成参考答案及评测（会调用模型、消耗计划额度或自己的 API 余额；本轮没有重跑42次生成实验）：

```powershell
python -m financial_rag.prepare_evaluation
python -m financial_rag.evaluate
```

评测写入 `output/evaluation_v4/`，不会覆盖 v3 历史实验；重跑前请另存现有v4结果，并重新人工复核，不能沿用评分。控制成本可只运行 `python -m financial_rag.evaluate --modes hybrid_expanded --question-ids Q02 Q03`。不调用模型的实时检索检查用 `python -m financial_rag.verify_web`。

`MAX_MODEL_CALLS` 为单次本地实验目录累计调用次数上限，包含失败请求。请求不自动重试。API key 模式限制回答输出 token；授权模式按官方支持字段调用。真实 token 用量保存在各评测记录中；调用次数限制不等于货币预算限制。

## 数据和密钥

收录复核见 `output/report_accuracy_audit.md` 及其 JSON：24份官方PDF重新下载后与本地SHA256一致，公司/年度/全文身份通过；72项年度营收、归母净利润、经营现金流金额与合并报表核对一致。23条发布日期已由UTC修正为中国时区。该文件记录修复前 v3 的1,744个可疑表头块，可疑数量不等于错误数量。修复后回归检查见 `output/extraction_v4_audit.json`，可运行 `python -m financial_rag.check_extraction` 重现。原始文件正确不代表提取库完全准确。

`output/evaluation/`与旧截图保留v3历史证据；当前结论PDF和`v4_`截图对应v4最终评测。v4 索引位于被忽略的 `data/index_v4/`。

仓库不包含原始 PDF、模型缓存、向量索引、私有 `.env` 或授权凭据，包含官方下载清单和可复现脚本。上传前检查 `.gitignore`。不要提交密码、API key、用户目录或浏览器授权日志。

已知限制：复杂表格、无框线表格、跨页表格和扫描页仍可能识别不完整；章节识别主要基于“第…节”；BGE 的输入长度可能截断较长块，切块字数不等于 tokenizer 的长度。金额与口径、重述数据及跨公司完整性需要回到原文核对。财报知识随年报更新，适合通过检索更新事实；本项目没有微调模型。
