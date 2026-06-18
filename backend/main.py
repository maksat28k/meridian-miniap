from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
import sqlite3, os, json, shutil, asyncio
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from pdf_parser import parse_pdf
from ai_analysis import analyze_with_ai, REFERENCE_RANGES, get_status

BOT_TOKEN  = os.environ.get("BOT_TOKEN", "")
WEBAPP_URL = "https://maksat28k.github.io/meridian-miniap"
API_URL    = os.environ.get("API_URL", "https://meridian-miniap-production.up.railway.app")
ADMIN_ID   = os.environ.get("ADMIN_ID", "")

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
            plan TEXT DEFAULT 'free',
            paid_at TEXT,
            plan_expires_at TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            yookassa_id TEXT UNIQUE,
            amount REAL,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            pdf_path TEXT,
            indicators TEXT,
            ai_result TEXT,
            analysis_date TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    """)
    db.commit()
    db.close()

init_db()

# Миграции для существующих БД
for _migration in [
    "ALTER TABLE analyses ADD COLUMN analysis_date TEXT",
    "ALTER TABLE users ADD COLUMN plan TEXT DEFAULT 'free'",
    "ALTER TABLE users ADD COLUMN paid_at TEXT",
    "ALTER TABLE users ADD COLUMN plan_expires_at TEXT",
]:
    try:
        _mdb = get_db()
        _mdb.execute(_migration)
        _mdb.commit()
        _mdb.close()
    except Exception:
        pass

YOOKASSA_SHOP_ID  = os.environ.get("YOOKASSA_SHOP_ID", "")
YOOKASSA_SECRET   = os.environ.get("YOOKASSA_SECRET_KEY", "")
PLAN_DAYS         = 5  # дней доступа после оплаты
PLAN_PRICE        = 490.00

def user_has_access(telegram_id: str) -> bool:
    """Проверяет есть ли активный оплаченный доступ у пользователя."""
    db = get_db()
    user = db.execute("SELECT plan, plan_expires_at FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
    db.close()
    if not user:
        return False
    if user['plan'] == 'free' or not user['plan_expires_at']:
        return False
    from datetime import timezone
    expires = datetime.fromisoformat(user['plan_expires_at'])
    return datetime.now() < expires

async def notify_admin(text: str):
    if not BOT_TOKEN or not ADMIN_ID:
        return
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": ADMIN_ID, "text": text, "parse_mode": "HTML"}
            )
    except Exception as e:
        print(f"notify_admin error: {e}")

# ── TELEGRAM BOT (webhook) ──
async def setup_webhook():
    if not BOT_TOKEN:
        return
    try:
        import httpx
        webhook_url = f"{API_URL}/bot/webhook"
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
                json={"url": webhook_url, "drop_pending_updates": True}
            )
            print(f"Webhook set: {r.json()}")
    except Exception as e:
        print(f"Webhook setup error: {e}")

@app.on_event("startup")
async def on_startup():
    await setup_webhook()

@app.post("/bot/webhook")
async def bot_webhook(request: Request):
    if not BOT_TOKEN:
        return {"ok": True}
    try:
        import httpx
        data = await request.json()
        msg = data.get("message") or data.get("edited_message")
        if not msg:
            return {"ok": True}

        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")
        user = msg.get("from", {})
        first = user.get("first_name", "")
        last  = user.get("last_name", "")
        name  = (first + (" " + last if last else "")).strip()

        if text.startswith("/start"):
            reply = {
                "chat_id": chat_id,
                "text": (
                    f"Привет, {first}! 👋\n\n"
                    "Meridian — персональный разбор анализов крови на основе доказательной медицины.\n\n"
                    "📄 Загрузи PDF с анализами\n"
                    "🔬 Получи расшифровку с научными источниками\n"
                    "📈 Следи за динамикой здоровья\n\n"
                    "Нажми кнопку ниже ↓"
                ),
                "reply_markup": {
                    "keyboard": [[{
                        "text": "🩺 Открыть Meridian",
                        "web_app": {"url": WEBAPP_URL}
                    }]],
                    "resize_keyboard": True,
                    "persistent": True
                }
            }
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json=reply
                )
        elif text.startswith("/help"):
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": (
                            "🩺 Как пользоваться Meridian:\n\n"
                            "1. Нажми кнопку «Открыть Meridian»\n"
                            "2. Заполни профиль (возраст, пол)\n"
                            "3. Загрузи PDF с анализами крови\n"
                            "4. Получи персональный разбор с AI\n\n"
                            "По вопросам: @maksat28k"
                        )
                    }
                )
        elif text.startswith("/stats") and str(chat_id) == ADMIN_ID:
            db = get_db()
            total_users    = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            total_analyses = db.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]
            today_users    = db.execute("SELECT COUNT(*) FROM users WHERE DATE(created_at)=DATE('now')").fetchone()[0]
            today_analyses = db.execute("SELECT COUNT(*) FROM analyses WHERE DATE(created_at)=DATE('now')").fetchone()[0]
            week_users     = db.execute("SELECT COUNT(*) FROM users WHERE created_at >= datetime('now','-7 days')").fetchone()[0]
            recent = db.execute("SELECT name, telegram_id, created_at FROM users ORDER BY created_at DESC LIMIT 5").fetchall()
            db.close()
            recent_text = "\n".join(f"  • {r['name'] or 'аноним'} ({r['telegram_id']}) — {r['created_at'][:10]}" for r in recent)
            stats_text = (
                f"📊 <b>Meridian Stats</b>\n\n"
                f"👥 Всего пользователей: <b>{total_users}</b>\n"
                f"📄 Всего анализов: <b>{total_analyses}</b>\n"
                f"📈 Анализов на пользователя: <b>{round(total_analyses/total_users,1) if total_users else 0}</b>\n\n"
                f"📅 Сегодня:\n"
                f"  Новых: <b>{today_users}</b> | Анализов: <b>{today_analyses}</b>\n\n"
                f"📅 За 7 дней: <b>{week_users}</b> новых\n\n"
                f"🕐 Последние регистрации:\n{recent_text}"
            )
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={"chat_id": chat_id, "text": stats_text, "parse_mode": "HTML"}
                )
    except Exception as e:
        print(f"Webhook handler error: {e}")
    return {"ok": True}

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
            vals = ', '.join(f"{k}={v}" for k, v in inds.items())  # все показатели, не [:8]
            lines.append(f"  {date}: {vals}")
        return "ИСТОРИЯ ПРЕДЫДУЩИХ АНАЛИЗОВ:\n" + "\n".join(lines)
    except Exception:
        return ""

# ── ROUTES ──
# ── PAYMENT ──

@app.post("/api/payment/create")
async def create_payment(telegram_id: str = Form(...)):
    """Создаёт платёж в ЮКасса и возвращает ссылку на оплату."""
    if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET:
        raise HTTPException(500, "Оплата временно недоступна")

    if user_has_access(telegram_id):
        return {"already_paid": True, "message": "У тебя уже активен доступ"}

    import uuid, httpx
    idempotency_key = str(uuid.uuid4())
    return_url = f"{WEBAPP_URL}?paid=1"

    payload = {
        "amount": {"value": f"{PLAN_PRICE:.2f}", "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": return_url},
        "capture": True,
        "description": f"Meridian — полный разбор анализов на 5 дней (ID: {telegram_id})",
        "metadata": {"telegram_id": telegram_id},
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.yookassa.ru/v3/payments",
                json=payload,
                auth=(YOOKASSA_SHOP_ID, YOOKASSA_SECRET),
                headers={"Idempotence-Key": idempotency_key},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

        payment_id = data["id"]
        confirm_url = data["confirmation"]["confirmation_url"]

        # Сохраняем платёж в БД
        db = get_db()
        user = db.execute("SELECT id FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
        if user:
            db.execute(
                "INSERT OR IGNORE INTO payments (user_id, yookassa_id, amount, status) VALUES (?,?,?,?)",
                (user['id'], payment_id, PLAN_PRICE, "pending")
            )
            db.commit()
        db.close()

        return {"payment_url": confirm_url, "payment_id": payment_id}

    except Exception as e:
        print(f"YooKassa create error: {e}")
        raise HTTPException(500, "Не удалось создать платёж. Попробуй позже.")


@app.post("/api/payment/webhook")
async def payment_webhook(request: Request):
    """Принимает уведомления от ЮКасса об успешной оплате."""
    try:
        data = await request.json()
        event = data.get("event", "")
        obj   = data.get("object", {})

        if event != "payment.succeeded":
            return {"ok": True}

        payment_id  = obj.get("id")
        metadata    = obj.get("metadata", {})
        telegram_id = metadata.get("telegram_id")

        if not telegram_id or not payment_id:
            return {"ok": True}

        # Активируем доступ на 5 дней
        from datetime import timedelta
        now     = datetime.now()
        expires = now + timedelta(days=PLAN_DAYS)

        db = get_db()
        db.execute(
            "UPDATE users SET plan='paid', paid_at=?, plan_expires_at=? WHERE telegram_id=?",
            (now.isoformat(), expires.isoformat(), telegram_id)
        )
        db.execute(
            "UPDATE payments SET status='succeeded' WHERE yookassa_id=?",
            (payment_id,)
        )
        db.commit()
        user = db.execute("SELECT name FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
        db.close()

        name = user['name'] if user else "аноним"
        await notify_admin(
            f"💳 <b>Оплата получена!</b>\n"
            f"👤 {name} ({telegram_id})\n"
            f"💰 {PLAN_PRICE:.0f} ₽\n"
            f"📅 Доступ до: {expires.strftime('%d.%m.%Y %H:%M')}"
        )

    except Exception as e:
        print(f"Webhook error: {e}")

    return {"ok": True}


@app.get("/api/payment/status/{telegram_id}")
def payment_status(telegram_id: str):
    """Возвращает текущий статус доступа пользователя."""
    db = get_db()
    user = db.execute(
        "SELECT plan, paid_at, plan_expires_at FROM users WHERE telegram_id=?",
        (telegram_id,)
    ).fetchone()
    db.close()
    if not user:
        return {"plan": "free", "has_access": False}

    has_access = user_has_access(telegram_id)
    return {
        "plan": user['plan'],
        "has_access": has_access,
        "expires_at": user['plan_expires_at'],
        "paid_at": user['paid_at'],
    }


@app.get("/")
def root():
    return {"status": "Meridian API running"}

@app.post("/api/user/save")
async def save_user(
    telegram_id: str = Form(...),
    name: str = Form(""),
    gender: str = Form(""),
    age: int = Form(0),
    height: int = Form(None),
    weight: int = Form(None),
):
    db = get_db()
    existing = db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
    if existing:
        existing = dict(existing)
        # Не затираем уже заполненные поля пустыми значениями
        upd_name   = name   if name   else existing.get('name', '')
        upd_gender = gender if gender else existing.get('gender', '')
        upd_age    = age    if age    else existing.get('age', 0)
        upd_height = height if height else existing.get('height')
        upd_weight = weight if weight else existing.get('weight')
        db.execute("""UPDATE users SET name=?,gender=?,age=?,height=?,weight=?
                      WHERE telegram_id=?""",
                   (upd_name, upd_gender, upd_age, upd_height, upd_weight, telegram_id))
    else:
        db.execute("""INSERT INTO users (telegram_id, name, gender, age, height, weight)
                      VALUES (?,?,?,?,?,?)""",
                   (telegram_id, name, gender, age, height, weight))
        # Уведомление о новом пользователе
        db2 = get_db()
        total = db2.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        db2.close()
        asyncio.create_task(notify_admin(
            f"🆕 <b>Новый пользователь!</b>\n"
            f"👤 {name or 'аноним'}\n"
            f"🆔 {telegram_id}\n"
            f"👥 Всего в базе: <b>{total}</b>"
        ))
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

    indicators    = parsed['indicators']
    raw_text      = parsed['raw_text']
    analysis_date = parsed.get('analysis_date')  # дата из документа

    # Если keyword-матчинг нашёл мало — пробуем AI-парсинг
    if len(indicators) < 3 and raw_text:
        try:
            ai_parsed = await loop.run_in_executor(executor, lambda: ai_parse_pdf(raw_text))
            if ai_parsed:
                indicators = {**ai_parsed, **indicators}  # keyword-результаты приоритетнее
        except Exception as e:
            print(f"AI PDF parse error: {e}")

    if not indicators:
        return JSONResponse({
            "success": False,
            "message": "Не удалось извлечь показатели из PDF. Попробуй загрузить другой файл или введи показатели вручную.",
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
        "INSERT INTO analyses (user_id, pdf_path, indicators, ai_result, analysis_date) VALUES (?,?,?,?,?)",
        (user['id'], filename, json.dumps(indicators), json.dumps(ai_result), analysis_date)
    )
    db.commit()
    analysis_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.close()

    return {
        "success": True,
        "analysis_id": analysis_id,
        "analysis_date": analysis_date,
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

def ai_parse_pdf(raw_text: str) -> dict:
    """Используем Gemini для извлечения показателей из PDF любой лаборатории."""
    import re as _re
    from ai_analysis import get_client
    keys_hint = (
        "hemoglobin, hematocrit, platelets, esr, leukocytes, erythrocytes, glucose, "
        "cholesterol, hdl, ldl, triglycerides, insulin, hba1c, ferritin, iron, tibc, "
        "transferrin, vitamin_d, b12, folate, tsh, t4_free, t3_free, tpo_ab, crp, "
        "alt, ast, ggt, bilirubin, albumin, creatinine, urea, uric_acid, cortisol, "
        "testosterone, estradiol, progesterone, magnesium, calcium, potassium, sodium, "
        "phosphorus, zinc, mcv, mch, mchc, rdw, neutrophils, lymphocytes, monocytes, "
        "eosinophils, basophils, dhea, igf1, homocysteine, prolactin, omega3_index"
    )
    prompt = f"""Ты — парсер лабораторных анализов. Из текста ниже извлеки числовые значения показателей крови.

