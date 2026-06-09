# KG Extraction Backend API

- Title: KG Extraction Backend
- Version: 1.0.0
- OpenAPI: 3.1.0

## Swagger UI

启动后端后访问：

- http://127.0.0.1:8000/docs
- http://127.0.0.1:8000/redoc

## Static OpenAPI File

- backend/docs/openapi.json

## Endpoints

- `POST /api/chunk/execute` [chunk] - Api Execute Chunking
- `POST /api/chunk/run` [chunk] - Api Run Strategy And Chunking
- `POST /api/chunk/strategy` [chunk] - Api Create Split Strategy
- `POST /api/extract/run` [extract] - Api Run Graph Extraction
- `POST /api/graph/clean` [graph] - Api Clean Graph
- `POST /api/graph/extract` [graph] - Api Extract Graph
- `POST /api/graph/final/generate` [graph] - Api Final Graph Generate
- `POST /api/graph/merge` [graph] - Api Merge Graph
- `POST /api/graph/quality/report` [graph] - Api Graph Quality Report
- `POST /api/graph/relations/clean` [graph] - Api Clean Graph Relations
- `GET /api/health` - Api Health Check
- `POST /api/pdf/to-txt` [upload] - Api Pdf To Txt
- `POST /api/pipeline/pdf-to-graph` [pipeline] - Api Pdf To Final Graph
- `POST /chunk/execute` [chunk] - Execute Chunking
- `GET /chunk/health` [chunk] - Chunk Health
- `POST /chunk/run` [chunk] - Run Strategy And Chunking
- `POST /chunk/strategy` [chunk] - Create Split Strategy
- `GET /extract/health` [extract] - Extract Health
- `POST /extract/run` [extract] - Run Graph Extraction
- `POST /graph/clean` [graph] - Clean Graph
- `POST /graph/extract` [graph] - Extract Graph
- `POST /graph/final/generate` [graph] - Final Graph Generate
- `GET /graph/health` [graph] - Graph Health
- `POST /graph/merge` [graph] - Merge Graph
- `POST /graph/quality/report` [graph] - Graph Quality Report
- `POST /graph/relations/clean` [graph] - Clean Graph Relations
- `GET /health` - Health Check
- `GET /pipeline/health` [pipeline] - Pipeline Health
- `POST /pipeline/pdf-to-graph` [pipeline] - Pdf To Final Graph
- `GET /upload/health` [upload] - Upload Health
- `POST /upload/pdf/to-txt` [upload] - Upload Pdf To Txt
