# Multi-Agent - 智能旅游助手
基于LangChain v1.0 构建多智能体旅游助手，集成实时天气查询、智能景点推荐与深度文化讲解等功能，打造一站式智能旅行服务。

##🌟 核心功能
🌤️ 智能天气查询：基于高德地图API的实时天气和3天预报，支持全国行政区划精准定位
🏛️ 景点POI查询：智能景点推荐和详细信息查询，覆盖全国各类旅游点
🎤 文化历史讲解：基于GLM-4大模型的深度文化讲解，无需外部API依赖
🤖 多智能体协作：主管智能体智能路由，专家智能体分工处理
🔌 RESTful API：基于FastAPI的标准HTTP接口，支持前后端分离部署

##🛠️ 技术栈
🧠 大语言模型：智谱AI GLM-4-plus
⚙️ 智能体框架：LangChain V1.0 + LangGraph
🌐 Web框架：FastAPI + HTML/CSS/JavaScript
🗺️ 地理服务：高德地图Web服务API
📊 数据处理：Pandas + YAML
🐍 Python：3.10+

##🚀 快速开始
📦 安装Python库：执行 pip install -r requirements.txt（需 Python 3.10+）
⚡ 运行后端服务：启动 agent.py（FastAPI，端口 8000）
🎨 访问前端界面：打开 index.html 或通过HTTP服务器访问
