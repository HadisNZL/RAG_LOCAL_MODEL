# Local Code RAG

本地 Code-RAG 完整部署操作文档（Mac 环境）

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
