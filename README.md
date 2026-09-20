# InnoCite — 学术论文创新点提炼与跨学科推荐系统

基于 Web 的学术论文分析平台。支持多种方式导入论文（arXiv / CSV / PDF / EndNote），自动提炼"问题-方法-效果"三维创新点，构建关键词热度时序曲线，通过语义向量实现跨学科创新迁移推荐，一键导出综合报告。

---

## 目录

- [功能概览](#功能概览)
- [从零开始配置（给接手者）](#从零开始配置给接手者)
  - [1. 基础环境](#1-基础环境)
  - [2. 获取 DeepSeek API Key（重要）](#2-获取-deepseek-api-key重要)
  - [3. 下载项目并安装依赖](#3-下载项目并安装依赖)
  - [4. 配置环境变量](#4-配置环境变量)
  - [5. 下载 SBERT 模型（国内用户必做）](#5-下载-sbert-模型国内用户必做)
  - [6. 初始化数据库](#6-初始化数据库)
  - [7. 启动应用](#7-启动应用)
- [环境变量完整参考](#环境变量完整参考)
- [功能开关说明](#功能开关说明)
- [项目结构](#项目结构)
- [API 端点](#api-端点)
- [技术栈](#技术栈)
- [常见问题](#常见问题)

---

## 功能概览

| 模块 | 功能 | 技术方案 |
|------|------|----------|
| 📥 **论文导入** | arXiv ID / 关键词搜索 / CSV / PDF / EndNote | GROBID 学术 PDF 解析 + 魔数安全校验 |
| 🔐 **用户认证** | 登录/登出、Session 管理、全局拦截 | 毛玻璃渐变登录页、CSRF 保护 |
| 💡 **创新点提炼** | 自动抽取"问题-方法-效果"三维创新点 | DeepSeek（优先）→ 规则引擎（回退） |
| 📈 **关键词热度** | 关键词提取 + 时序曲线 + 热力图 | KeyBERT(SBERT) → TF-IDF 双轨 |
| 🔗 **跨学科推荐** | 语义向量相似度匹配，发现跨领域创新迁移 | SBERT(384维) → TF-IDF 双轨，批量矩阵运算 |
| 📄 **报告导出** | 图表 + 表格综合报告一键导出 | reportlab + Plotly 渲染 |
| 📋 **数据导出** | CSV / JSON 格式导出 | 支持搜索条件筛选 |

---

## 从零开始配置（给接手者）

> 以下步骤假设你有一台 **未安装任何相关依赖** 的 Windows 电脑，从零开始配到能跑。

### 1. 基础环境

| 软件 | 最低版本 | 下载地址 | 说明 |
|------|----------|----------|------|
| Python | 3.9+ | https://www.python.org/downloads/ | **安装时勾选 "Add Python to PATH"** |
| Git（可选） | 任意 | https://git-scm.com/downloads | 用于版本管理，不用也行 |
| Docker（可选） | 任意 | https://www.docker.com/products/docker-desktop | 仅 GROBID PDF 解析需要，不用也行 |

安装 Python 后，打开终端（PowerShell 或 CMD），验证：

```powershell
python --version   # 应显示 Python 3.9.x 或更高
pip --version      # 应显示 pip 版本号
```

---

### 2. 获取 DeepSeek API Key（重要）

> **DeepSeek 是系统的"大脑"**，负责创新点提取、推荐理由生成、论文学科分类、文献综述生成。不配也能跑（回退到规则引擎），但效果差很多。

**步骤：**

1. 打开 https://platform.deepseek.com/
2. 注册账号（手机号即可）
3. 进入「API Keys」页面，点击「创建 API Key」
4. 复制生成的 key（格式为 `sk-xxxxxxxxxxxxxxxx`）

**费用参考：**
- DeepSeek 定价极低，约 **¥1/百万 tokens**
- 处理一篇论文的创新点提取约消耗 2000 tokens，成本约 **¥0.002**
- 新注册用户通常有免费额度

> ⚠️ **重要**：API Key 不要提交到 Git！本项目已配置 `.gitignore` 忽略 `.env` 文件。

---

### 3. 下载项目并安装依赖

```powershell
# 进入项目文件夹
cd InnoCite

# 创建虚拟环境（推荐，避免污染系统 Python）
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# macOS/Linux:
# source venv/bin/activate

# 安装 Python 依赖（约 2-3 分钟，首次需下载约 500MB）
pip install -r requirements.txt
```

> 如果 `pip install` 速度慢，先用国内镜像：
> ```powershell
> pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
> ```

---

### 4. 配置环境变量

将 `.env.example` 复制为 `.env`，然后编辑 `.env` 填入实际值：

```powershell
copy .env.example .env
notepad .env    # 或用你喜欢的编辑器打开
```

**`.env` 文件内容（最少配置）：**

```env
# 必填：DeepSeek API Key（从 platform.deepseek.com 获取）
DEEPSEEK_API_KEY=sk-你的key

# HuggingFace 镜像（国内用户必须配置，用于下载 SBERT 模型）
HF_ENDPOINT=https://hf-mirror.com

# 可选：应用环境
# APP_ENV=development
```

完整配置项见下方 [环境变量完整参考](#环境变量完整参考)。

---

### 5. 下载 SBERT 模型（国内用户必做）

> **SBERT 是系统的"尺子"**，负责计算论文学术相似度。模型文件托管在 HuggingFace，国内直连会被墙，需要用镜像下载。

**方式一：用镜像自动下载（推荐）**

确保 `.env` 中已配置 `HF_ENDPOINT=https://hf-mirror.com`，然后运行：

```powershell
# 激活虚拟环境后执行
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
```

首次运行会从镜像下载模型（约 **90MB**），存放于 `C:\Users\<用户名>\.cache\huggingface\`。之后不再需要联网。

**方式二：手动下载（备选）**

如果方式一失败，可以用浏览器直接下载模型文件（约 90MB），解压后放到对应目录。具体文件清单见常见问题。

---

### 6. 初始化数据库

```powershell
python init_db.py
```

这一步会：
- 创建 SQLite 数据库文件 `instance/innocite.db`
- 建立所有数据表
- 插入 **20 篇示例论文**（覆盖计算机视觉、NLP、AI 三个学科，演示用合成数据）
- 创建管理员账户（默认 `admin / admin123`）
- 预计算 SBERT 嵌入向量和推荐缓存

> 💡 脚本**幂等可重复运行**：已存在的示例论文按 arXiv ID 自动跳过，不会重复插入。

---

### 7. 启动应用

```powershell
python app.py
```

浏览器访问 **http://127.0.0.1:5000**，使用默认管理员账户登录：

| 用户名 | 密码 |
|--------|------|
| `admin` | `admin123` |

> ⚠️ 生产环境务必修改管理员密码！可通过环境变量 `ADMIN_USERNAME` / `ADMIN_PASSWORD` 设置。

---

## 环境变量完整参考

所有配置项均可通过 `.env` 文件或系统环境变量设置（`.env` 文件优先级更高）。

### 必填

| 变量 | 说明 | 从哪里获取 |
|------|------|-----------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 | https://platform.deepseek.com/ → API Keys |

### 国内网络必配

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `HF_ENDPOINT` | `https://huggingface.co` | **国内用户必须设为 `https://hf-mirror.com`**，否则 SBERT 模型无法下载 |

### 应用基础

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `APP_ENV` | `development` | 环境：`development` / `testing` / `production` |
| `SECRET_KEY` | 随机生成 | Flask 密钥（生产环境务必设置固定值） |
| `DATABASE_URL` | `sqlite:///instance/innocite.db` | 数据库连接字符串 |

### DeepSeek LLM

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DEEPSEEK_API_KEY` | （空） | API 密钥 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | API 地址（一般不用改） |
| `DEEPSEEK_MODEL` | `deepseek-v4-flash` | 快速任务模型（推荐理由生成、学科分类） |
| `DEEPSEEK_MODEL_PRO` | `deepseek-v4-pro` | 深度推理模型（创新点提取、文献综述） |
| `LLM_TIMEOUT` | `30` | API 请求超时秒数 |
| `LLM_MAX_RETRIES` | `2` | API 调用失败重试次数 |
| `LLM_TEMPERATURE` | `0.3` | 生成温度（0-1，越低越确定） |

### 功能开关

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_INNOVATION_ENABLED` | `1` | 是否用 DeepSeek 提取创新点（设为 `0` 只用规则引擎） |
| `LLM_REASON_ENABLED` | `1` | 是否用 DeepSeek 生成推荐理由（设为 `0` 用模板） |
| `KEYBERT_ENABLED` | `1` | 是否用 KeyBERT 提取关键词（设为 `0` 只用 TF-IDF） |
| `AUTO_CLASSIFY_ENABLED` | `1` | 是否自动分类论文学科 |

### 管理员

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ADMIN_USERNAME` | `admin` | 默认管理员用户名（仅首次初始化时生效） |
| `ADMIN_PASSWORD` | `admin123` | 默认管理员密码（**生产环境务必修改**） |

### PDF 解析

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `GROBID_ENABLED` | `1` | 是否启用 GROBID（需 Docker 启动 GROBID 服务） |
| `GROBID_URL` | `http://localhost:8070` | GROBID 服务地址 |
| `GROBID_TIMEOUT` | `30` | GROBID 请求超时秒数 |

### 其他

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LOG_LEVEL` | `INFO` | 日志级别：`DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `SBERT_MODEL_NAME` | `all-MiniLM-L6-v2` | SBERT 模型名称（一般不用改） |
| `TFIDF_MAX_FEATURES` | `3000` | TF-IDF 最大特征数 |
| `RECOMMENDATION_TOP_N_DEFAULT` | `3` | 推荐结果默认返回条数 |

---

## 功能开关说明

系统采用"**多层回退**"架构，每个功能都有主方案和兜底方案：

| 功能 | 主力方案 | 回退方案 | 回退触发条件 |
|------|----------|----------|-------------|
| 创新点提取 | DeepSeek API | 规则引擎（触发词 + 正则） | API Key 未配 / 网络不通 / API 报错 |
| 推荐理由 | DeepSeek API | 模板规则 | 同上 |
| 论文分类 | SBERT 语义匹配 | DeepSeek API → 返回"未知" | SBERT 不可用 → DeepSeek 也不可用 |
| 关键词提取 | KeyBERT (SBERT) | TF-IDF 统计频率 | SBERT 模型加载失败 / 功能开关关闭 |
| 跨学科推荐 | SBERT (384维向量) | TF-IDF (3000维稀疏) | SBERT 模型加载失败 |
| PDF 解析 | GROBID 学术解析 | pdfplumber 本地提取 | Docker 未启动 / GROBID 不可达 |

> **最简可用状态**：不配 DeepSeek + 不装 SBERT → 全部回退到规则引擎 + TF-IDF，功能完整但精度较低。
>
> **最佳效果**：配 DeepSeek + 装 SBERT → 全功能满血运行。

---

## 项目结构

```
InnoCite/
├── app.py                  # Flask 主入口（工厂模式 + CSRF + 登录拦截）
├── config.py               # 多环境配置（dev/test/prod）
├── models.py               # 数据模型（Paper / Innovation / KeywordCache / LLMCache 等）
├── .env                    # 实际环境变量（不提交 Git）⚠️
├── .env.example            # 环境变量模板（可提交 Git）
│
├── llm_client.py           # DeepSeek LLM 统一客户端（含持久化响应缓存）
├── innovation_extractor.py # 创新点提取（LLM 优先 + 规则回退）
├── paper_classifier.py     # 论文学科分类（SBERT → LLM 三轨）
├── keybert_extractor.py    # KeyBERT 关键词提取
├── keyword_trend.py        # 关键词时序热度分析
├── recommender.py          # 跨学科推荐（SBERT/TF-IDF 双轨 + 批量矩阵）
├── paper_parser.py         # 论文解析（arXiv/CSV/PDF/EndNote）
├── report_generator.py     # PDF 综合报告生成
├── grobid_client.py        # GROBID 学术 PDF 解析客户端
├── evaluator.py            # 模型评估工具
│
├── init_db.py              # 数据库初始化（建表 + 示例数据 + 管理员）
├── requirements.txt        # Python 依赖清单
├── pytest.ini              # pytest 配置
│
├── tests/                  # 最小测试集（规则提取器 / 推荐器 / 评估器）
│   ├── conftest.py         # 测试 fixture（内存 SQLite 应用）
│   ├── test_rule_extractor.py
│   ├── test_recommender.py
│   └── test_evaluator.py
│
├── utils/                  # 工具模块
│   ├── sbert_manager.py    # SBERT 全局单例管理器（含线程安全 encode）
│   ├── task_queue.py       # 后台线程池（独立 app context / session）
│   ├── gzip_middleware.py  # Gzip 压缩中间件
│   └── response.py         # 统一 API 响应格式
│
├── routes/                 # 路由蓝图（8 模块）
│   ├── auth.py             # 登录/登出
│   ├── papers.py           # 论文导入与管理
│   ├── innovation.py       # 创新点提取与编辑
│   ├── trends.py           # 关键词趋势
│   ├── recommend.py        # 跨学科推荐
│   ├── report.py           # 报告与导出
│   ├── admin.py            # 系统管理
│   ├── bookmarks.py        # 收藏功能
│   └── helpers.py          # 共享服务实例
│
├── templates/              # Jinja2 页面模板
├── static/                 # CSS / JS 静态资源
├── data/                   # 停用词表等数据文件
├── instance/               # 运行时生成（数据库、日志、上传文件）
│
├── README.md               # 本文件
└── USER_GUIDE.md           # 用户使用指南
```

---

## API 端点

### 页面

| 方法 | 路由 | 说明 | 需登录 |
|------|------|------|:------:|
| `GET` | `/` | 首页 - 论文列表与管理 | ✅ |
| `GET` `POST` | `/auth/login` | 登录 | — |
| `GET` | `/auth/logout` | 登出 | — |
| `GET` | `/papers/<id>` | 论文详情 | ✅ |
| `GET` | `/trends` | 关键词热度曲线 | ✅ |
| `GET` | `/recommend` | 跨学科推荐 | ✅ |
| `GET` | `/report` | 综合报告 | ✅ |
| `GET` | `/timeline` | 创新点时间线 | ✅ |
| `GET` | `/about` | 使用说明 | ✅ |
| `GET` | `/healthz` | 健康检查（DB / SBERT / LLM 状态） | — |

### 论文导入

| 方法 | 路由 | 说明 | 需登录 |
|------|------|------|:------:|
| `POST` | `/import/arxiv-id` | 通过 arXiv ID 导入 | ✅ |
| `POST` | `/import/arxiv-search` | arXiv 关键词搜索批量导入 | ✅ |
| `POST` | `/import/csv` | 上传 CSV 批量导入 | ✅ |
| `POST` | `/import/pdf` | 上传 PDF 解析导入 | ✅ |
| `POST` | `/import/enw` | 上传 EndNote 文件导入 | ✅ |

### 数据 API

| 方法 | 路由 | 说明 | 需登录 |
|------|------|------|:------:|
| `GET` | `/api/stats` | 数据库统计摘要 | ✅ |
| `GET` | `/api/keywords` | 关键词热力图数据 | ✅ |
| `POST` | `/api/trend` | 指定关键词时序曲线 | ✅ |
| `GET` | `/api/top-keywords` | 热度排名 TOP N | ✅ |
| `GET` | `/api/recommend` | 获取推荐 (params: paper_id, top_n) | ✅ |
| `GET` | `/api/innovations` | 分页创新点列表 | ✅ |

### 论文操作

| 方法 | 路由 | 说明 | 需登录 |
|------|------|------|:------:|
| `POST` | `/papers/<id>/delete` | 删除论文 | ✅ |
| `GET` | `/papers/<id>/innovation` | 获取创新点 | ✅ |
| `POST` | `/papers/<id>/innovation` | 保存/编辑创新点 | ✅ |

### 导出

| 方法 | 路由 | 说明 | 需登录 |
|------|------|------|:------:|
| `POST` | `/api/export_pdf` | 导出 PDF 报告 | ✅ |
| `GET` | `/api/export/csv` | 导出 CSV | ✅ |
| `GET` | `/api/export/json` | 导出 JSON | ✅ |
| `GET` | `/api/csv-template` | 下载 CSV 导入模板 | ✅ |

### 管理

| 方法 | 路由 | 说明 | 需登录 |
|------|------|------|:------:|
| `POST` | `/api/rebuild-embeddings` | 重建全部 SBERT 嵌入 | ✅ |
| `POST` | `/api/rebuild-recommendations` | 重建全部推荐缓存 | ✅ |

### 文档

| 方法 | 路由 | 说明 |
|------|------|------|
| `GET` | `/apidocs/` | Swagger 交互式 API 文档 |

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | Flask 3.x（工厂模式 + 蓝图） |
| 数据库 | SQLite + SQLAlchemy ORM |
| 认证安全 | Session 登录 + Flask-WTF CSRF + 文件魔数校验 |
| 大语言模型 | DeepSeek API（v4-flash + v4-pro 双模型策略） |
| 语义向量 | SentenceTransformers (all-MiniLM-L6-v2, 384维) |
| PDF 解析 | GROBID（优先）+ pdfplumber（回退） |
| 中文分词 | jieba |
| 关键词 | KeyBERT + sklearn TfidfVectorizer |
| 推荐算法 | sklearn cosine_similarity（批量矩阵运算） |
| 可视化 | Plotly.js（趋势曲线 + 饼图 + 热力图） |
| PDF 生成 | reportlab + plotly.io.write_image |
| 测试 | pytest（`python -m pytest`，最小测试集见 `tests/`） |
| 日志 | RotatingFileHandler（10MB × 10 滚动归档） |
| 前端 | Bootstrap 5 + 暗色模式 |
| API 文档 | Flasgger / Swagger |

---

## 示例数据

> ⚠️ **演示用合成数据**：初始化示例论文为**自创数据**（`data/sample_papers.json`），标题、作者、指标均为原创虚构，不引用任何真实论文，不存在知识产权争议。界面展示时请说明"演示数据"。

初始化后包含 **20 篇**示例论文，覆盖 3 个学科（2018-2024）：

| 学科 | 数量 | 研究主题 |
|------|:----:|----------|
| cs.CV（计算机视觉） | 7 | 视觉识别、目标检测、图像生成、分割、多模态、神经渲染等 |
| cs.CL（自然语言处理） | 7 | 预训练、机器翻译、问答、模型微调、推理、蒸馏等 |
| cs.AI（人工智能） | 6 | 图学习、强化学习、因果发现、联邦学习、异常检测、多智能体等 |

其中 3 篇预置了完整创新点（问题-方法-效果三维），其余论文导入后自动提取。

---

## 常见问题

### Q: 启动后提示 "HuggingFace 网络不可用，SBERT 将不可用"？

国内网络无法直连 HuggingFace。解决方案：
1. 在 `.env` 中设置 `HF_ENDPOINT=https://hf-mirror.com`
2. 运行 `python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"` 下载模型
3. 重启应用

详见 [步骤 5：下载 SBERT 模型](#5-下载-sbert-模型国内用户必做)。

### Q: DeepSeek API 调用失败？

检查以下几点：
- `.env` 中 `DEEPSEEK_API_KEY` 是否正确（以 `sk-` 开头）
- 账户是否有余额：https://platform.deepseek.com/ → 账户概览
- 网络能否访问 `https://api.deepseek.com`（国内一般可以直连）

即使 DeepSeek 不可用，系统会自动回退到规则引擎，功能不会完全丢失。

### Q: 推荐结果为空？

确保数据库中有**至少两个不同学科**的论文。初始化示例数据已覆盖 3 个学科，可以直接测试。

### Q: 如何重置所有数据？

删除 `instance/innocite.db`，重新运行 `python init_db.py`。

### Q: PDF 中文显示为方块？

将中文字体文件（`SimHei.ttf`、`msyh.ttc` 等）放入 `data/` 目录，重启应用。

### Q: GROBID 如何启动？

```bash
docker run -d -p 8070:8070 lfoppiano/grobid:0.8.1
```

不启动 GROBID 也不影响使用，系统会自动回退到 pdfplumber 本地解析。

### Q: 忘记管理员密码怎么办？

删除 `instance/innocite.db`，重新运行 `python init_db.py` 重建数据库（会丢失已有数据）。

### Q: 如何修改自动提取的创新点？

论文列表页或详情页点击编辑按钮，修改保存即可。手动编辑的创新点不会被自动提取覆盖。

### Q: SBERT 模型文件放在哪里？

默认缓存路径：
- Windows: `C:\Users\<用户名>\.cache\huggingface\hub\models--sentence-transformers--all-MiniLM-L6-v2\`
- macOS: `~/.cache/huggingface/hub/models--sentence-transformers--all-MiniLM-L6-v2/`
- Linux: `~/.cache/huggingface/hub/models--sentence-transformers--all-MiniLM-L6-v2/`

如果需要在无网络环境下部署，可以先在联网机器上下载好，然后把整个 `models--sentence-transformers--all-MiniLM-L6-v2` 目录复制到目标机器的对应路径。
