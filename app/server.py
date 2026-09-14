r"""
Lớp ỨNG DỤNG: máy chủ web của trợ lý giao thông (FastAPI + SSE).

Vì sao nằm ngoài `src/`: đây không phải engine mà là một ứng dụng dựng TRÊN engine, cho đúng
miền giao thông. Nó phục vụ các trang chuyên biệt — tra mức phạt, biển báo, ma trận tốc độ,
6 bộ văn bản — nên nó ĐƯỢC PHÉP phụ thuộc vào `domains/vietnam_traffic/`.

Chiều phụ thuộc của cả dự án:

    app/  ->  domains/<miền>/  ->  src/   (engine, không biết gì về miền)
       \_______________________^

Engine không bao giờ import ngược lên `domains/` hay `app/`; nó chỉ nạp hàm của miền qua chuỗi
'module:hàm' khai báo trong `domain.yaml`.
"""

import os
import sys
import json
import traceback
from typing import List, Optional

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from src.paths import project_root

BASE_DIR = project_root()
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.agent import astream_agent, get_agent, LegalAgent
from domains.vietnam_traffic.lib.tool_contract import PENALTY_DECREE_NAME
from domains.vietnam_traffic.lib.document_provider import get_document_provider
from domains.vietnam_traffic.lib.penalty_lookup import PenaltyLookup

app = FastAPI(title="LexTraffic AI - Legal & Traffic Intelligence Platform API")

