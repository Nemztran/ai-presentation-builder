import { useEffect, useState } from "react";
import "./style.css";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export default function App() {
  const [sourceFile, setSourceFile] = useState(null);
  const [filePreview, setFilePreview] = useState("");
  const [audience, setAudience] = useState("general");
  const [tone, setTone] = useState("professional");
  const [numSlides, setNumSlides] = useState(6);
  const [slides, setSlides] = useState(null);
  const [deckData, setDeckData] = useState(null);
  const [sourceImages, setSourceImages] = useState([]);
  const [activeSlide, setActiveSlide] = useState(0);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState(null);
  const [llmHealth, setLlmHealth] = useState(null);
  const [generation, setGeneration] = useState(null);
  const [customApiKey, setCustomApiKey] = useState("");

  useEffect(() => {
    fetch(`${API_BASE}/health`)
      .then((res) => res.json())
      .then(setLlmHealth)
      .catch(() => setLlmHealth(null));
  }, []);

  async function handleFileChange(e) {
    const file = e.target.files?.[0] || null;
    setSourceFile(file);
    setDeckData(null);
    setSlides(null);
    setSourceImages([]);
    setGeneration(null);
    setError(null);

    if (!file) {
      setFilePreview("");
      return;
    }

    const allowed = ["text/plain", "text/markdown", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ""];
    const nameOk = /\.(txt|md|markdown|docx)$/i.test(file.name);
    if (!allowed.includes(file.type) && !nameOk) {
      setError("Chỉ hỗ trợ file .txt, .md, .markdown hoặc .docx");
      setFilePreview("");
      return;
    }

    if (file.size > 15_000_000) {
      setError("File quá lớn. Hãy dùng file dưới 15 MB.");
      setFilePreview("");
      return;
    }

    if (/\.docx$/i.test(file.name)) {
      setFilePreview(`Đã chọn file DOCX: ${file.name}\nDung lượng: ${(file.size / 1024).toFixed(1)} KB\nBackend sẽ đọc văn bản, bảng và trích xuất hình ảnh nhúng trong file Word.`);
      return;
    }

    const text = await file.text();
    setFilePreview(text.slice(0, 1200));
  }

  async function handleGenerate() {
    if (!sourceFile) return;
    setLoading(true);
    setError(null);
    setSlides(null);
    setSourceImages([]);
    setGeneration(null);

    try {
      const formData = new FormData();
      formData.append("file", sourceFile);
      formData.append("audience", audience);
      formData.append("tone", tone);
      formData.append("num_slides", String(Number(numSlides)));
      if (customApiKey) {
        formData.append("api_key", customApiKey);
      }

      const res = await fetch(`${API_BASE}/generate-deck-from-file`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const body = await res.text();
        let detail = body;
        try {
          const parsed = JSON.parse(body);
          detail = parsed.detail ?? body;
          if (Array.isArray(detail)) {
            detail = detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
          }
        } catch {
          /* keep raw body */
        }
        throw new Error(detail || `HTTP ${res.status}`);
      }

      const data = await res.json();
      setDeckData(data.deck);
      setSlides(data.deck.slides);
      setSourceImages(data.images || []);
      setGeneration(data.generation || null);
      setActiveSlide(0);
    } catch (e) {
      setError(e.message || "Không tạo được deck từ file.");
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  async function handleExport() {
    if (!deckData) return;
    setExporting(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/export-pptx`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          deck: deckData,
          enable_transitions: true,
        }),
      });

      if (!res.ok) {
        const body = await res.text();
        let detail = body;
        try {
          const parsed = JSON.parse(body);
          detail = parsed.detail ?? body;
        } catch {
          /* ignore */
        }
        throw new Error(detail || `HTTP ${res.status}`);
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${deckData.title || "deck"}.pptx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError("Export PPTX thất bại. Kiểm tra backend log.");
      console.error(e);
    } finally {
      setExporting(false);
    }
  }

  const active = slides?.[activeSlide];

  return (
    <main className="page">
      <section className="hero">
        <div>
          <p className="eyebrow">Hackathon Demo</p>
          <h1>AI Presentation Builder</h1>
          <p className="subtitle">
            Upload file .docx / .txt / .md, AI đọc nội dung, trích xuất hình ảnh, tạo slide demo và export PowerPoint có transition effects.
          </p>
        </div>
      </section>

      <div className={`llm-status ${(llmHealth?.llm_configured) || customApiKey ? "configured" : "missing"}`}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>
            Backend LLM:{" "}
            {customApiKey
              ? "Đang dùng Custom API Key (từ trình duyệt)"
              : llmHealth?.llm_configured
                ? `${llmHealth.llm_provider} (${llmHealth.llm_model}) — key môi trường`
                : llmHealth === null
                  ? "Không kết nối được backend — nhập API Key để dùng"
                  : "chưa có API key (vui lòng nhập bên dưới)"}
          </span>
          <button
            onClick={() => {
              const key = prompt("Nhập API Key từ Google AI Studio (bắt đầu bằng AIza...) hoặc Anthropic (sk-ant...):", customApiKey);
              if (key !== null) setCustomApiKey(key.trim());
            }}
            style={{ fontSize: '12px', padding: '6px 10px', background: '#e5e7eb', color: '#1f2937', border: '1px solid #d1d5db', borderRadius: '6px', cursor: 'pointer', fontWeight: 'bold', flexShrink: 0, marginLeft: '12px' }}
          >
            {customApiKey ? "Đổi API Key" : "Nhập API Key"}
          </button>
        </div>
      </div>

      {generation && (
        <div className={`llm-status ${generation.used_llm ? "configured" : "missing"}`}>
          Lần generate vừa rồi: {formatGeneration(generation)}
        </div>
      )}

      <section className="panel controls file-controls">
        <label className="file-box">
          <span>Source file</span>
          <input type="file" accept=".txt,.md,.markdown,.docx,text/plain,text/markdown,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={handleFileChange} />
          <strong>{sourceFile ? sourceFile.name : "Chọn file .docx / .txt / .md"}</strong>
        </label>

        <select value={audience} onChange={(e) => setAudience(e.target.value)}>
          <option value="general">General audience</option>
          <option value="students">Students</option>
          <option value="investors">Investors</option>
          <option value="technical">Technical audience</option>
        </select>

        <select value={tone} onChange={(e) => setTone(e.target.value)}>
          <option value="professional">Professional</option>
          <option value="friendly">Friendly</option>
          <option value="persuasive">Persuasive</option>
          <option value="academic">Academic</option>
        </select>

        <input
          type="number"
          min="3"
          max="15"
          value={numSlides}
          onChange={(e) => {
            const n = Number(e.target.value);
            if (!Number.isNaN(n)) setNumSlides(n);
          }}
        />

        <button onClick={handleGenerate} disabled={loading || !sourceFile}>
          {loading ? "Generating..." : "Generate demo slides"}
        </button>
      </section>

      {filePreview && !slides && (
        <section className="panel file-preview-box">
          <div className="side-title">FILE PREVIEW</div>
          <pre>{filePreview}{filePreview.length >= 1200 ? "\n..." : ""}</pre>
        </section>
      )}

      {error && <div className="error">{error}</div>}

      {loading && (
        <section className="panel loading">
          <div className="robot">🤖</div>
          <p>AI đang đọc file, trích xuất hình ảnh và tạo slide deck...</p>
        </section>
      )}

      {slides && (
        <section className="workspace">
          <aside className="panel thumbnails">
            <div className="side-title">SLIDES ({slides.length})</div>
            {slides.map((slide, index) => (
              <button
                key={slide.slide_id ?? index}
                className={index === activeSlide ? "thumb active" : "thumb"}
                onClick={() => setActiveSlide(index)}
              >
                <span>{index + 1}.</span>
                <strong>{slide.content?.heading || slide.layout}</strong>
                <small>{slide.layout} · {slide.transition || "fade"}</small>
              </button>
            ))}
          </aside>

          <section className="preview-area">
            {sourceImages.length > 0 && (
              <div className="panel image-strip">
                <div className="side-title">DOCX IMAGES ({sourceImages.length})</div>
                <div className="image-list">
                  {sourceImages.slice(0, 8).map((img) => (
                    <img key={img.image_id} src={`${API_BASE}${img.url}`} alt={img.caption || img.filename} />
                  ))}
                </div>
              </div>
            )}

            <SlidePreview slide={active} theme={deckData?.theme} />

            {active?.speaker_notes && (
              <div className="notes">
                <strong>SPEAKER NOTES</strong>
                <p>{active.speaker_notes}</p>
              </div>
            )}

            <div className="actions">
              <button className="export" onClick={handleExport} disabled={exporting}>
                {exporting ? "Exporting..." : "Export complete PPTX with effects"}
              </button>
            </div>
          </section>
        </section>
      )}
    </main>
  );
}

function formatGeneration(gen) {
  if (gen.used_llm) {
    return `đã gọi ${gen.provider} (${gen.model})`;
  }
  if (gen.source === "demo_document_no_key" || gen.source === "demo_no_key") {
    return "không gọi LLM — chế độ demo (chưa có key)";
  }
  if (gen.source === "demo_document_llm_error" || gen.source === "demo_llm_error") {
    const hint = gen.error?.includes("429") || gen.error?.includes("quota")
      ? "hết quota / rate limit — đổi model hoặc đợi"
      : "lỗi API";
    return `không gọi LLM thành công (${hint})${gen.error ? `: ${gen.error.slice(0, 120)}…` : ""}`;
  }
  return gen.source || "không rõ";
}

function SlidePreview({ slide, theme }) {
  if (!slide) return null;

  const content = slide.content || {};
  const imageUrl = content.image_url ? `${API_BASE}${content.image_url}` : null;

  return (
    <div className={`slide-preview theme-${theme || "professional"} layout-${slide.layout}`}>
      <div className="slide-header-band" />
      <div className="badge">{slide.layout} · {slide.transition || "fade"}</div>

      {imageUrl && (slide.layout === "title" || slide.layout === "quote") && <img className="slide-bg-image" src={imageUrl} alt={content.image_caption || "DOCX image"} />}
      {imageUrl && (slide.layout === "title" || slide.layout === "quote") && <div className="slide-bg-overlay" />}

      {slide.layout === "two_column" ? (
        <>
          <h2>{content.heading}</h2>
          <div className="columns">
            <pre>{content.left_column}</pre>
            <pre>{content.right_column}</pre>
          </div>
        </>
      ) : slide.layout === "image_text" ? (
        <>
          <div className="image-text-left">
            <h2>{content.heading}</h2>
            {content.subheading && <pre>{content.subheading}</pre>}
            {content.bullets?.slice(0, 4).map((b, index) => (
              <div className="bullet" key={index}>
                <span>•</span>
                <p><strong>{b.text}</strong>{b.detail && <em>{b.detail}</em>}</p>
              </div>
            ))}
          </div>
          <div className="docx-image-card">
            {imageUrl ? <img src={imageUrl} alt={content.image_caption || "DOCX image"} /> : <span>No image selected</span>}
          </div>
        </>
      ) : slide.layout === "quote" ? (
        <blockquote>
          “{content.quote}”
          <footer>— {content.author}</footer>
        </blockquote>
      ) : (
        <>
          {content.heading && <h2>{content.heading}</h2>}
          {content.subheading && <p className="subheading">{content.subheading}</p>}

          {content.bullets?.map((b, index) => (
            <div className="bullet" key={index}>
              <span>•</span>
              <p>
                <strong>{b.text}</strong>
                {b.detail && <em>{b.detail}</em>}
              </p>
            </div>
          ))}

          {imageUrl && <img className="mini-docx-image" src={imageUrl} alt={content.image_caption || "DOCX image"} />}
          {content.cta && <div className="cta">{content.cta}</div>}
        </>
      )}
    </div>
  );
}