Используй ТОЛЬКО эти ключи (английские, snake_case):
{keys_hint}

Правила:
- Извлекай только числа которые явно присутствуют в тексте
- Если показатель указан в другой единице (например г/л вместо г/дл) — пересчитай
- Не придумывай значения
- Верни ТОЛЬКО валидный JSON: {{"ключ": число, ...}}

Текст анализов:
{raw_text[:8000]}"""

    client = get_client()
    import time as _time
    for attempt in range(3):
        try:
            resp = client.models.generate_content(model='models/gemini-2.5-flash', contents=prompt)
            break
        except Exception as e:
            if attempt < 2:
                _time.sleep(3 * (attempt + 1))
            else:
                raise e
    text = resp.text.strip()
    m = _re.search(r'\{[^{}]*\}', text, _re.DOTALL)
    if m:
        data = json.loads(m.group())
        return {k: float(v) for k, v in data.items() if isinstance(v, (int, float)) and v > 0}
    return {}


@app.post("/api/analyze-manual")
async def analyze_manual(
    telegram_id: str = Form(...),
    name: str = Form(...),
    gender: str = Form(...),
    age: int = Form(...),
    indicators: str = Form(...),  # JSON-строка
    analysis_date: str = Form(""),  # дата обследования от пользователя
):
    """Анализ вручную введённых показателей."""
    try:
        inds = json.loads(indicators)
        inds = {k: float(v) for k, v in inds.items() if v}
    except Exception:
        raise HTTPException(400, "Invalid indicators JSON")

    if not inds:
        raise HTTPException(400, "No indicators provided")

    loop = asyncio.get_event_loop()
    history = await loop.run_in_executor(executor, get_history_summary, telegram_id)

    ai_result = await loop.run_in_executor(
        executor,
        lambda: analyze_with_ai(inds, gender, age, name, "", history)
    )

    user = get_or_create_user(telegram_id, name)
    db = get_db()
    db.execute(
        "INSERT INTO analyses (user_id, pdf_path, indicators, ai_result, analysis_date) VALUES (?,?,?,?,?)",
        (user['id'], 'manual', json.dumps(inds), json.dumps(ai_result), analysis_date or None)
    )
    db.commit()
    analysis_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.close()

    return {
        "success": True,
        "analysis_id": analysis_id,
        "analysis_date": analysis_date or None,
        "found": len(inds),
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
        "SELECT id, created_at, analysis_date, indicators, ai_result FROM analyses WHERE user_id=? ORDER BY created_at DESC",
        (user['id'],)
    ).fetchall()
    db.close()
    result = []
    for a in analyses:
        inds = json.loads(a['indicators'])
        ai   = json.loads(a['ai_result'])
        result.append({
            'id': a['id'],
            'date': a['analysis_date'] or a['created_at'],  # дата обследования или загрузки
            'uploaded_at': a['created_at'],
            'found': len(inds),
            'attention': ai.get('attention_count', 0),
            'summary': ai.get('summary', ''),
            'indicators': ai.get('indicators', []),
        })
    return result

@app.get("/api/full-analysis/{telegram_id}")
async def full_analysis(telegram_id: str):
    """Комплексный разбор на основе ВСЕХ анализов пользователя с динамикой."""
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
    if not user:
        raise HTTPException(404, "User not found")
    user = dict(user)

    analyses = db.execute(
        "SELECT id, indicators, ai_result, created_at, analysis_date FROM analyses WHERE user_id=? ORDER BY created_at ASC",
        (user['id'],)
    ).fetchall()
    db.close()

    if not analyses:
        raise HTTPException(404, "No analyses found")

    # Строим хронологию показателей
    timeline = []
    all_keys = set()
    for a in analyses:
        inds = json.loads(a['indicators'])
        all_keys.update(inds.keys())
        # Используем дату обследования если есть, иначе дату загрузки
        display_date = (a['analysis_date'] or a['created_at'])[:10]
        timeline.append({'date': display_date, 'indicators': inds})

    # Динамика: сравниваем первый и последний
    from ai_analysis import REFERENCE_RANGES
    gender = user.get('gender', 'm') or 'm'
    first = timeline[0]['indicators']
    last  = timeline[-1]['indicators']
    dynamics = []
    for k in all_keys:
        if k in first and k in last:
            diff = last[k] - first[k]
            pct  = round(diff / first[k] * 100, 1) if first[k] else 0
            ref = REFERENCE_RANGES.get(k, {})
            g = gender if gender in ('m', 'f') else 'm'
            rng = ref.get(g, ref.get('m', (None, None)))
            dynamics.append({
                'key': k,
                'name': ref.get('name', k),
                'unit': ref.get('unit', ''),
                'norm_min': rng[0],
                'norm_max': rng[1],
                'first': first[k],
                'last': last[k],
                'diff': round(diff, 2),
                'pct': pct
            })

    # Полный промпт для AI
    gender_text = "мужчина" if user.get('gender') == 'm' else "женщина"
    age  = user.get('age', 25)
    name = user.get('name', 'Пациент')

    timeline_text = ""
    for t in timeline:
        lines = ', '.join(f"{k}={v}" for k,v in t['indicators'].items())
        timeline_text += f"  {t['date']}: {lines}\n"

    dynamics_text = ""
    for d in dynamics:
        arrow = "↑" if d['diff'] > 0 else "↓"
        dynamics_text += f"  {d['key']}: {d['first']} → {d['last']} ({arrow}{abs(d['pct'])}%)\n"

    prompt = f"""Ты — медицинский аналитик Meridian. Твои ответы строго основаны на доказательной медицине.

