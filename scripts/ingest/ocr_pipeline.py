"""
Pipeline OCR chuyên sâu tiếng Việt cho tài liệu pháp luật giao thông.
Sử dụng mô hình Vision (Google Gemini 3.8 Flash qua OpenRouter API) kết hợp caching từng trang.
Đảm bảo độ chính xác 100% về dấu tiếng Việt, bảng biểu, số hiệu và điều khoản.
"""

import os
import sys
import time
import base64
import fitz
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(BASE_DIR, "data", "raw_data")
CACHE_DIR = os.path.join(BASE_DIR, "data", "processed", "ocr_cache")

API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL_NAME = "google/gemini-3.8-flash"

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=API_KEY
)

OCR_SYSTEM_PROMPT = """Bạn là chuyên gia số hóa văn bản quy phạm pháp luật Việt Nam.
Nhiệm vụ của bạn là OCR chính xác 100% toàn bộ văn bản trong hình ảnh trang tài liệu pháp luật này.
YÊU CẦU BẮT BUỘC:
1. Giữ nguyên 100% chữ tiếng Việt có đầy đủ dấu thanh, dấu mũ, số hiệu văn bản, ngày tháng năm.
2. Giữ nguyên cấu trúc văn bản: Tiêu ngữ, Quốc hiệu, Tên văn bản, Chương, Mục, Điều, Khoản (1, 2, 3...), Điểm (a, b, c...), gạch đầu dòng (-).
3. Với bảng biểu (ví dụ: bảng tốc độ, khoảng cách, phân công...), xuất ra định dạng bảng Markdown chuẩn (| ... | ... |).
4. Không tự ý tóm tắt, không suy diễn, không bỏ sót bất kỳ từ ngữ nào, kể cả phần nơi nhận, chữ ký, chức vụ người ký.
5. Chỉ trả về nội dung văn bản OCR được (định dạng Markdown), không thêm lời mở đầu hay kết luận giải thích.
"""


def ocr_single_page(doc_id: str, page_idx: int, page_pix: fitz.Pixmap, max_retries: int = 5) -> str:
    page_cache_dir = os.path.join(CACHE_DIR, doc_id)
    os.makedirs(page_cache_dir, exist_ok=True)
    cache_file = os.path.join(page_cache_dir, f"page_{page_idx + 1:03d}.md")

    # Kiểm tra cache
    if os.path.exists(cache_file):
        with open(cache_file, "r", encoding="utf-8") as f:
            content = f.read()
            if len(content.strip()) > 20:
                return content

    img_bytes = page_pix.tobytes("png")
    img_b64 = base64.b64encode(img_bytes).decode("utf-8")

    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": OCR_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"Hãy OCR trang {page_idx + 1} của tài liệu pháp luật này theo đúng yêu cầu đã giao."
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{img_b64}"}
                            }
                        ]
                    }
                ],
                temperature=0.0
            )
            text = resp.choices[0].message.content or ""
            with open(cache_file, "w", encoding="utf-8") as f:
                f.write(text)
            return text
        except Exception as e:
            wait_time = (attempt + 1) * 3
            print(f"   [Thử {attempt+1}/{max_retries}] Lỗi trang {page_idx+1} ({doc_id}): {e}. Đợi {wait_time}s...")
            time.sleep(wait_time)

    raise RuntimeError(f"Không thể OCR trang {page_idx+1} của {doc_id} sau {max_retries} lần thử")


def ocr_pdf_document(pdf_filename: str, doc_id: str, max_workers: int = 4) -> List[str]:
    pdf_path = os.path.join(RAW_DIR, pdf_filename)
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"Không tìm thấy file: {pdf_path}")

    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    print(f"\n🚀 Bắt đầu OCR tài liệu: {pdf_filename} ({total_pages} trang)")
    print(f"   - Thư mục cache: {os.path.join(CACHE_DIR, doc_id)}")

    page_pixmaps = []
    cached_count = 0

    page_cache_dir = os.path.join(CACHE_DIR, doc_id)
    os.makedirs(page_cache_dir, exist_ok=True)

    for i in range(total_pages):
        cache_file = os.path.join(page_cache_dir, f"page_{i + 1:03d}.md")
        if os.path.exists(cache_file) and os.path.getsize(cache_file) > 30:
            cached_count += 1
        page = doc[i]
        pix = page.get_pixmap(dpi=150)
        page_pixmaps.append((i, pix))

    print(f"   - Đã có cache: {cached_count}/{total_pages} trang. Cần OCR mới: {total_pages - cached_count} trang.")

    results = {}
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_page = {
            executor.submit(ocr_single_page, doc_id, i, pix): i
            for i, pix in page_pixmaps
        }

        completed = 0
        for future in as_completed(future_to_page):
            idx = future_to_page[future]
            try:
                page_text = future.result()
                results[idx] = page_text
                completed += 1
                if completed % 5 == 0 or completed == total_pages:
                    print(f"   ▶ Tiến độ: {completed}/{total_pages} trang ({completed/total_pages*100:.1f}%)")
            except Exception as e:
                print(f"   ❌ Lỗi trang {idx+1}: {e}")
                raise e

    ordered_texts = [results[i] for i in range(total_pages)]
    elapsed = time.time() - t0
    total_chars = sum(len(t) for t in ordered_texts)
    print(f"✅ Hoàn tất OCR {doc_id}: {total_pages} trang, {total_chars:,} ký tự trong {elapsed:.1f}s")

    # Lưu bản toàn văn Markdown
    full_md_path = os.path.join(CACHE_DIR, f"{doc_id}_full.md")
    with open(full_md_path, "w", encoding="utf-8") as f:
        for idx, text in enumerate(ordered_texts):
            f.write(f"\n\n<!-- PAGE {idx + 1} -->\n\n")
            f.write(text)
    print(f"   - Đã ghi bản Markdown toàn văn: {full_md_path}")

    return ordered_texts


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="OCR pipeline cho PDF pháp luật")
    parser.add_argument("--doc", type=str, choices=["01_luat36", "03_nd168", "04_tt31", "05_tt73", "all"], default="03_nd168",
                        help="Tài liệu cần OCR")
    parser.add_argument("--workers", type=int, default=5, help="Số luồng song song")
    args = parser.parse_args()

    docs = {
        "01_luat36": ("01_luat_36_2024_qh15_trat_tu_an_toan_giao_thong.pdf", "01_luat_36_2024_qh15"),
        "03_nd168": ("03_nghi_dinh_168_2024_nd_cp_xu_phat_vi_pham.pdf", "03_nghi_dinh_168_2024_nd_cp"),
        "04_tt31": ("04_thong_tu_31_2019_tt_bgtvt_toc_do_khoang_cach.pdf", "04_thong_tu_31_2019_tt_bgtvt"),
        "05_tt73": ("05_thong_tu_73_2024_tt_bca_tuan_tra_csgt.pdf", "05_thong_tu_73_2024_tt_bca"),
    }

    targets = [args.doc] if args.doc != "all" else ["03_nd168", "04_tt31", "05_tt73", "01_luat36"]
    for t in targets:
        filename, doc_id = docs[t]
        ocr_pdf_document(filename, doc_id, max_workers=args.workers)
