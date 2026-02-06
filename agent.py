import os  # 操作系统接口
from langchain.agents import create_agent, AgentState  # LangChain智能体和状态
from langchain.tools import tool  # 工具装饰器
from langchain.chat_models import init_chat_model  # 聊天模型初始化

from langgraph.checkpoint.memory import InMemorySaver  # 内存检查点保存器
from langchain.agents.middleware import before_model  # 模型前中间件
from langgraph.runtime import Runtime  # 运行时管理
from langchain.messages import RemoveMessage  # 消息移除类
from langgraph.graph.message import REMOVE_ALL_MESSAGES  # 移除所有消息常量

from pydantic import BaseModel, Field  # 数据验证和字段定义
import pandas as pd  # 数据处理
import requests  # HTTP请求
import fastapi  # Web框架
from fastapi.responses import StreamingResponse  # 流式响应
from fastapi.middleware.cors import CORSMiddleware  # CORS跨域中间件

import yaml  # YAML配置文件解析
import asyncio  # 异步编程
from typing import Any  # 类型提示

#读取配置文件key
with open("Travel_Multi-Agent/config.yaml", "r") as f:
    config = yaml.safe_load(f)
    print(config)

#初始化大模型
model = init_chat_model(
    model = "glm-4-plus",
    model_provider="openai",            # 仍用 openai provider
    base_url="https://open.bigmodel.cn/api/paas/v4",
    api_key= config["openai_api_key"],# 换成你的智普 key
    temperature=0.0
)

# ====================== 天气相关 ======================
# 城市行政区划代码查询参数模型
class CityAdcode(BaseModel):
    adcode: str = Field(description="行政区划代码")
    type: str = Field(description="查询类型：'base'代表实时天气（现在），'all'代表天气预报（未来3天）", default='base')

# 城市信息输入参数模型  
class InputCityDecode(BaseModel):
    province: str = Field(description="省份名称")
    city: str = Field(description="城市名称")
    district: str = Field(description="区县名称")

#读取数据
data = pd.read_excel('Travel_Multi-Agent/AMap_adcode_citycode.xlsx')

#创建工具-查询城市编码
@tool(args_schema=InputCityDecode)
def query_adcode(province: str, city: str, district: str) -> str:
    """根据省市区名称查询adcode"""
    tar = 0
    if province:
        for i in range(len(data)):
            if data['中文名'][i] == province:
                adcode = data['adcode'][i] 
                tar = i
                break
    if city:
        for i in range(tar, len(data)):
            if data['中文名'][i] == city:
                adcode = data['adcode'][i] 
                tar = i
                break
            if data['中文名'][i].endswith('省'):
                break 
    if district:
        for i in range(tar, len(data)):
            if data['中文名'][i] == district:
                adcode = data['adcode'][i] 
                tar = i
                break
            if data['中文名'][i].endswith('市'):
                break
    if 'adcode' not in locals():
        return ""
    return str(adcode)

#创建工具-获取实时天气
@tool(args_schema=CityAdcode) 
def get_weather(adcode: str, type: str = 'base') -> str:
    """根据adcode获取实时天气"""
    if len(adcode) == 0:
        return f"City with adcode {adcode} not found."

    key = config["gaode_api_key"]
    url = f"https://restapi.amap.com/v3/weather/weatherInfo?city={adcode}&key={key}&extensions={type}&output=JSON"

    response = requests.get(url)
    weather_data = response.json()
    return weather_data

# ====================== POI查询相关 ======================
class POIRequest(BaseModel):
    keywords: str

@tool(args_schema=POIRequest)
def get_poi(keywords: str) -> str:
    """Get point of interest (POI) information."""
    # key = os.getenv("GAODE_API_KEY")
    key = config["gaode_api_key"]
    url = f"https://restapi.amap.com/v5/place/text?key={key}&keywords={keywords}&show_fields=business"
    response = requests.get(url)
    poi_data = response.json()
    return poi_data

