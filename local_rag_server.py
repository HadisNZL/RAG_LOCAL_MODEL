import os
import time
import json
import asyncio
import re
import chromadb
from chromadb.utils.embedding_functions import OllamaEmbeddingFunction
import ollama
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager

# ====================== 可自定义配置区 ======================
PROJECT_PATH = "/Users/niuzilin/VSCodeProjects/LocalModel/"
SUFFIX_WHITE_LIST = (".kt", ".go", ".gradle", ".md", ".java", ".xml", ".properties")
SKIP_DIRS = {"build", ".git", "node_modules", ".idea", "dist", "out"}
OLLAMA_URL = "http://127.0.0.1:11434"
LLM_MODEL = "deepseek-coder:6.7b-instruct-q4_K_M"
EMBED_MODEL = "nomic-embed-text"
TOP_K = 3                 
CHUNK_SIZE = 800          
CHROMA_STORE = "./chroma_code_db"
SERVER_PORT = 11435
BATCH_SIZE = 64           
EMBED_TIMEOUT = 180
# ==========================================================

chroma_client = None
code_collection = None

def get_collection(clean_exist=False):
    global chroma_client, code_collection
    if chroma_client is None:
        chroma_client = chromadb.PersistentClient(path=CHROMA_STORE)
    embed_func = OllamaEmbeddingFunction(model_name=EMBED_MODEL, url=OLLAMA_URL, timeout=EMBED_TIMEOUT)
    if clean_exist:
        try:
            chroma_client.delete_collection(name="code_store")
            print("🧹 已成功清理历史向量数据库...")
        except Exception:
            pass
    code_collection = chroma_client.get_or_create_collection(name="code_store", embedding_function=embed_func)
    return code_collection

def has_valid_chroma_db(db_path: str) -> bool:
    if not os.path.isdir(db_path):
        return False
    return os.path.isfile(os.path.join(db_path, "chroma.sqlite3"))

def scan_project_and_index():
    collection = get_collection(clean_exist=True)
    document_list = []
    meta_list = []
    id_list = []
    seq_id = 0

    if not os.path.isdir(PROJECT_PATH):
        print(f"❌ 错误：项目路径不存在 {PROJECT_PATH}")
        return

    print(f"🔍 开始扫描项目目录: {PROJECT_PATH} ...")
    for root, dirs, files in os.walk(PROJECT_PATH):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for filename in files:
            if not filename.endswith(SUFFIX_WHITE_LIST):
                continue
            full_file_path = os.path.join(root, filename)
            try:
                try:
                    with open(full_file_path, "r", encoding="utf-8") as f:
                        content = f.read().strip()
                except UnicodeDecodeError:
                    with open(full_file_path, "r", encoding="gbk") as f:
                        content = f.read().strip()
                if not content:
                    continue
                
                chunks = [content[i:i+CHUNK_SIZE] for i in range(0, len(content), CHUNK_SIZE)]
                for chunk_text in chunks:
                    if not chunk_text.strip():
                        continue
                    enhanced_text = f"// File: {filename}\n{chunk_text}"
                    document_list.append(enhanced_text)
                    meta_list.append({"file": full_file_path, "filename": filename})
                    id_list.append(f"chunk_{seq_id}")
                    seq_id += 1
            except Exception as e:
                print(f"⚠️ 读取失败 {full_file_path} : {str(e)}")

    total = len(document_list)
    if total == 0:
        print("⚠️ 没有读取到任何可索引的代码文件。")
        return

    print(f"🚀 开始向 Chroma 录入 {total} 个分片 (Batch Size: {BATCH_SIZE})...")
    for start in range(0, total, BATCH_SIZE):
        end = start + BATCH_SIZE
        collection.add(
            documents=document_list[start:end],
            metadatas=meta_list[start:end],
            ids=id_list[start:end]
        )
        print(f"📊 已录入分片: {min(end, total)}/{total}")
    print(f"✅ 索引处理完毕，总计成功处理 {total} 个代码分片")