ОБЯЗАТЕЛЬНОЕ ПРАВИЛО: каждую рекомендацию, каждый риск, каждый паттерн ОБЯЗАТЕЛЬНО подкрепляй конкретным источником.
Формат: "Автор et al., Журнал Год — краткая суть" или "Название руководства Год — суть".
Примеры:
- "Ridker PM et al., NEJM 2017 (JUPITER) — СРБ >2 мг/л удваивает риск ССЗ"
- "ADA Standards of Care 2024 — HbA1c >5.7% = предиабет"
- "Camaschella C., NEJM 2015 — механизм железодефицитной анемии"
- "ESC Guidelines Dyslipidaemia 2019 — целевой ЛПНП <1.8 ммоль/л"
- "Holick MF et al., NEJM 2007 — дефицит витамина D и иммунодисфункция"
- "Cochrane Review, Bjelakovic et al. 2014 — омега-3 снижает триглицериды на 25–30%"
- "WHO Iron Deficiency Anaemia Report 2023"

ПАЦИЕНТ: {name}, {age} лет, {gender_text}
КОЛИЧЕСТВО АНАЛИЗОВ: {len(analyses)} (с {timeline[0]['date']} по {timeline[-1]['date']})

ХРОНОЛОГИЯ ПОКАЗАТЕЛЕЙ:
{timeline_text}

