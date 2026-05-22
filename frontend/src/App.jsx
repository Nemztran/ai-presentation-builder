import { useState } from "react";
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

  async function handleFileChange(e) {
    const file = e.target.files?.[0] || null;
    setSourceFile(file);
    setDeckData(null);
    setSlides(null);
    setSourceImages([]);
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

    try {
      const formData = new FormData();
      formData.append("file", sourceFile);
      formData.append("audience", audience);
      formData.append("tone", tone);
      formData.append("num_slides", String(Number(numSlides)));

      const res = await fetch(`${API_BASE}/generate-deck-from-file`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) throw new Error(await res.text());

      const data = await res.json();
      setDeckData(data.deck);
      setSlides(data.deck.slides);
      setSourceImages(data.images || []);
      setActiveSlide(0);
    } catch (e) {
      setError("Không tạo được deck từ file. Kiểm tra backend log hoặc định dạng file.");
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
        body: JSON.stringify({ deck: deckData, enable_transitions: true }),
      });

      if (!res.ok) throw new Error(await res.text());

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
          onChange={(e) => setNumSlides(e.target.value)}
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

function SlidePreview({ slide, theme }) {
  if (!slide) return null;

  const content = slide.content || {};
  const imageUrl = content.image_url ? `${API_BASE}${content.image_url}` : null;

  return (
    <div className={`slide-preview theme-${theme || "professional"} layout-${slide.layout}`}>
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
