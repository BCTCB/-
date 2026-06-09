# 知识图谱抽取应用

这是一个从 PDF 文档生成知识图谱的 Demo 项目。用户在前端上传 PDF，选择默认抽取或自定义抽取规则后，后端会完成文本提取、文本切分、实体关系抽取、图谱清洗、语义合并、质量报告和最终图谱生成，前端会实时显示项目进度并渲染知识图谱。

## 项目结构

```text
project/
├── backend/              # FastAPI 后端服务
│   ├── api/              # 接口路由
│   ├── services/         # PDF、切分、抽取、清洗、合并等业务流程
│   ├── prompts/          # LLM 提示词
│   ├── schemas/          # 请求和响应模型
│   ├── data/             # 上传文件和各阶段生成结果
│   └── docs/             # API 文档
├── frontend/             # 无构建工具的静态前端
│   ├── index.html        # 页面入口
│   └── assets/           # CSS 和 JS 资源
└── README.md             # 项目总说明
```

## 环境要求

- Python 3.10 或更高版本
- 可用的 DeepSeek API Key
- 现代浏览器

后端依赖见 `backend/requirements.txt`，主要包括 FastAPI、Uvicorn、PyMuPDF、OpenAI SDK 和 python-dotenv。

## 后端启动

进入后端目录并安装依赖：

```bash
cd backend
pip install -r requirements.txt
```

在 `backend/.env` 中配置模型调用参数：

```bash
DEEPSEEK_API_KEY=你的_API_Key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

启动服务：

```bash
uvicorn main:app --reload
```

默认后端地址是：

```text
http://127.0.0.1:8000
```

## 前端启动

前端不需要安装依赖或构建，可以直接打开：

```text
frontend/index.html
```

也可以在 `frontend/` 目录下使用任意静态文件服务访问。前端默认请求 `http://127.0.0.1:8000`，配置位置在 `frontend/assets/js/config.js`。

## 使用流程

1. 启动后端服务。
2. 打开前端页面。
3. 选择本地 PDF 文件。
4. 选择抽取模式：
   - 默认抽取：系统自动识别实体和关系。
   - 自定义抽取：手动配置抽取对象和关系规则。
5. 点击“一键生成知识图谱”。
6. 页面会显示总进度条和当前步骤说明，并在完成后渲染图谱。

## 处理流程

一键生成会按以下阶段执行：

1. PDF 文本提取
2. 文本切分策略分析与切分
3. 实体和关系抽取
4. 重复实体和关系清理
5. 语义相近节点合并
6. 关系清洗
7. 图谱质量报告生成
8. 最终知识图谱生成

各阶段结果会保存在 `backend/data/` 下的对应目录中，例如：

- `uploads/`：上传的 PDF
- `extracted_text/`：提取后的文本
- `chunks/`：文本切分结果
- `raw_graphs/`：原始图谱
- `cleaned_graphs/`：去重清洗后的图谱
- `merged_graphs/`：节点合并后的图谱
- `relation_cleaned_graphs/`：关系清洗后的图谱
- `graph_quality_reports/`：质量报告
- `final_graphs/`：最终图谱

## 常用接口

- `GET /api/health`：检查后端服务是否运行
- `POST /api/pdf/to-txt`：上传 PDF 并提取文本
- `POST /api/chunk/run`：分析切分策略并执行文本切分
- `POST /api/graph/extract`：抽取实体和关系
- `POST /api/graph/clean`：清理重复图谱内容
- `POST /api/graph/merge`：合并语义相近节点
- `POST /api/graph/relations/clean`：清洗关系
- `POST /api/graph/quality/report`：生成图谱质量报告
- `POST /api/graph/final/generate`：生成最终知识图谱
- `POST /api/pipeline/pdf-to-graph`：后端一键完整流程接口

更完整的接口说明可以查看 `backend/docs/API.md` 或 `backend/docs/openapi.json`。

## 注意事项

- 运行完整抽取流程需要配置 `DEEPSEEK_API_KEY`。
- 前端的一键生成会逐阶段调用后端接口，用于实时更新进度条和当前步骤。
- 如果后端端口或地址发生变化，需要同步修改 `frontend/assets/js/config.js` 中的 `API_BASE_URL`。
- `backend/data/` 中保存的是运行产生的数据文件，调试时可以根据 `extraction_id` 追踪每一步输出。
