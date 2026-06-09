from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import chunk_api, extract_api, graph_api, pipeline_api, upload_api


app = FastAPI(
    title="KG Extraction Backend",
    description="接收前端上传的 PDF，提取文本并保存为 TXT 文件",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_api.router)
app.include_router(extract_api.router)
app.include_router(chunk_api.router)
app.include_router(graph_api.router)
app.include_router(pipeline_api.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/api/health")
def api_health_check():
    return {"success": True, "message": "Backend is running"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