def get_target_filename_from_history(messages: list) -> str:
    """
    🌟 最完美的防污染解析器（严格 ASCII 英文版）
    只扫描用户的发言历史，且彻底屏蔽中文、空格等多余前缀噪音。
    """
    suffix_pattern = "|".join([re.escape(s) for s in SUFFIX_WHITE_LIST])
    # 绝杀改动：将 [\w\-\./] 替换为严格的 [a-zA-Z0-9_\-\./]，彻底无视中文
    file_regex = re.compile(r'([a-zA-Z0-9_\-\./]+(?:' + suffix_pattern + r'))')
    
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            
            if isinstance(content, list):
                texts = [item.get("text", "") for item in content if item.get("type") == "text"]
                content = " ".join(texts)
            elif not isinstance(content, str):
                continue
                
            matches = file_regex.findall(content)
            if matches:
                # 拿到了纯净的 'CommonHelpWebActivity.kt'
                target_filename = os.path.basename(matches[-1])
                print(f"🧬 [纯净意图提取] 从用户历史提问中成功解析到目标文件: '{target_filename}'")
                return target_filename
                
    return ""

def get_related_code_context(user_query: str, target_filename: str) -> str:
    collection = get_collection()
    
    # 🌟 核心修改：如果是明确的目标文件，直接全量提取，拒绝模糊检索
    if target_filename:
        print(f"🎯 [物理提取模式] 尝试从库中全量提取文件: '{target_filename}'")
        try:
            # 使用 get 获取该文件名的所有分片，绕过 n_results 限制
            result = collection.get(where={"filename": target_filename})
            
            if result and result["documents"] and len(result["documents"]) > 0:
                print(f"✅ 成功提取到 '{target_filename}' 的 {len(result['documents'])} 个代码切片")
                output_blocks = []
                for doc_chunk, meta_info in zip(result["documents"], result["metadatas"]):
                    file_path = meta_info["file"]
                    block = f"【文件路径: {file_path}】\n{doc_chunk}\n"
                    output_blocks.append(block)
                return "\n---\n".join(output_blocks)
            else:
                print(f"⚠️ 库中未找到 '{target_filename}'（可能未被索引或名字错误），自动降级为全局语义检索...")
        except Exception as e:
            print(f"⚠️ 提取 '{target_filename}' 时发生错误: {e}，自动降级...")

    # 如果没有目标文件，或者物理提取失败，降级走常规的全局语义检索
    print("🔍 [全局语义模式] 启动跨文件模糊检索...")
    result = collection.query(
        query_texts=[user_query], 
        n_results=TOP_K
    )
    
    if not result or not result["documents"] or not result["documents"][0]:
        print("⚠️ 向量库检索结果完全为空")
        return ""
    
    matched_files = list(set([meta["file"] for meta in result["metadatas"][0]]))
    print(f"🎯 语义检索命中文件列表: {matched_files}")
    
    output_blocks = []
    for doc_chunk, meta_info in zip(result["documents"][0], result["metadatas"][0]):
        file_path = meta_info["file"]
        block = f"【文件路径: {file_path}】\n{doc_chunk}\n"
        output_blocks.append(block)
        
    return "\n---\n".join(output_blocks)

async def response_stream_generator(full_text: str, model_name: str):
    created_time = int(time.time())
    yield f"data: {json.dumps({'id': 'local-rag-code', 'object': 'chat.completion.chunk', 'created': created_time, 'model': model_name, 'choices': [{'index': 0, 'delta': {'role': 'assistant', 'content': ''}, 'finish_reason': None}]})}\n\n"
    
    chunk_size = 30
    for i in range(0, len(full_text), chunk_size):
        text_chunk = full_text[i:i+chunk_size]
        chunk_data = {
            "id": "local-rag-code", "object": "chat.completion.chunk", "created": created_time, "model": model_name,
            "choices": [{"index": 0, "delta": {"content": text_chunk}, "finish_reason": None}]
        }
        yield f"data: {json.dumps(chunk_data)}\n\n"
        await asyncio.sleep(0.005)
        
    end_data = {
        "id": "local-rag-code", "object": "chat.completion.chunk", "created": created_time, "model": model_name,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
    }
    yield f"data: {json.dumps(end_data)}\n\n"
    yield "data: [DONE]\n\n"