ДИНАМИКА (первый → последний):
{dynamics_text}

Сделай КОМПЛЕКСНЫЙ СИСТЕМНЫЙ РАЗБОР на основе ВСЕЙ истории анализов:
1. Что улучшилось и что ухудшилось — с конкретными источниками к каждому выводу
2. Долгосрочные тренды и риски — механизм + исследование которое это доказывает
3. Паттерны видные только при сравнении нескольких анализов — с источником
4. Протокол действий с дозами, сроками и ссылкой на исследование для каждого пункта

Верни строго валидный JSON:
{{
  "summary": "2-3 предложения: общая динамика здоровья за весь период",
  "period": "{timeline[0]['date']} — {timeline[-1]['date']}",
  "analyses_count": {len(analyses)},
  "improved": [{{"key":"показатель","name":"название","from":0,"to":0,"interpretation":"что это значит для жизни","evidence":"Источник — суть"}}],
  "worsened": [{{"key":"показатель","name":"название","from":0,"to":0,"interpretation":"что это значит","urgency":"high/medium/low","evidence":"Источник — суть"}}],
  "stable": [{{"key":"показатель","value":0,"assessment":"оценка"}}],
  "patterns": [{{"title":"","description":"","indicators":[],"evidence":"Автор, Журнал Год — суть (обязательно)"}}],
  "risks": [{{"level":"high/medium/low","title":"","description":"","science":"Автор et al., Журнал Год — суть (обязательно)"}}],
  "protocol": [{{"priority":1,"action":"","reason":"","timeframe":"","evidence":"Источник рекомендации (обязательно)"}}],
  "lifestyle": {{"nutrition":"продукты + ссылка на исследование","supplements":"доза + источник (автор/журнал/год)","tests":"","doctor":""}},
  "positive": "что хорошо + источник подтверждающий важность этого показателя"
}}"""

    try:
        from ai_analysis import get_client
        import time as _time
        loop = asyncio.get_event_loop()
        def call_gemini():
            import re
            client = get_client()
            last_err = None
            for attempt in range(3):
                try:
                    resp = client.models.generate_content(model='models/gemini-2.5-flash', contents=prompt)
                    break
                except Exception as e:
                    last_err = e
                    if attempt < 2:
                        _time.sleep(3 * (attempt + 1))
                    else:
                        raise last_err
            text = resp.text.strip()
            m = re.search(r'\{.*\}', text, re.DOTALL)
            return json.loads(m.group()) if m else json.loads(text)
        result = await loop.run_in_executor(executor, call_gemini)
    except Exception as e:
        result = {"summary": f"Ошибка AI: {e}", "error": True}

    result['dynamics'] = dynamics
    result['timeline'] = timeline
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
    has_analyses = False
    if user:
        analyses = db.execute(
            "SELECT indicators, ai_result, created_at FROM analyses WHERE user_id=? ORDER BY created_at DESC LIMIT 3",
            (user['id'],)
        ).fetchall()
        if analyses:
            has_analyses = True
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

ДВУХУРОВНЕВАЯ СИСТЕМА ИСТОЧНИКОВ:

УРОВЕНЬ 1 — РОССИЙСКИЕ НОРМЫ (приоритет при оценке норм):
При ответе на вопрос "норма или нет" — опирайся на МЗ РФ, РКО, РАЭ. Это те же нормы что напечатаны в бланке пациента из Инвитро/Гемотеста.
- МЗ РФ — федеральные клинические рекомендации
- РКО (Российское кардиологическое общество) — холестерин, АД, ССР
- РАЭ (Российская ассоциация эндокринологов) — щитовидка, витамин D, диабет

УРОВЕНЬ 2 — МЕЖДУНАРОДНАЯ ДОКАЗАТЕЛЬНАЯ БАЗА:
- Механизмы болезней → NEJM, JAMA, Lancet, BMJ
- Протоколы лечения → ESC, ADA, Endocrine Society
- Дозы добавок → Endocrine Society, WHO, EFSA
- Эффективность вмешательств → Cochrane Library (высший уровень доказательности)

ДАННЫЕ ПОЛЬЗОВАТЕЛЯ:
{context}

ОБЯЗАТЕЛЬНОЕ ПРАВИЛО ЦИТИРОВАНИЯ:
Каждую рекомендацию или медицинское утверждение ОБЯЗАТЕЛЬНО подкрепляй источником прямо в тексте.
Примеры:
- "По нормам МЗ РФ и РАЭ, ТТГ в диапазоне 0.4–4.0 мкМЕ/мл считается нормой — это совпадает с референсами вашей лаборатории."
- "Ферритин ниже 30 мкг/л нарушает работу митохондрий (Camaschella C., NEJM 2015) — РАЭ рекомендует целевой ферритин >40 мкг/л."
- "Витамин D3 2000 МЕ/день — стартовая доза по рекомендациям РАЭ 2021; при дефиците Endocrine Society 2011 рекомендует до 4000–5000 МЕ/день."
- "СРБ выше 3 мг/л — независимый предиктор инфаркта (Ridker PM et al., NEJM 2002, JUPITER trial)."
- "По KР МЗ РФ по дислипидемиям 2023, целевой ЛПНП <3.0 ммоль/л для низкого ССР; ESC 2019 рекомендует <1.8 при высоком риске."
- "Cochrane Review 2017: омега-3 2–4 г/день снижает триглицериды на 25–30%."
- "ADA Standards of Care 2024: HbA1c 5.7–6.4% — зона предиабета."
- "WHO 2023: препараты железа 100–200 мг/день элементарного железа при дефиците."

ПРАВИЛА ОТВЕТА:
- Норму оцениваешь по российским стандартам (МЗ РФ/РКО/РАЭ) — пациент сравнит с бланком и увидит совпадение
- Если российские и западные нормы расходятся — укажи оба значения и объясни почему
- Объясняй биологический механизм простым языком — как влияет на энергию, сон, иммунитет, концентрацию
- Конкретные дозы с источником: препарат, форма, дозировка, время приёма
- НЕ ставь диагнозы — описывай функциональные состояния и риски
- Если нужен врач — указывай специализацию и конкретную причину направления
- Отвечай кратко и по делу
- Если вопрос не о здоровье — мягко верни к теме анализов

КРИТИЧЕСКИ ВАЖНОЕ ПРАВИЛО ПРО АНАЛИЗЫ ПАЦИЕНТА:
{"У пациента ЕСТЬ загруженные анализы — используй их данные при ответах на вопросы о его показателях." if has_analyses else "У пациента НЕТ загруженных анализов. СТРОГО ЗАПРЕЩЕНО придумывать, предполагать или называть какие-либо конкретные показатели этого пациента. Если пациент спрашивает о своих личных показателях (что у меня с анализами, какой у меня гемоглобин, есть ли у меня дефицит и т.д.) — ОБЯЗАТЕЛЬНО скажи что анализы не загружены и попроси загрузить PDF через кнопку в приложении. На общие вопросы о здоровье, питании, добавках — отвечай нормально."}"""

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