@app.middleware("http")
async def add_no_cache_header(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# Jinja2 Templates engine
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Khởi tạo lười (lazy) cho các tài nguyên độc lập
_penalties_lookup: Optional[PenaltyLookup] = None


def get_penalties_lookup() -> PenaltyLookup:
    """Tải trực tiếp PenaltyLookup độc lập, không phụ thuộc vào Agent tools_handler."""
    global _penalties_lookup
    if _penalties_lookup is None:
        _penalties_lookup = PenaltyLookup(BASE_DIR)
    return _penalties_lookup



class ChatMessage(BaseModel):
    role: str
    content: str


class AskRequest(BaseModel):
    question: str
    history: List[ChatMessage] = []
    # Định danh cuộc hội thoại cho checkpointer. Thiếu thì server tự sinh và trả về trong
    # sự kiện `done`, nên client cũ không gửi trường này vẫn chạy đúng như trước.
    thread_id: Optional[str] = None


def _sse(payload: dict) -> str:
    """Đóng gói một sự kiện theo chuẩn Server-Sent Events"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# =====================================================================
# 1. Giao Diện Web Chuẩn Jinja2 Templates
# =====================================================================

@app.get("/")
def index(request: Request):
    """Render trang chủ LexTraffic AI bằng Jinja2 Templates"""
    provider = get_document_provider()
    docs = provider.list_documents()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "documents": docs,
            "total_documents": len(docs),
            "app_version": "2024.12.5",
            "active_tab": "chat"
        }
    )


# =====================================================================
# 2. AI Agent Chat Stream (Server-Sent Events)
# =====================================================================

@app.post("/api/ask")
async def ask(req: AskRequest):
    """Chạy AI Agent và stream toàn bộ tiến trình tra cứu về trình duyệt"""
    question = (req.question or "").strip()
    if not question:
        return JSONResponse({"error": "Câu hỏi trống."}, status_code=400)

    history = [m.model_dump() for m in req.history]
    thread_id = (req.thread_id or "").strip()

    async def event_stream():
        try:
            async for evt in astream_agent(question, history=history, thread_id=thread_id):
                yield _sse(evt)
        except Exception as e:
            # Ngoại lệ giữa luồng làm đứt SSE mà không có sự kiện kết thúc nào, nên
            # trình duyệt treo spinner vĩnh viễn. Luôn phát ra một kết cục để giao
            # diện chốt được trạng thái, và in stack trace để còn lần ra nguyên nhân.
            traceback.print_exc()
            yield _sse({"event": "error", "message": f"Lỗi trong quá trình tra cứu: {e}"})
            yield _sse({
                "event": "done",
                "answer": "",
                "agent_steps": [],
                "sources": [],
                "needs_search": False,
                "search": None
            })

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


# =====================================================================
# 3. Tra Cứu 6 Bộ Luật & Văn Bản Pháp Luật
# =====================================================================

@app.get("/api/documents")
def list_documents():
    """Trả về danh sách 6 văn bản pháp luật kèm metadata và thống kê"""
    return {"documents": get_document_provider().list_documents()}


@app.get("/api/documents/{doc_id}/chapters")
def document_chapters(doc_id: str):
    """Cây mục lục các Chương và Điều của một văn bản cụ thể"""
    try:
        return get_document_provider().get_chapters(doc_id)
    except KeyError as e:
        return JSONResponse({"error": str(e)}, status_code=404)


@app.get("/api/documents/{doc_id}/articles/{article_number}")
def document_article(doc_id: str, article_number: int):
    """Toàn văn nội dung một Điều luật cụ thể trong văn bản bất kỳ"""
    try:
        return get_document_provider().get_article(doc_id, article_number)
    except KeyError as e:
        return JSONResponse({"error": str(e)}, status_code=404)


# Endpoints tương thích ngược cho client cũ
@app.get("/api/chapters")
def chapters():
    """Mục lục Luật 36/2024 (tương thích ngược)"""
    return get_document_provider().get_chapters("01_luat_36_2024_qh15")


@app.get("/api/article/{article_number}")
def article(article_number: int):
    """Toàn văn một Điều luật của Luật 36/2024 (tương thích ngược)"""
    try:
        return get_document_provider().get_article("01_luat_36_2024_qh15", article_number)
    except KeyError as e:
        return JSONResponse({"error": str(e)}, status_code=404)


@app.get("/api/search")
def search(q: str, doc_id: Optional[str] = None, limit: int = 15):
    """Tìm kiếm từ khóa trong các Điều luật"""
    query = (q or "").strip()
    if not query:
        return {"query": "", "results": []}
    results = get_document_provider().search_articles(query, doc_id=doc_id, limit=limit)
    return {"query": query, "doc_id": doc_id, "results": results}


# =====================================================================
# 4. Bảng Mức Phạt Nghị Định 168/2024/NĐ-CP
# =====================================================================

@app.get("/api/penalties")
def penalties(vehicle: Optional[str] = None, q: Optional[str] = None, limit: int = 1000):
    """Bảng tra cứu mức phạt dựng từ toàn văn Nghị định 168/2024/NĐ-CP"""
    lookup = get_penalties_lookup()
    rows = lookup.browse(vehicle=vehicle, keyword=q, limit=limit)
    return {
        "doc_name": PENALTY_DECREE_NAME,
        "date_effective": "01/01/2025",
        "total": len(lookup.chunks),
        "returned": len(rows),
        "vehicles": lookup.vehicles(),
        "items": rows
    }


# =====================================================================
# 5. Kho Tiện Ích Giao Thông Chuẩn (Traffic Utilities APIs)
# =====================================================================

@app.get("/api/utilities/signs")
def utility_signs(group: Optional[str] = None, q: Optional[str] = None, limit: int = 400):
    """Danh mục 363 biển báo giao thông chuẩn QCVN 41:2019 kèm ảnh và ý nghĩa"""
    return get_document_provider().get_traffic_signs(group=group, query=q, limit=limit)


@app.get("/api/utilities/speed-matrix")
def utility_speed_matrix():
    """Ma trận tốc độ tối đa cho phép và cự ly an toàn Thông tư 31/2019"""
    return get_document_provider().get_speed_matrix()


@app.get("/api/utilities/license-points")
def utility_license_points():
    """Hệ thống 12 điểm bằng lái, phân nhóm hành vi bị trừ điểm và quy tắc phục hồi"""
    return get_document_provider().get_license_points_data()


@app.get("/api/utilities/road-markings")
def utility_road_markings(q: Optional[str] = None):
    """Danh mục 43 vạch kẻ đường kèm thông số kỹ thuật và ảnh đồ họa QCVN 41"""
    return {"items": get_document_provider().get_road_markings(query=q)}


@app.get("/api/utilities/police-patrol")
def utility_police_patrol():
    """Quy chuẩn tuần tra, kiểm soát và 4 trường hợp dừng xe CSGT theo TT 73/2024"""
    return get_document_provider().get_police_inspection_guide()


# =====================================================================
# 6. Bản Gốc PDF Đa Văn Bản (Searchable PDF)
# =====================================================================

@app.get("/api/pdf")
def pdf(doc: Optional[str] = None):
    """Phục vụ bản PDF gốc có Text Layer của cả 6 văn bản pháp luật"""
    provider = get_document_provider()
    target_path = None
    target_name = "Luat-36-2024-QH15.pdf"

    if doc:
        target_path = provider.get_pdf_path(doc)
        if target_path and os.path.exists(target_path):
            target_name = os.path.basename(target_path)

    # Fallback mặc định
    if not target_path or not os.path.exists(target_path):
        candidates = [
            doc,
            "01_luat_36_2024_qh15_trat_tu_an_toan_giao_thong_searchable.pdf",
            "01_luat_36_2024_qh15_trat_tu_an_toan_giao_thong.pdf",
            "Luật-36-2024-QH15.pdf",
        ]
        for cand in candidates:
            if not cand:
                continue
            p1 = os.path.join(BASE_DIR, "data", "digitized_pdf", cand)
            if os.path.exists(p1):
                target_path = p1
                target_name = cand
                break
            p2 = os.path.join(BASE_DIR, "data", "raw_data", cand)
            if os.path.exists(p2):
                target_path = p2
                target_name = cand
                break

    if not target_path or not os.path.exists(target_path):
        return JSONResponse({"error": f"Không tìm thấy tệp PDF cho: {doc}"}, status_code=404)

    return FileResponse(
        target_path,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{target_name}"'}
    )


# =====================================================================
# 7. Quản Trị Hệ Thống & Kiểm Thử RAG
# =====================================================================

@app.get("/api/benchmark")
def benchmark():
    """Kết quả đo hiệu năng truy xuất RAG trên bộ 35 câu hỏi thực tế"""
    path = os.path.join(BASE_DIR, "data", "benchmark", "evaluation_report.json")
    if not os.path.exists(path):
        return JSONResponse({"error": "Chưa có báo cáo đánh giá. Chạy: python main.py --eval"}, status_code=404)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/trace/summary")
def trace_summary(since: Optional[str] = None):
    """
    Chỉ số quan trắc tổng hợp: độ trễ theo node, chi phí, tỉ lệ trúng cache, phân bố
    tầng structured output, tỉ lệ fallback.

    KHÔNG trả nội dung câu hỏi của người dùng — chỉ con số. Toàn văn câu hỏi chỉ nằm
    trong tệp JSONL cục bộ dưới data/runtime/traces/.
    """
    from scripts.eval.summarize_traces import iter_records, summarize
    from src.observability.tracer import get_trace_dir

    trace_dir = get_trace_dir()
    if not os.path.isabs(trace_dir):
        trace_dir = os.path.join(BASE_DIR, trace_dir)

    summary = summarize(iter_records(trace_dir, since=since))
    if summary["runs"] == 0:
        return JSONResponse(
            {"error": "Chưa có dữ liệu trace. Hãy chạy vài câu hỏi trước."}, status_code=404
        )
    return summary


@app.get("/api/health")
def health():
    """Tình trạng hệ thống: cấu hình model, dữ liệu đã nạp, trạng thái các tệp chỉ mục"""
    try:
        provider = get_document_provider()
        penalties_lookup = get_penalties_lookup()
        model_name = os.getenv("LLM_MODEL", "deepseek/deepseek-chat")
        fb_model = os.getenv("FALLBACK_LLM_MODEL", "deepseek/deepseek-chat")

        processed_dir = os.path.join(BASE_DIR, "data", "processed")
        data_files = {
            "Cây Luật 36/2024 (9 Chương / 89 Điều)": os.path.join(processed_dir, "law_36_2024_structured.json"),
            "Toàn văn 89 Điều Luật 36/2024": os.path.join(processed_dir, "rag_chunks.jsonl"),
            "Cây Luật 35/2024 (6 Chương / 86 Điều)": os.path.join(processed_dir, "02_luat_35_2024_qh15_duong_bo_structured.json"),
            "Toàn văn 86 Điều Luật 35/2024": os.path.join(processed_dir, "luat_35_articles.jsonl"),
            "Cây Nghị định 168/2024 (4 Chương / 55 Điều)": os.path.join(processed_dir, "03_nghi_dinh_168_2024_nd_cp_xu_phat_vi_pham_structured.json"),
            "634 hành vi phạt (Nghị định 168/2024)": penalties_lookup.chunks_path,
            "363 Biển báo đường bộ (QCVN 41:2019)": os.path.join(processed_dir, "traffic_signs_catalog.json"),
            "Ma trận tốc độ & cự ly (Thông tư 31/2019)": os.path.join(processed_dir, "speed_limits_matrix.json"),
            "Chỉ mục ngữ nghĩa hợp nhất (3072 chiều)": os.path.join(processed_dir, "semantic_index.npz"),
        }

        # Thống kê mục lục Luật 36/2024
        law36_tree = provider.get_chapters("01_luat_36_2024_qh15")
        chapters_list = law36_tree.get("chapters", [])
        total_articles = sum(len(c.get("articles", [])) for c in chapters_list)

        return {
            "status": "ok",
            "model": model_name,
            "fallback_model": fb_model,
            "embedding_model": os.getenv("EMBEDDING_MODEL", "google/gemini-embedding-2"),
            "documents_loaded": len(provider.list_documents()),
            "articles_loaded": total_articles or 89,
            "chapters_loaded": len(chapters_list) or 9,
            "penalty_behaviours": len(penalties_lookup.chunks),
            "penalty_source": PENALTY_DECREE_NAME,
            "semantic_chunks": 2114,
            "tools": ["penalty_lookup", "traffic_sign_lookup", "speed_limit_lookup", "semantic_search", "keyword_search", "get_article", "list_chapters"],
            "data_files": [
                {
                    "name": name,
                    "exists": os.path.exists(path),
                    "size_mb": round(os.path.getsize(path) / 1048576, 2) if os.path.exists(path) else 0
                }
                for name, path in data_files.items()
            ]
        }
    except Exception as e:
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=500)


# =====================================================================
# 8. Mount Thư Mục Tĩnh & Hình Ảnh
# =====================================================================

images_dir = os.path.join(BASE_DIR, "data", "images")
if os.path.exists(images_dir):
    app.mount("/data/images", StaticFiles(directory=images_dir), name="data_images")

if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
