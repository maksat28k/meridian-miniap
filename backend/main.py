from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import sqlite3, os, json, shutil, asyncio
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
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

executor = ThreadPoolExecutor(max_workers=4)

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

def get_or_create_user(telegram_id: str, name: str = None):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
    if not user:
        db.execute("INSERT INTO users (telegram_id, name) VALUES (?,?)", (telegram_id, name or ""))
        db.commit()
        user = db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
    db.close()
    return dict(user)

def get_history_summary(telegram_id: str, limit: int = 3) -> str:
    """Получает историю анализов для контекста AI."""
    try:
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
        if not user:
            db.close()
            return ""
        analyses = db.execute(
            "SELECT indicators, created_at FROM analyses WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user['id'], limit)
        ).fetchall()
        db.close()
        if not analyses:
            return ""
        lines = []
        for a in analyses:
            inds = json.loads(a['indicators'])
            date = a['created_at'][:10]
            vals = ', '.join(f"{k}={v}" for k, v in list(inds.items())[:8])
            lines.append(f"  {date}: {vals}")
        return "ИСТОРИЯ ПРЕДЫДУЩИХ АНАЛИЗОВ:\n" + "\n".join(lines)
    except Exception:
        return ""

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
    # Сохраняем PDF асинхронно
    filename = f"{telegram_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    filepath = os.path.join(UPLOAD_DIR, filename)
    content = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)

    # Парсим PDF + получаем историю параллельно
    loop = asyncio.get_event_loop()
    parsed, history = await asyncio.gather(
        loop.run_in_executor(executor, parse_pdf, filepath),
        loop.run_in_executor(executor, get_history_summary, telegram_id),
    )

    indicators = parsed['indicators']
    raw_text   = parsed['raw_text']

    if not indicators:
        return JSONResponse({
            "success": False,
            "message": "Не удалось извлечь показатели из PDF. Попробуй PDF из Инвитро, Гемотест или Хеликс.",
        })

    # AI анализ с историей (в отдельном потоке чтобы не блокировать)
    ai_result = await loop.run_in_executor(
        executor,
        lambda: analyze_with_ai(indicators, gender, age, name, raw_text, history)
    )

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
            'indicators': ai.get('indicators', []),
        })
    return result

@app.post("/api/chat")
async def chat(
    telegram_id: str = Form(...),
    message: str = Form(...),
    history: str = Form("[]"),
):
    """AI-чат с контекстом всех анализов пользователя."""
    # Загружаем последние анализы
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
    context = ""
    if user:
        analyses = db.execute(
            "SELECT indicators, ai_result, created_at FROM analyses WHERE user_id=? ORDER BY created_at DESC LIMIT 3",
            (user['id'],)
        ).fetchall()
        if analyses:
            latest = dict(analyses[0])
            ai = json.loads(latest['ai_result'])
            inds = json.loads(latest['indicators'])
            date = latest['created_at'][:10]
            ind_lines = '\n'.join(f"  {k}: {v}" for k,v in inds.items())
            context = f"""ДАННЫЕ ПОЛЬЗОВАТЕЛЯ (анализ от {date}):
Показатели:
{ind_lines}
Краткий вывод AI: {ai.get('summary','')}
"""
        profile = dict(user)
        if profile.get('name'):
            context = f"Пациент: {profile['name']}, {profile.get('age','')} лет, {'мужчина' if profile.get('gender')=='m' else 'женщина'}\n" + context
    db.close()

    chat_history = json.loads(history) if history else []

    system = f"""Ты — персональный медицинский консультант Meridian. Твои ответы строго основаны на доказательной медицине.

ИСТОЧНИКИ: PubMed/MEDLINE, Cochrane Library, NEJM, JAMA, Lancet, BMJ, клинические руководства AHA/ESC/ADA/WHO/Endocrine Society, стандарты МЗ РФ.

ДАННЫЕ ПОЛЬЗОВАТЕЛЯ:
{context}

ПРАВИЛА ОТВЕТА:
- Каждое утверждение опирается на доказательства: упоминай источник когда уместно (например: "по данным Cochrane 2022...")
- Объясняй биологический механизм простым языком — почему это влияет на энергию, сон, концентрацию
- Конкретные рекомендации: дозы, формы препаратов, сроки
- НЕ ставь диагнозы — описывай состояния и риски
- Если вопрос требует очного врача — указывай специализацию и причину
- Отвечай кратко: 3-5 предложений, по делу
- Если вопрос не о здоровье — мягко верни к теме анализов"""

    # Строим историю разговора
    contents = [{"role": "user", "parts": [{"text": system + "\n\nНачало диалога."}]},
                {"role": "model", "parts": [{"text": "Привет! Я изучил твои анализы и готов ответить на вопросы."}]}]

    for msg in chat_history[-10:]:  # последние 10 сообщений
        role = "user" if msg.get("role") == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg.get("text", "")}]})

    contents.append({"role": "user", "parts": [{"text": message}]})

    try:
        from ai_analysis import get_client
        loop = asyncio.get_event_loop()
        def call_gemini():
            client = get_client()
            resp = client.models.generate_content(
                model='models/gemini-2.5-flash',
                contents=contents
            )
            return resp.text.strip()
        reply = await loop.run_in_executor(executor, call_gemini)
    except Exception as e:
        reply = "Извини, не смог ответить. Попробуй ещё раз."

    return {"reply": reply}

@app.get("/api/analysis/{analysis_id}")
def get_analysis(analysis_id: int):
    db = get_db()
    a = db.execute("SELECT * FROM analyses WHERE id=?", (analysis_id,)).fetchone()
    db.close()
    if not a:
        raise HTTPException(404, "Analysis not found")
    ai = json.loads(a['ai_result'])
    return {
        'id': a['id'],
        'created_at': a['created_at'],
        'indicators': ai.get('indicators', []),
        'summary': ai.get('summary', ''),
        'attention_count': ai.get('attention_count', 0),
        'ok_count': ai.get('ok_count', 0),
        'patterns': ai.get('patterns', []),
        'risks': ai.get('risks', []),
        'protocol': ai.get('protocol', []),
        'lifestyle': ai.get('lifestyle', {}),
        'positive': ai.get('positive', ''),
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
