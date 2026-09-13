# Domain Pack — dùng hệ thống cho một lĩnh vực khác

Engine trong `src/` không biết gì về giao thông đường bộ. Tất cả phần "biết về miền" nằm trong
`domains/<id>/` dưới dạng khai báo. Tạo một trợ lý cho lĩnh vực mới = viết một thư mục mới,
không sửa dòng code engine nào.

## Chiều phụ thuộc

```
app/  ──>  domains/<miền>/  ──>  src/        (engine, không biết gì về miền)
   └──────────────────────────────^
```

`src/` **không bao giờ** import `domains/` hay `app/`. Nơi engine cần logic riêng của miền, nó
nạp qua chuỗi `'module:hàm'` khai báo trong `domain.yaml`. Không khai báo thì engine dùng bản
mặc định chung, và miền vẫn chạy được.

Có bài test chốt chiều này: `tests/test_domain_pack.py` nạp một pack hoàn toàn khác miền (quy
chế nhân sự, dữ liệu bịa, công cụ riêng) rồi chạy các đường đi chính của engine.

## Cấu trúc một pack

```
domains/<id>/
  domain.yaml        BẮT BUỘC — kho tài liệu, bộ công cụ, policy
  prompts/system.md  BẮT BUỘC — persona và tri thức nền
  lexicon.yaml       nên có — từ lóng, nhóm thực thể, regex nhận diện ý định
  guard.yaml         nên có — lớp số liệu cần kiểm chứng, dấu hiệu trích dẫn
  tools.py           hàm thực thi công cụ
  evidence.py        tuỳ chọn — dựng bằng chứng có cấu trúc cho khối nguồn
  presentation.py    tuỳ chọn — câu chữ mô tả tiến trình tra cứu
  corpus.py          tuỳ chọn — tra cấu trúc kho (mục được trích dẫn có thật không)
  lib/               nghiệp vụ tra cứu riêng của miền
```

Bật bằng `ACTIVE_DOMAIN=<id>` trong `.env`.

## Tối thiểu để chạy

Một pack chỉ cần `domain.yaml` + `prompts/system.md` + một công cụ:

```yaml
id: quy_che_noi_bo
name: Quy chế Nội bộ
language: vi
system_prompt_file: prompts/system.md

corpus:
  documents:
    - id: qc_01
      short_title: Nội quy lao động
      doc_type: noi_quy
      aliases: [noi_quy]

tools:
  - name: policy_search
    description: Tra cứu quy định trong bộ quy chế nội bộ.
    handler: domains.quy_che_noi_bo.tools:policy_search
    parameters:
      type: object
      properties:
        question: {type: string}
      required: [question]
```

Handler trả về **một chuỗi** — đúng nội dung mô hình sẽ đọc. Engine tự lo phần dựng `Evidence`,
phát sự kiện SSE, ghi trace và kiểm chứng.

## Engine giữ cơ chế, pack khai báo lựa chọn

Đây là nguyên tắc chia việc xuyên suốt.

| Engine biết cách làm | Pack quyết định |
|---|---|
| Bóc số tiền tiếng Việt (`6.000.000` / `6 triệu` / `6000000`) | Miền có lớp số liệu nào, ngưỡng bỏ qua bao nhiêu |
| Quét số theo dòng có ngữ cảnh, mang ngữ cảnh qua bảng Markdown | Đơn vị và regex ngữ cảnh là gì |
| Tách token, sinh bigram tiếng Việt | Từ lóng của lĩnh vực, stopword đặc thù |
| Hợp nhất thứ hạng bằng RRF, chọn theo vách rơi | Kho tài liệu nào, nhóm ra sao |
| Vòng ReAct, kiểm chứng, cache, quan trắc | Persona, bộ công cụ, mức rủi ro cache |

Ví dụ `guard.yaml` — miền chọn cơ chế (`kind`) do engine cung cấp:

```yaml
figure_classes:
  - id: money          # cơ chế 'money': mọi cách viết số tiền tiếng Việt
    kind: money
    label: số tiền
    min_value: 1000
  - id: leave_days     # cơ chế 'contextual_count': số + đơn vị, chỉ ở dòng có ngữ cảnh
    kind: contextual_count
    label: ngày nghỉ
    unit: ngày
    context: nghỉ|phép|thai sản
citation_marker: Điều\s*\d|Mục\s*\d|QC-\d
```

## Không có tham số hiệu chuẩn tay

Pack **không** chứa ngưỡng liên quan tới chất lượng truy xuất. Những thứ đó được **đo**:

```bash
# Dựng chỉ mục cho kho tài liệu mới
python scripts/ingest/build_bm25_index.py
python scripts/ingest/build_semantic_index.py

# Đo mốc tham chiếu phạm vi TỪ CHÍNH CORPUS (không gõ tay ngưỡng nào)
python scripts/ingest/calibrate_scope.py

# Chính xác hơn, nếu miền có ví dụ gán nhãn trong/ngoài phạm vi:
python scripts/ingest/calibrate_scope.py --labels <benchmark>.json
```

Có nhãn thì mốc được khớp để tối đa hoá (bắt đúng lạc đề − báo nhầm câu hợp lệ). Không có nhãn
thì lấy phân vị của phân bố điểm trên truy vấn giả sinh từ chính corpus. Cả hai đều tự sinh lại
cho miền mới — không ai phải đoán một con số như `SEMANTIC_FLOOR = 0.58` của bản cũ.

## Các hook tuỳ chọn

Khai báo khi muốn nâng chất lượng; bỏ qua thì engine dùng bản mặc định.

| Khai báo | Nhận | Trả | Mặc định của engine |
|---|---|---|---|
| `tools[].evidence_builder` | `args`, `raw_output` | danh sách `Evidence` | Một Evidence chung từ nguyên văn kết quả |
| `presentation.describe_call` | `tool_name`, `args` | chuỗi | "Tra cứu bằng công cụ `x` với ..." |
| `presentation.summarize_result` | `tool_name`, `raw_output` | chuỗi | "Đã thu thập dữ liệu thành công." |
| `guard.citation_validator` | `answer`, `verified_sources` | danh sách trích dẫn sai | Bỏ qua lớp này |
| `corpus.article_exists` | `doc_id`, `number` | bool | Luôn coi là có thật |

Hai bất biến không được phá:

1. Mọi `Evidence` phải mang `raw_tool_output` là **nguyên văn** kết quả công cụ. Node `verify`
   đối chiếu từng con số trong câu trả lời với đúng trường đó. Đưa bản đã cắt gọn vào sẽ sinh
   ra hàng loạt cảnh báo "số liệu không có căn cứ" giả.
2. Handler trả chuỗi, không ném ngoại lệ ra ngoài. Engine có bắt lỗi, nhưng một công cụ im lặng
   trả rỗng khó lần ra hơn nhiều so với một chuỗi nói rõ đã xảy ra chuyện gì.

## Kiểm tra pack mới

```bash
ACTIVE_DOMAIN=<id> python -m pytest tests/ -q
ACTIVE_DOMAIN=<id> python main.py --web
```

Tham khảo `tests/fixtures/domains/demo_hr/` — pack tối giản đầy đủ chức năng, dùng làm khuôn.
