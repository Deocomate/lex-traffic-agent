"""
Script trích xuất, cắt cúp chuẩn vị trí và tổ chức hệ thống ảnh minh họa từ QCVN 41:2019/BGTVT.
- Quét toàn bộ 211 trang của tài liệu Quy chuẩn Kỹ thuật Quốc gia về Báo hiệu Đường bộ.
- Phân loại 463 hình ảnh vào các thư mục tương ứng theo nhóm báo hiệu.
- Render crop độ phân giải cao (200 DPI) dạng PNG sắc nét, loại bỏ rác/viền thừa.
- Tự động nhận diện mã hiệu (sign_code / marking_code), chú thích hình ảnh (figure_caption)
  qua thuật toán phân tích vị trí không gian (Spatial Proximity Analysis).
- Xuất catalog siêu dữ liệu hoàn chỉnh tại data/processed/illustrations_catalog.json.
"""

import os
import sys
import re
import json
import unicodedata
import fitz
from typing import Any, Dict, List, Optional, Tuple

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_PDF = os.path.join(BASE_DIR, "data", "raw_data", "06_qcvn_41_2019_bgtvt_quy_chuan_bao_hieu_duong_bo.pdf")
IMAGES_BASE = os.path.join(BASE_DIR, "data", "images", "qcvn_41")
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
CATALOG_PATH = os.path.join(PROCESSED_DIR, "illustrations_catalog.json")

# Danh mục thư mục phân loại theo Phụ lục
FOLDER_MAPPING = {
    "bien_bao_cam": os.path.join(IMAGES_BASE, "bien_bao_cam"),
    "bien_nguy_hiem": os.path.join(IMAGES_BASE, "bien_nguy_hiem"),
    "bien_hieu_lenh": os.path.join(IMAGES_BASE, "bien_hieu_lenh"),
    "bien_chi_dan": os.path.join(IMAGES_BASE, "bien_chi_dan"),
    "bien_phu": os.path.join(IMAGES_BASE, "bien_phu"),
    "vach_ke_duong": os.path.join(IMAGES_BASE, "vach_ke_duong"),
    "den_tin_hieu": os.path.join(IMAGES_BASE, "den_tin_hieu"),
    "thiet_bi_dan_huong": os.path.join(IMAGES_BASE, "thiet_bi_dan_huong"),
    "minh_hoa_ky_thuat": os.path.join(IMAGES_BASE, "minh_hoa_ky_thuat"),
}

# Regex tìm mã biển báo và vạch kẻ
RE_SIGN_CODE = re.compile(r'\b((?:DP|IE|SG|SH|SR|IS|P|R|W|I|S)\.\d{3}[a-z]?)\b')
RE_MARKING = re.compile(r'Vạch\s+(\d{1,2}\.\d{1,2}[a-z]?)', re.IGNORECASE)
RE_FIG_CAPTION = re.compile(r'(Hình\s+[A-Z0-9.]+[\s\-–]*[^;\n\r]{0,80})', re.IGNORECASE)
RE_SUB_LETTER = re.compile(r'([a-zđ])\)\s*Biển\s+số\s+((?:DP|IE|SG|SH|SR|IS|P|R|W|I|S)\.\d{3}[a-z]?)', re.IGNORECASE)


def determine_category_and_folder(page_num: int) -> Tuple[str, str, str]:
    """Xác định danh mục, phụ lục và thư mục đích dựa trên số trang (1-indexed)"""
    if 1 <= page_num <= 74:
        return "minh_hoa_ky_thuat", "Thân quy chuẩn (Chương 1-13)", "minh_hoa_ky_thuat"
    elif 75 <= page_num <= 78:
        return "den_tin_hieu", "Phụ lục A - Đèn tín hiệu", "den_tin_hieu"
    elif 79 <= page_num <= 99:
        return "bien_bao_cam", "Phụ lục B - Biển báo cấm", "bien_bao_cam"
    elif 100 <= page_num <= 118:
        return "bien_nguy_hiem", "Phụ lục C - Biển báo nguy hiểm", "bien_nguy_hiem"
    elif 119 <= page_num <= 130:
        return "bien_hieu_lenh", "Phụ lục D - Biển hiệu lệnh", "bien_hieu_lenh"
    elif 131 <= page_num <= 150:
        return "bien_chi_dan", "Phụ lục E - Biển chỉ dẫn", "bien_chi_dan"
    elif 151 <= page_num <= 158:
        return "bien_phu", "Phụ lục F - Biển phụ", "bien_phu"
    elif 159 <= page_num <= 185:
        return "vach_ke_duong", "Phụ lục G - Vạch kẻ đường", "vach_ke_duong"
    elif 186 <= page_num <= 194:
        return "thiet_bi_dan_huong", "Phụ lục H - Đèn và thiết bị dẫn hướng", "thiet_bi_dan_huong"
    else:
        return "minh_hoa_ky_thuat", "Phụ lục I-P - Kích thước & chi tiết kỹ thuật", "minh_hoa_ky_thuat"


