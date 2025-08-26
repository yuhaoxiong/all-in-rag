import os
import pandas as pd
from llama_index.core import VectorStoreIndex, Document, Settings
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.vector_stores import MetadataFilters, ExactMatchFilter
from llama_index.llms.deepseek import DeepSeek
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

# 配置模型
Settings.llm = DeepSeek(model="deepseek-chat", api_key=os.getenv("DEEPSEEK_API_KEY"))
Settings.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-small-zh-v1.5")

# 1. 加载和预处理数据
excel_file = '../../data/C3/excel/movie.xlsx'
xls = pd.ExcelFile(excel_file)

summary_docs = []
content_docs = []

print("开始加载和处理Excel文件...")
for sheet_name in xls.sheet_names:
    df = pd.read_excel(xls, sheet_name=sheet_name)
    
    # 数据清洗
    if '评分人数' in df.columns:
        df['评分人数'] = df['评分人数'].astype(str).str.replace('人评价', '').str.strip()
        df['评分人数'] = pd.to_numeric(df['评分人数'], errors='coerce').fillna(0).astype(int)

    # 创建摘要文档 (用于路由)
    year = sheet_name.replace('年份_', '')
    summary_text = f"这个表格包含了年份为 {year} 的电影信息，包括电影名称、导演、评分、评分人数等。"
    summary_doc = Document(
        text=summary_text,
        metadata={"sheet_name": sheet_name}
    )
    summary_docs.append(summary_doc)
    
    # 创建内容文档 (用于最终问答)
    content_text = df.to_string(index=False)
    content_doc = Document(
        text=content_text,
        metadata={"sheet_name": sheet_name}
    )
    content_docs.append(content_doc)

print("数据加载和处理完成。\n")

# 2. 构建向量索引
# 使用默认的内存SimpleVectorStore，它支持元数据过滤

# 2.1 为摘要创建索引
summary_index = VectorStoreIndex(summary_docs)

# 2.2 为内容创建索引
content_index = VectorStoreIndex(content_docs)

print("摘要索引和内容索引构建完成。\n")

# 3. 定义两步式查询逻辑
def query_safe_recursive(query_str):
    print(f"--- 开始执行查询 ---")
    print(f"查询: {query_str}")
    
    # 第一步：路由 - 在摘要索引中找到最相关的表格
    print("\n第一步：在摘要索引中进行路由...")
    summary_retriever = VectorIndexRetriever(index=summary_index, similarity_top_k=1)
    retrieved_nodes = summary_retriever.retrieve(query_str)
    
    if not retrieved_nodes:
        return "抱歉，未能找到相关的电影年份信息。"
    
    # 获取匹配到的工作表名称
    matched_sheet_name = retrieved_nodes[0].node.metadata['sheet_name']
    print(f"路由结果：匹配到工作表 -> {matched_sheet_name}")
    
    # 第二步：检索 - 在内容索引中根据工作表名称过滤并检索具体内容
    print("\n第二步：在内容索引中检索具体信息...")
    content_retriever = VectorIndexRetriever(
        index=content_index,
        similarity_top_k=1, # 通常只返回最匹配的整个表格即可
        filters=MetadataFilters(
            filters=[ExactMatchFilter(key="sheet_name", value=matched_sheet_name)]
        )
    )
    
    # 创建查询引擎并执行查询
    query_engine = RetrieverQueryEngine.from_args(content_retriever)
    response = query_engine.query(query_str)
    
    print("--- 查询执行结束 ---\n")
    return response

# 4. 执行查询
query = input()
response = query_safe_recursive(query)

print(f"最终回答: {response}")