@app.get("/admin", response_class=HTMLResponse)
def admin_panel(token: str = Query(default="")):
    ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "meridian2025")
    if token != ADMIN_TOKEN:
        return HTMLResponse("""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Meridian Admin</title>
<style>body{font-family:sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;background:#0f172a;color:#fff}
.box{background:#1e293b;padding:32px;border-radius:16px;text-align:center;min-width:300px}
h2{margin:0 0 20px;color:#60a5fa}input{width:100%;padding:10px 14px;border-radius:8px;border:1px solid #334155;background:#0f172a;color:#fff;font-size:15px;box-sizing:border-box;margin-bottom:12px}
button{width:100%;padding:10px;background:#3b82f6;color:#fff;border:none;border-radius:8px;font-size:15px;cursor:pointer}
</style></head><body><div class="box"><h2>🔐 Meridian Admin</h2>
<form onsubmit="event.preventDefault();window.location='/admin?token='+document.getElementById('t').value">
<input id="t" type="password" placeholder="Пароль"><button type="submit">Войти</button>
</form></div></body></html>""", status_code=401)

    db = get_db()

    total_users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_analyses = db.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]

    users_by_day = db.execute("""
        SELECT DATE(created_at) as day, COUNT(*) as cnt
        FROM users GROUP BY day ORDER BY day DESC LIMIT 30
    """).fetchall()

    analyses_by_day = db.execute("""
        SELECT DATE(created_at) as day, COUNT(*) as cnt
        FROM analyses GROUP BY day ORDER BY day DESC LIMIT 30
    """).fetchall()

    recent_users = db.execute("""
        SELECT u.telegram_id, u.name, u.age, u.gender, u.created_at,
               COUNT(a.id) as analysis_count
        FROM users u LEFT JOIN analyses a ON a.user_id = u.id
        GROUP BY u.id ORDER BY u.created_at DESC LIMIT 50
    """).fetchall()

    db.close()

    def bar(val, max_val, width=120):
        pct = int(val / max_val * width) if max_val else 0
        return f'<div style="display:inline-block;width:{pct}px;height:10px;background:#3b82f6;border-radius:3px;vertical-align:middle;margin-left:8px"></div>'

    max_reg = max((r['cnt'] for r in users_by_day), default=1)
    max_ana = max((r['cnt'] for r in analyses_by_day), default=1)

    reg_rows = ''.join(f'<tr><td>{r["day"]}</td><td>{r["cnt"]}{bar(r["cnt"],max_reg)}</td></tr>' for r in users_by_day)
    ana_rows = ''.join(f'<tr><td>{r["day"]}</td><td>{r["cnt"]}{bar(r["cnt"],max_ana)}</td></tr>' for r in analyses_by_day)

    gender_map = {'m': '♂ муж', 'f': '♀ жен', None: '—', '': '—'}
    user_rows = ''.join(f'''<tr>
        <td>{u["name"] or "—"}</td>
        <td style="color:#94a3b8;font-size:12px">{u["telegram_id"]}</td>
        <td>{u["age"] or "—"}</td>
        <td>{gender_map.get(u["gender"], "—")}</td>
        <td style="text-align:center"><span style="background:#3b82f6;color:#fff;padding:2px 8px;border-radius:10px;font-size:12px">{u["analysis_count"]}</span></td>
        <td style="color:#64748b;font-size:12px">{(u["created_at"] or "")[:16]}</td>
    </tr>''' for u in recent_users)

    html = f"""<!DOCTYPE html><html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Meridian Admin</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0;padding:24px}}
h1{{font-size:22px;margin-bottom:24px;color:#f8fafc}}span.tag{{color:#60a5fa}}
.stats{{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:32px}}
.stat{{background:#1e293b;border-radius:14px;padding:20px 28px;flex:1;min-width:140px}}
.stat .n{{font-size:40px;font-weight:700;color:#60a5fa}}
.stat .l{{font-size:13px;color:#94a3b8;margin-top:4px}}
.card{{background:#1e293b;border-radius:14px;padding:20px;margin-bottom:24px}}
.card h2{{font-size:15px;font-weight:600;margin-bottom:16px;color:#cbd5e1}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{text-align:left;padding:8px 10px;color:#64748b;font-weight:500;border-bottom:1px solid #334155}}
td{{padding:8px 10px;border-bottom:1px solid #1e293b;vertical-align:middle}}
tr:hover td{{background:#263348}}
</style></head><body>
<h1>📊 Meridian <span class="tag">Admin</span></h1>
<div class="stats">
  <div class="stat"><div class="n">{total_users}</div><div class="l">Пользователей</div></div>
  <div class="stat"><div class="n">{total_analyses}</div><div class="l">Анализов загружено</div></div>
  <div class="stat"><div class="n">{round(total_analyses/total_users,1) if total_users else 0}</div><div class="l">Анализов на пользователя</div></div>
</div>
<div class="card">
  <h2>👥 Пользователи (последние 50)</h2>
  <table><thead><tr><th>Имя</th><th>Telegram ID</th><th>Возраст</th><th>Пол</th><th>Анализов</th><th>Зарегистрирован</th></tr></thead>
  <tbody>{user_rows}</tbody></table>
</div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
<div class="card">
  <h2>📅 Регистрации по дням</h2>
  <table><thead><tr><th>Дата</th><th>Новых</th></tr></thead><tbody>{reg_rows}</tbody></table>
</div>
<div class="card">
  <h2>📄 Анализы по дням</h2>
  <table><thead><tr><th>Дата</th><th>Загружено</th></tr></thead><tbody>{ana_rows}</tbody></table>
</div>
</div>
</body></html>"""
    return HTMLResponse(html)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