def sanitize_filename(name: str) -> str:
    """Tạo tên file an toàn chuẩn ASCII từ mã hiệu hoặc chú thích"""
    name = name.replace("đ", "d").replace("Đ", "D")
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('utf-8')
    s = name.replace(".", "_").replace(" ", "_").replace("-", "_").replace(":", "")
    s = re.sub(r'[^a-zA-Z0-9_]', '', s)
    s = re.sub(r'_+', '_', s).strip('_')
    return s


def extract_all_illustrations():
    print("=" * 80)
    print("TRÍCH XUẤT VÀ CẤU TRÚC HÓA ẢNH MINH HỌA TỪ QCVN 41:2019/BGTVT")
    print("=" * 80)

    # Đảm bảo các thư mục đích tồn tại
    for folder in FOLDER_MAPPING.values():
        os.makedirs(folder, exist_ok=True)
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    if not os.path.exists(RAW_PDF):
        raise FileNotFoundError(f"Không tìm thấy file PDF gốc: {RAW_PDF}")

    doc = fitz.open(RAW_PDF)
    total_pages = len(doc)
    print(f"📄 Mở tài liệu: {os.path.basename(RAW_PDF)} ({total_pages} trang)")

    catalog: List[Dict[str, Any]] = []
    category_counts: Dict[str, int] = {k: 0 for k in FOLDER_MAPPING}
    extracted_total = 0
    skipped_total = 0

    for page_idx in range(total_pages):
        page_num = page_idx + 1
        page = doc[page_idx]
        image_infos = page.get_images()

        if not image_infos:
            continue

        cat_key, appendix_name, folder_name = determine_category_and_folder(page_num)
        target_dir = FOLDER_MAPPING[cat_key]

        # Thu thập các khối văn bản trên trang
        text_blocks = page.get_text("blocks")

        # Thu thập tất cả các rect ảnh hợp lệ trên trang
        valid_img_rects = []
        for img_info in image_infos:
            xref = img_info[0]
            rects = page.get_image_rects(xref)
            if not rects:
                continue
            r = rects[0]
            # Bỏ qua các ảnh quá nhỏ (nhỏ hơn 15x15 points, thường là rác hoặc divider)
            if r.width < 15 or r.height < 15:
                skipped_total += 1
                continue
            valid_img_rects.append((xref, r))

        if not valid_img_rects:
            continue

        # Sắp xếp các ảnh theo thứ tự từ trên xuống dưới, từ trái sang phải
        valid_img_rects.sort(key=lambda x: (round(x[1].y0 / 25) * 25, x[1].x0))

        # Nhóm các ảnh nằm cùng một hàng ngang (y0 gần nhau trong khoảng 30 points)
        rows: List[List[Tuple[int, fitz.Rect]]] = []
        for item in valid_img_rects:
            if not rows:
                rows.append([item])
            else:
                last_row = rows[-1]
                if abs(item[1].y0 - last_row[0][1].y0) <= 35:
                    last_row.append(item)
                else:
                    rows.append([item])

        # Với từng hàng ảnh, tìm kiếm văn bản chú thích tương ứng
        for row in rows:
            # Sắp xếp ảnh trong cùng một hàng từ trái sang phải
            row.sort(key=lambda x: x[1].x0)
            row_y0 = min(r.y0 for _, r in row)
            row_y1 = max(r.y1 for _, r in row)

            # Tìm các khối văn bản ngay bên dưới hàng ảnh (trong khoảng 100 points) hoặc bên trên
            below_blocks = [
                b for b in text_blocks
                if row_y1 - 5 <= b[1] <= row_y1 + 100 and b[4].strip()
            ]
            below_blocks.sort(key=lambda b: b[1])

            above_blocks = [
                b for b in text_blocks
                if row_y0 - 60 <= b[3] <= row_y0 + 5 and b[4].strip()
            ]
            above_blocks.sort(key=lambda b: -b[3])

            surrounding_text = " ".join(b[4].strip() for b in below_blocks + above_blocks)

            # Tìm các mã hiệu biển báo trong phạm vi hàng ảnh
            codes_found = RE_SIGN_CODE.findall(surrounding_text)
            markings_found = RE_MARKING.findall(surrounding_text)
            fig_match = RE_FIG_CAPTION.search(surrounding_text)
            fig_caption = fig_match.group(1).strip() if fig_match else ""

            # Tìm các sub-letter nếu có (ví dụ a) Biển số P.103a, b) Biển số P.103b)
            sub_letters = RE_SUB_LETTER.findall(surrounding_text)
            sub_letter_map = {letter.lower(): code for letter, code in sub_letters}

            for col_idx, (xref, rect) in enumerate(row):
                extracted_total += 1
                assigned_code = None
                assigned_name = ""

                # Chiến lược gán nhãn định danh:
                # 1. Nếu có sub_letters và số ảnh khớp số sub_letters
                if len(sub_letters) == len(row):
                    assigned_code = sub_letters[col_idx][1]
                # 2. Nếu có markings_found (Phụ lục G vạch kẻ đường)
                elif markings_found and col_idx < len(markings_found):
                    assigned_code = f"Vạch {markings_found[col_idx]}"
                # 3. Nếu có codes_found
                elif codes_found and col_idx < len(codes_found):
                    assigned_code = codes_found[col_idx]
                elif codes_found:
                    assigned_code = codes_found[0]
                elif fig_caption:
                    assigned_code = fig_caption.split("-")[0].strip()

                # Tên file xuất ra
                if assigned_code:
                    base_name = sanitize_filename(assigned_code)
                    if len(row) > 1 and not any(base_name.endswith(c) for c in "abcdefgh"):
                        base_name = f"{base_name}_{chr(97 + col_idx)}"
                elif fig_caption:
                    base_name = sanitize_filename(fig_caption[:30])
                else:
                    base_name = f"page_{page_num:03d}_img_{extracted_total:03d}"

                filename = f"{base_name}.png"
                out_path = os.path.join(target_dir, filename)

                # Nếu bị trùng tên, thêm hậu tố index
                dup_counter = 1
                while os.path.exists(out_path):
                    filename = f"{base_name}_{dup_counter}.png"
                    out_path = os.path.join(target_dir, filename)
                    dup_counter += 1

                # Render crop vùng ảnh ở 200 DPI
                # Thêm padding nhẹ 2 points xung quanh rect để không bị mất viền
                crop_rect = fitz.Rect(
                    max(0, rect.x0 - 2),
                    max(0, rect.y0 - 2),
                    min(page.rect.width, rect.x1 + 2),
                    min(page.rect.height, rect.y1 + 2)
                )

                pix = page.get_pixmap(clip=crop_rect, dpi=200)
                pix.save(out_path)

                rel_path = os.path.relpath(out_path, BASE_DIR).replace("\\", "/")

                catalog_entry = {
                    "id": f"qcvn_41_img_{page_num:03d}_{extracted_total:03d}",
                    "sign_code": assigned_code if assigned_code and not assigned_code.startswith("Hình") else None,
                    "figure_caption": fig_caption or None,
                    "category": cat_key,
                    "appendix": appendix_name,
                    "page_number": page_num,
                    "bbox": [round(rect.x0, 2), round(rect.y0, 2), round(rect.x1, 2), round(rect.y1, 2)],
                    "width": pix.width,
                    "height": pix.height,
                    "image_path": rel_path
                }
                catalog.append(catalog_entry)
                category_counts[cat_key] += 1

        if (page_num % 25 == 0) or page_num == total_pages:
            print(f"   ▶ Tiến độ: Trang {page_num}/{total_pages} | Đã trích xuất: {extracted_total} ảnh")

    # Lưu catalog vào file JSON
    with open(CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)

    doc.close()

    print("\n" + "=" * 80)
    print("HOÀN TẤT TRÍCH XUẤT ẢNH MINH HỌA")
    print("=" * 80)
    print(f"✅ Tổng số ảnh đã trích xuất: {extracted_total} ảnh (Bỏ qua {skipped_total} ảnh nhỏ/rác)")
    print(f"📁 Catalog siêu dữ liệu đã lưu tại: {CATALOG_PATH}")
    print("\n📊 Phân bố theo từng nhóm báo hiệu đường bộ:")
    for cat, count in category_counts.items():
        print(f"   - {cat:<22}: {count:>3} ảnh -> data/images/qcvn_41/{cat}/")

    return catalog


if __name__ == "__main__":
    extract_all_illustrations()