@asynccontextmanager
async def lifespan(app: FastAPI):
    need_init = not has_valid_chroma_db(CHROMA_STORE)
    if need_init:
        print("🐳 [Lifespan] 无有效向量库，正在执行首次全量索引...")
        scan_project_and_index()
    else:
        print("🐳 [Lifespan] 检测到已有向量库，直接加载服务")
        get_collection() 
    yield

app = FastAPI(title="Local Code RAG Server", lifespan=lifespan)

class ChatReq(BaseModel):
    model: str
    messages: list[dict]
    temperature: float = 0.01  
    max_tokens: int = 8192

@app.post("/v1/chat/completions")
async def chat_endpoint(req: ChatReq):
    try:
        original_user_content = ""
        user_msg_index = -1
        
        for idx, msg in enumerate(reversed(req.messages)):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, list):
                    texts = [item.get("text", "") for item in content if item.get("type") == "text"]
                    original_user_content = " ".join(texts)
                else:
                    original_user_content = str(content)
                user_msg_index = len(req.messages) - 1 - idx
                break
                
        if not original_user_content or user_msg_index == -1:
            raise HTTPException(status_code=400, detail="未检测到用户提问内容")

        if "所有" in original_user_content or "全部" in original_user_content or "列表" in original_user_content:
            for suffix in SUFFIX_WHITE_LIST:
                if suffix in original_user_content:
                    all_matched_files = []
                    for root, dirs, files in os.walk(PROJECT_PATH):
                        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                        for filename in files:
                            if filename.endswith(suffix):
                                all_matched_files.append(os.path.join(root, filename))
                    
                    if all_matched_files:
                        files_str = "\n".join([f"- `{f}`" for f in all_matched_files])
                        final_reply = f"📊 **【系统直连审计结果】**\n在项目路径下，共扫描到 **{len(all_matched_files)}** 个 `{suffix}` 文件。完整路径列表如下：\n\n{files_str}"
                        return StreamingResponse(response_stream_generator(final_reply, LLM_MODEL), media_type="text/event-stream")

        target_filename = get_target_filename_from_history(req.messages)
        code_context = get_related_code_context(original_user_content, target_filename)

        if not code_context.strip():
            err_reply = f"❌ 未能在向量库中检索到关于代码。请确认该文件已被索引，或执行 curl -X POST http://127.0.0.1:11435/ingest/rebuild 刷新索引。"
            return StreamingResponse(response_stream_generator(err_reply, LLM_MODEL), media_type="text/event-stream")

        wrapped_user_content = f"""你是一个严谨的本地代码辅助专家。

[本地项目参考代码库开始]
{code_context}
[本地项目参考代码库结束]

[硬性应答规范]：
1. 【非常重要】当前我们讨论的核心文件是：{target_filename or '全局项目'}。请完全基于该文件相关的参考代码库来回答最后的用户提问。
2. 代码在哪个文件，提供代码时必须在上方标明文件路径。
3. 严禁自行编写、提供与上方代码片段无关的通用教程或第三方库代码。

[用户的最新提问]：
{original_user_content}"""

        processed_messages = list(req.messages)
        processed_messages[user_msg_index]["content"] = wrapped_user_content

        ollama_resp = ollama.chat(
            model=LLM_MODEL,
            messages=processed_messages,  
            options={"num_ctx": 8192}
        )

        answer_text = ollama_resp["message"]["content"]
        
        return StreamingResponse(
            response_stream_generator(answer_text, LLM_MODEL), 
            media_type="text/event-stream"
        )
        
    except Exception as err:
        raise HTTPException(status_code=500, detail=str(err))

@app.post("/ingest/rebuild")
async def rebuild_index():
    try:
        scan_project_and_index()
        return {"status": "success", "msg": "项目代码索引已成功重建并刷新"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重建索引失败: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=SERVER_PORT)