# ====================== 新增：导游智能体工具 ======================
@tool
def cultural_guide(query: str) -> str:
    """
    导游功能：讲解目的地文化、历史、习俗、趣闻。
    基于LLM的丰富知识库，无需外部API。
    """
    # 工具会自动被智能体调用，这里只需定义函数
    # 实际的解释工作由智能体的系统提示词控制
    return "文化历史讲解功能"

# ====================== 中间件 ======================
@before_model
def trim_messages(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
    """修剪消息以适配上下文窗口长度"""
    messages = state["messages"]
    if len(messages) <= 9:
        return None
    
    first_msg = messages[0]
    recent_messages = messages[-9:] if len(messages) % 2 == 0 else messages[-10:]
    new_messages = [first_msg] + recent_messages

    return {
        "messages": [
            RemoveMessage(id=REMOVE_ALL_MESSAGES),
            *new_messages
        ]
    }

# ====================== 创建专业智能体 ======================

# 1. 天气查询智能体
agent_weather = create_agent(
    model = model,
    tools = [query_adcode, get_weather],
    system_prompt="""
    你是一个天气查询代理，负责根据用户的问题获取指定城市的天气信息。

    步骤：
    1. 分析用户查询中的地名，将其标准化为三级行政单位：省、市、区县。
    2. 使用"查询adcode"工具获取adcode。
    3. 判断用户意图：
       - 如果用户问"现在"、"当前"的天气，调用"获取天气"工具时，type参数传 'base'。
       - 如果用户问"明天"、"后天"、"未来几天"的天气，调用"获取天气"工具时，type参数传 'all'。
    4. 使用"获取天气"工具查询。
    5. 将天气信息以清晰、友好的方式反馈给用户。如果是预报，请列出具体的日期和天气情况。
    
    注意：地名必须是标准的三级名称；如果用户只提供部分信息，你需要推断完整的三级结构。始终使用工具，不要直接回答。
    """
)

# 2. 景点查询智能体
agent_travel = create_agent(
    model = model,
    tools = [get_poi],
    system_prompt="""
    你是一个旅游信息查询代理，负责根据用户的问题获取指定地点的POI信息。
    """
)

# 3. 新增：导游智能体（纯LLM，无需API）
agent_guide = create_agent(
    model = model,
    tools = [cultural_guide],  # 使用纯LLM工具
    system_prompt="""
    🎤 你是专业的旅行导游，擅长讲解目的地的文化、历史、习俗和趣闻，回答必须要在50个字以内。
    
    ## 核心能力：
    1. **历史文化讲解**
       - 讲解目的地的历史沿革、重要事件
       - 介绍文化特色、传统习俗
       - 讲述当地的名人故事、传说趣闻
    
    2. **文化体验指导**
       - 推荐地道的文化体验活动
       - 讲解传统节日和庆典的参与方式
       - 介绍当地艺术、音乐、舞蹈等特色

    ## 回答风格：
    - 生动有趣，像现场导游一样讲解
    - 使用适当的emoji和分段，增强可读性
    - 结合具体例子和故事
    - 提供实用的体验建议
    
    ## 示例回答框架：
    🏛️ [目的地] 文化深度游指南
    
    **📜 历史脉络**
    • 重要历史时期和事件
    • 历史文化遗迹的背景故事
    
    **🎭 文化特色**
    • 传统习俗和节庆
    • 饮食文化和特色美食
    

    
    注意：基于你的知识库诚实回答，对于不确定的信息要说明。
    """
)

# ====================== 封装工具 ======================

# 天气代理调用工具
@tool("call_weather_agent", description="调用天气代理以获取天气信息。")
def call_weather_agent(query: str) -> str:
    """辅助函数，用于调用天气智能体"""
    response = agent_weather.invoke(
        {
            "messages": [{"role": "user", "content": query}]
        }
    )
    return response['messages'][-1].content

# 旅游代理调用工具
@tool("call_travel_agent", description="调用旅游代理以获取POI信息。")
def call_travel_agent(query: str) -> str:
    """辅助函数：调用旅游智能体"""
    response = agent_travel.invoke(
        {
            "messages": [{"role": "user", "content": query}]
        }
    )
    return response['messages'][-1].content

# 新增：导游代理调用工具
@tool("call_guide_agent", description="调用导游代理以获取文化历史讲解。")
def call_guide_agent(query: str) -> str:
    """辅助函数：调用导游智能体"""
    response = agent_guide.invoke(
        {
            "messages": [{"role": "user", "content": query}]
        }
    )
    return response['messages'][-1].content

# ====================== 创建主管智能体 ======================
agent_supervisor = create_agent(
    model = model,
    tools = [call_weather_agent, call_travel_agent, call_guide_agent],  # 新增导游工具
    middleware=[trim_messages],
    checkpointer=InMemorySaver(), 
    debug=True,
    system_prompt="""  
    🧭 你是全能旅行助手，能同时处理多种旅行需求,要求回答控制在100字以内：
    
    ## 可用的专业代理：
    1. 🌤️ 天气代理 - 查询实时天气和预报
    2. 🏛️ 景点代理 - 查询景点和POI信息  
    3. 🎤 导游代理 - 讲解文化、历史、习俗（纯知识，无需API）
    
    ## 处理流程：
    1. 分析用户问题，识别需求类型
    2. 智能选择合适的代理：
       - 天气相关 → 调用天气代理
       - 景点查询 → 调用景点代理
       - 文化/历史/习俗 → 调用导游代理
       - 综合需求 → 按需调用多个代理
    
    3. 组合结果，提供全面回答
    
    ## 示例场景：
    Q: "北京天气怎么样？"
    → 调用天气代理
    
    Q: "北京有什么景点？"
    → 调用景点代理
    
    Q: "介绍一下北京的历史文化"
    → 调用导游代理
    
    Q: "我要去北京旅游，需要天气、景点和文化介绍"
    → 1. 调用天气代理：获取天气
       2. 调用景点代理：获取景点
       3. 调用导游代理：获取文化讲解
       4. 组合所有信息
    
    ## 回答要求：
    - 结构清晰，使用适当emoji和分段
    - 不同部分之间有明显区分
    - 保持友好、专业的导游风格
    - 对于需要实时数据的问题，诚实地告知局限性

    4. 如果某个代理失败，继续下一个，不要阻塞.
    """
)

# ====================== FastAPI应用 ======================
app = fastapi.FastAPI()

# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"], 
)

