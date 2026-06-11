# Local Code RAG

本地 Code-RAG 完整部署操作文档（Mac 环境）

## 📚 相关文档
- [工作原理详解](工作原理.md) - 了解 RAG 系统的完整工作流程和技术细节

## 一、环境准备：创建独立虚拟环境 rag-env

### 1. 打开终端，进入项目目录
```bash
cd /Users/niuzilin/VSCodeProjects/LocalModel
```

### 2. 创建 Python 虚拟环境
```bash
# python3 确保系统有3.9~3.11版本
python3 -m venv rag-env
```

### 3. 激活虚拟环境
```bash
source rag-env/bin/activate
```

### 4. 一键安装全部依赖包
```bash
pip install chromadb ollama fastapi uvicorn
```

## 二、前置 Ollama 准备（必须提前运行）

1. 打开 Ollama 客户端软件，保持后台运行
2. 拉取嵌入模型 + 代码大模型

```bash
# 嵌入向量模型
ollama pull nomic-embed-text

# 代码主模型（当前6.7b量化）
ollama pull deepseek-coder:6.7b-instruct-q4_K_M
```

## 三、创建服务主文件

在项目目录下创建 `local_rag_server.py` 文件，完整代码参考项目中的 [local_rag_server.py](local_rag_server.py) 文件。

## 四、首次启动初始化流程

### 1. 彻底清空旧损坏向量库（第一次全新部署必执行）
```bash
rm -rf chroma_code_db
```

### 2. 启动服务
```bash
python local_rag_server.py
```

**运行逻辑：**
- 无 `chroma.sqlite3` → 自动执行 `scan_project_and_index()` 批量嵌入所有代码分片
- 等待控制台打印 `✅ 索引处理完毕，总计 xxx 个代码分片` 才算初始化完成
- 后续再次启动不会重复扫描，秒启动服务

## 五、curl 测试命令

新开一个终端窗口执行以下命令：

### 1. 标准问答测试（定向询问 ChooseDeviceTypeActivity 优化）
```bash
curl -X POST http://127.0.0.1:11435/v1/chat/completions \
-H "Content-Type: application/json" \
-d '{
  "model":"deepseek-coder:6.7b-instruct-q4_K_M",
  "messages": [{"role":"user","content":"针对ChooseDeviceTypeActivity.kt里的代码，给出可落地的优化改进点"}]
}'
```

**完整启动与测试日志示例：**
```
# niuzilin @ zhanbuzhedeMacBook-Pro in ~/VSCodeProjects/LoaclModel rag-env [9:48:53]
$ python3 local_rag_server.py
INFO:     Started server process [57586]
INFO:     Waiting for application startup.
🐳 [Lifespan] 无有效向量库，正在执行首次全量索引...
🔍 开始扫描项目目录: /Users/niuzilin/VSCodeProjects/LocalModel/ ...
🚀 开始向 Chroma 录入 96 个分片 (Batch Size: 64)...
📊 已录入分片: 64/96
📊 已录入分片: 96/96
✅ 索引处理完毕，总计成功处理 96 个代码分片
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:11435 (Press CTRL+C to quit)
🧬 [纯净意图提取] 从用户历史提问中成功解析到目标文件: 'CommonHelpWebActivity.kt'
🎯 [物理提取模式] 尝试从库中全量提取文件: 'CommonHelpWebActivity.kt'
✅ 成功提取到 'CommonHelpWebActivity.kt' 的 3 个代码切片
INFO:     127.0.0.1:64665 - "POST /v1/chat/completions HTTP/1.1" 200 OK
INFO:     127.0.0.1:64737 - "POST /v1/chat/completions HTTP/1.1" 200 OK
```

### 2. 代码大量修改后，手动刷新向量索引
```bash
curl http://127.0.0.1:11435/ingest/rebuild
```

## 六、VSCode Continue 插件对接配置

1. 打开 Continue 设置 → Models → OpenAI Compatible
2. 配置项：
   - **API Base URL**：`http://127.0.0.1:11435/v1`
   - **Model Name**：`deepseek-coder:6.7b-instruct-q4_K_M`
   - **API Key**：随便填一串字符（本地服务不需要鉴权，占位即可）

