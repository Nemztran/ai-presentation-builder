# AI Presentation Builder

Ứng dụng hackathon demo: upload `.docx`, `.txt`, `.md` → backend đọc nội dung → AI tạo deck JSON → frontend preview slide demo → export file `.pptx` hoàn chỉnh.

## Tính năng chính

- Nhận file `.docx`, `.txt`, `.md`, `.markdown`
- Với `.docx`: đọc paragraph, table và trích xuất hình ảnh trong `word/media`
- Tự động nhận diện và sinh slide theo đúng ngôn ngữ của file gốc (Tiếng Việt/Tiếng Anh)
- Tạo slide demo có layout `title`, `bullet`, `two_column`, `image_text`, `quote`, `closing`
- Preview slide trên React, bao gồm hình ảnh lấy từ file DOCX
- Nhập trực tiếp Google AI Studio API Key từ giao diện web
- Export `.pptx` bằng `python-pptx`
- Có slide transition effects cơ bản: `fade`, `push`, `wipe`
- Có fallback demo nếu chưa cung cấp API Key

> Lưu ý: `python-pptx` không hỗ trợ animation từng object như PowerPoint UI. Bản này thêm slide transition effects vào XML của PPTX. Các hiệu ứng này sẽ hiển thị khi mở bằng Microsoft PowerPoint.

## Chạy backend

```powershell
cd ai-presentation-builder\backend
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000
```

API docs:

```text
http://localhost:8000/docs
```

## Chạy frontend

Mở terminal khác:

```powershell
cd ai-presentation-builder\frontend
npm.cmd install
npm.cmd run dev
```

Mở web:

```text
http://localhost:5173
```

## Cấu hình AI thật

### Google AI Studio (Gemini) — khuyến nghị

Lấy API key tại: https://aistudio.google.com/apikey

```powershell
cd ai-presentation-builder\backend
.venv\Scripts\activate
pip install -r requirements.txt
$env:GOOGLE_API_KEY="your_google_ai_studio_api_key_here"
python -m uvicorn main:app --reload --port 8000
```

Tuỳ chọn model (mặc định `gemini-3.1-pro`):

```powershell
$env:GEMINI_MODEL="gemini-3.1-pro"
```

Xem quota thực tế tại https://ai.dev/rate-limit — chỉ dùng model có RPM/RPD **khác 0/0**.  
Ví dụ các model hiện đại: `gemini-3.1-pro`, `gemini-3.1-flash-lite`, `gemini-3.5-flash`, `gemini-2.5-flash`.

### Anthropic Claude (tuỳ chọn)

```powershell
$env:ANTHROPIC_API_KEY="your_api_key_here"
python -m uvicorn main:app --reload --port 8000
```

Nếu set cả hai key, backend ưu tiên **Gemini**. Ép dùng Claude: `$env:LLM_PROVIDER="anthropic"`.

Nếu chưa có key, backend vẫn trả deck demo từ nội dung file để test end-to-end.

## API quan trọng

### Generate từ file

```text
POST /generate-deck-from-file
```

Form-data:

- `file`: `.docx`, `.txt`, `.md`
- `num_slides`: 3-15
- `audience`: general/students/investors/technical
- `tone`: professional/friendly/persuasive/academic

Response gồm:

- `deck`: JSON deck để preview/export
- `images`: danh sách ảnh trích xuất từ DOCX
- `image_count`: số ảnh tìm được

### Export PPTX

```text
POST /export-pptx
```

Body:

```json
{
  "deck": {},
  "enable_transitions": true
}
```

Export hoàn chỉnh sang PowerPoint với layout hiện đại (header band, footer số trang, card 2 cột, nút CTA) và hiệu ứng chuyển slide.

## Luồng xử lý DOCX

1. Backend nhận file DOCX.
2. `document_reader.py` đọc text, table và extract ảnh.
3. Ảnh được lưu tạm ở thư mục temp và serve qua `/assets/...`.
4. Prompt gửi thêm danh sách ảnh cho AI.
5. AI chọn ảnh bằng `content.image_id`.
6. Frontend preview slide có hình ảnh.
7. `pptx_exporter.py` render ảnh vào file PPTX và thêm slide transition effects.