# SSE格式转换
def to_sse_chunk(text: str) -> str:
    return "data: " + text.replace("\n", "\ndata: ") + "\n\n"

# 旅游助手API（增强版）
@app.get("/travel_assistant")
async def travel_assistant(userid: str, channel_id: str, query: str):
    """全能旅行助手API - 支持天气、景点、文化讲解"""
    if not query:
        return fastapi.responses.JSONResponse(
            {"error": "Query parameter is required"},
            status_code=400
        )
    
    async def event_generator(user_query: str):
        """生成SSE格式响应的事件流"""
        try:
            for token, metadata in agent_supervisor.stream(  
                {"messages": [{"role": "user", "content": user_query}]},
                {"configurable": {"thread_id": userid + channel_id}},
                stream_mode="messages",
            ):
                if metadata['langgraph_node'] == 'model':
                    if hasattr(token, 'content_blocks') and len(token.content_blocks) >= 1 and token.content_blocks[0]['type'] == 'text':
                        text = token.content_blocks[0]['text']
                        yield to_sse_chunk(text)
                    elif isinstance(token.content, str):
                        yield to_sse_chunk(token.content)
        except Exception as e:
            yield f"data: 错误: {str(e)}\n\n"
    
    return StreamingResponse(event_generator(query), media_type="text/event-stream")


# 测试流式接口
async def generate_data():
    for i in range(10):
        yield f"Chunk {i}\n"
        await asyncio.sleep(1)


# 主程序入口
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)