## 七、常见问题与优化方案

### 问题 1：模型依旧无视上下文、输出外部教程

**临时方案：** 保持代码内 `temperature=0`、自带路径校验重试逻辑

**根治方案：** 升级更大指令跟随模型
```bash
ollama pull deepseek-coder:13b-instruct-q4_K_M
```
修改代码配置 `LLM_MODEL = "deepseek-coder:13b-instruct-q4_K_M"`

### 问题 2：嵌入批量报错、超时

调大 `EMBED_TIMEOUT=240`，缩小 `BATCH_SIZE=5` 降低单次压力

### 问题 3：想完全重置整个向量库
```bash
# 删除整个库文件夹
rm -rf chroma_code_db

# 重启服务自动全量重建
python local_rag_server.py
```

## 八、日常启停规范

### 关闭服务
运行服务的终端按 `Ctrl + C`

### 日常启动（已有向量库）
```bash
source rag-env/bin/activate
python local_rag_server.py
```

### 退出虚拟环境
```bash
deactivate
```

## 项目结构

```
LocalModel/
├── README.md                # 项目文档
├── local_rag_server.py      # RAG 服务主程序
├── chroma_code_db/          # 向量数据库（自动生成）
├── rag-env/                 # Python 虚拟环境（自动生成）
└── SourceCode/              # 源代码目录（索引目标）
```

## 技术栈

- **向量数据库**: ChromaDB
- **嵌入模型**: nomic-embed-text
- **LLM 模型**: deepseek-coder:6.7b-instruct-q4_K_M
- **Web 框架**: FastAPI + Uvicorn
- **模型运行时**: Ollama

## 方案对比：为什么选择自研本地 RAG？

| 对比维度 | Claude Code / Cursor（闭源商业） | Tabby/Continue（成品开源 AI 工具） | 你手写 local_rag_server.py |
|---------|----------------------------------|-----------------------------------|---------------------------|
| **代码数据流向** | 默认云端上传，不安全 | 100% 本地离线，不上网 | 100% 本地离线 |
| **RAG 核心能力** | 向量 + AST 语法 + 符号索引三重增强 | Tabby 带 AST；Continue 简易 AST；纯向量为主 | 仅纯文本向量相似度匹配 |
| **代码是否开源** | 闭源黑盒，底层不可改 | 完全开源，可 Fork 二次开发 | 代码完全私有，逻辑 100% 自己掌控 |
| **模型自由度** | 只能官方模型；Cursor 本地模式体验阉割 | 自由对接 Ollama 全系列开源模型 | Ollama 任意嵌入 / LLM 模型随意切换 |
| **自定义深度** | 几乎无法自定义规则 | 可改插件 / 程序源码，门槛中等 | 无框架束缚，分片、重试、prompt、校验全代码自定义 |
| **开箱即用程度** | 极高，登录即用 | 高，一键部署插件 / 程序 | 中等，需要配置虚拟环境、Ollama、依赖 |
| **文件编辑 / 重构能力** | 强大，批量改多文件 | 完善，自带 diff、重构、新建文件 | 仅问答分析，无原生文件操作工具 |
| **额外开销** | 持续 token / 订阅付费 | 一次性硬件消耗，永久免费 | 一次性硬件消耗，永久免费 |
| **纠错 / 约束机制** | 内部黑盒逻辑，用户不能干预 | 基础 prompt 模板，无自定义重试校验 | 自研双层路径校验、temperature 锁 0、强制纠正回答 |
| **部署复杂度** | 最低 | 中低 | 中（从零搭建流程） |

### 核心优势
- **绝对隐私**：代码、向量、推理全程本地，零外泄风险
- **完全掌控**：每一行逻辑、每个 prompt、每次重试都可自定义
- **永久免费**：一次配置，终身使用，无订阅费用
- **深度定制**：针对特定项目可调整分片策略、检索逻辑、纠错机制
