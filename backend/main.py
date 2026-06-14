from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import sqlite3, os, json, shutil
from datetime import datetime
from pdf_parser import parse_pdf
from ai_analysis import analyze_with_ai, REFERENCE_RANGES, get_status

app = FastAPI(title="Meridian API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "meridian.db"
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ── DATABASE ──
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id TEXT UNIQUE NOT NULL,
            name TEXT,
            gender TEXT,
            age INTEGER,
            height INTEGER,
            weight INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            pdf_path TEXT,
            indicators TEXT,
            ai_result TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    """)
    db.commit()
    db.close()

init_db()

# ── HELPERS ──
def get_or_create_user(telegram_id: str, name: str = None):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
    if not user:
        db.execute("INSERT INTO users (telegram_id, name) VALUES (?,?)", (telegram_id, name or ""))
        db.commit()
        user = db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
    db.close()
    return dict(user)

# ── ROUTES ──

@app.get("/")
def root():
    return {"status": "Meridian API running"}

@app.post("/api/user/save")
async def save_user(
    telegram_id: str = Form(...),
    name: str = Form(...),
    gender: str = Form(...),
    age: int = Form(...),
    height: int = Form(None),
    weight: int = Form(None),
):
    db = get_db()
    db.execute("""
        INSERT INTO users (telegram_id, name, gender, age, height, weight)
        VALUES (?,?,?,?,?,?)
        ON CONFLICT(telegram_id) DO UPDATE SET
            name=excluded.name, gender=excluded.gender,
            age=excluded.age, height=excluded.height, weight=excluded.weight
    """, (telegram_id, name, gender, age, height, weight))
    db.commit()
    user = db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
    db.close()
    return dict(user)

@app.get("/api/user/{telegram_id}")
def get_user(telegram_id: str):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
    db.close()
    if not user:
        raise HTTPException(404, "User not found")
    return dict(user)

@app.post("/api/analyze")
async def analyze_pdf(
    telegram_id: str = Form(...),
    name: str = Form(...),
    gender: str = Form(...),
    age: int = Form(...),
    file: UploadFile = File(...),
):
    # Сохраняем PDF
    filename = f"{telegram_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    filepath = os.path.join(UPLOAD_DIR, filename)

    with open(filepath, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Парсим PDF
    parsed = parse_pdf(filepath)
    indicators = parsed['indicators']
    raw_text   = parsed['raw_text']

    if not indicators:
        return JSONResponse({
            "success": False,
            "message": "Не удалось извлечь показатели из PDF. Попробуй PDF из Инвитро, Гемотест или Хеликс.",
        })

    # AI анализ
    ai_result = analyze_with_ai(indicators, gender, age, name, raw_text)

    # Сохраняем в БД
    user = get_or_create_user(telegram_id, name)
    db = get_db()
    db.execute(
        "INSERT INTO analyses (user_id, pdf_path, indicators, ai_result) VALUES (?,?,?,?)",
        (user['id'], filename, json.dumps(indicators), json.dumps(ai_result))
    )
    db.commit()
    analysis_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.close()

    # Возвращаем всё плоско — фронтенд ждёт indicators на верхнем уровне
    return {
        "success": True,
        "analysis_id": analysis_id,
        "found": len(indicators),
        "indicators": ai_result.get("indicators", []),
        "summary": ai_result.get("summary", ""),
        "attention_count": ai_result.get("attention_count", 0),
        "ok_count": ai_result.get("ok_count", 0),
        "patterns": ai_result.get("patterns", []),
        "risks": ai_result.get("risks", []),
        "protocol": ai_result.get("protocol", []),
        "lifestyle": ai_result.get("lifestyle", {}),
        "positive": ai_result.get("positive", ""),
    }

@app.get("/api/analyses/{telegram_id}")
def get_analyses(telegram_id: str):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
    if not user:
        return []
    analyses = db.execute(
        "SELECT id, created_at, indicators, ai_result FROM analyses WHERE user_id=? ORDER BY created_at DESC",
        (user['id'],)
    ).fetchall()
    db.close()
    result = []
    for a in analyses:
        inds = json.loads(a['indicators'])
        ai   = json.loads(a['ai_result'])
        result.append({
            'id': a['id'],
            'date': a['created_at'],
            'found': len(inds),
            'attention': ai.get('attention_count', 0),
            'summary': ai.get('summary', ''),
        })
    return result

@app.get("/api/analysis/{analysis_id}")
def get_analysis(analysis_id: int):
    db = get_db()
    a = db.execute("SELECT * FROM analyses WHERE id=?", (analysis_id,)).fetchone()
    db.close()
    if not a:
        raise HTTPException(404, "Analysis not found")
    return {
        'id': a['id'],
        'date': a['created_at'],
        'indicators': json.loads(a['indicators']),
        'result': json.loads(a['ai_result']),
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
