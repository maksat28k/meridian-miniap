from google import genai
import json
import re
import os
import time

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
_client = None

def get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=GEMINI_KEY, http_options={'api_version': 'v1'})
    return _client

REFERENCE_RANGES = {
    'hemoglobin':    {'m': (13.2, 17.5), 'f': (11.7, 15.5), 'unit': 'г/дл',     'name': 'Гемоглобин'},
    'hematocrit':    {'m': (38.3, 48.6), 'f': (35.5, 44.9), 'unit': '%',         'name': 'Гематокрит'},
    'platelets':     {'m': (150, 400),   'f': (150, 400),   'unit': '×10⁹/л',    'name': 'Тромбоциты'},
    'esr':           {'m': (0, 15),      'f': (0, 20),      'unit': 'мм/ч',      'name': 'СОЭ'},
    'leukocytes':    {'m': (4.0, 9.0),   'f': (4.0, 9.0),   'unit': '×10⁹/л',   'name': 'Лейкоциты'},
    'erythrocytes':  {'m': (4.3, 5.7),   'f': (3.8, 5.1),   'unit': '×10¹²/л',  'name': 'Эритроциты'},
    'glucose':       {'m': (3.9, 5.5),   'f': (3.9, 5.5),   'unit': 'ммоль/л',  'name': 'Глюкоза'},
    'cholesterol':   {'m': (0, 5.2),     'f': (0, 5.2),     'unit': 'ммоль/л',  'name': 'Холестерин'},
    'hdl':           {'m': (1.0, 2.2),   'f': (1.2, 2.5),   'unit': 'ммоль/л',  'name': 'ЛПВП'},
    'ldl':           {'m': (0, 3.0),     'f': (0, 3.0),     'unit': 'ммоль/л',  'name': 'ЛПНП'},
    'triglycerides': {'m': (0, 1.7),     'f': (0, 1.7),     'unit': 'ммоль/л',  'name': 'Триглицериды'},
    'insulin':       {'m': (2.6, 24.9),  'f': (2.6, 24.9),  'unit': 'мкМЕ/мл',  'name': 'Инсулин'},
    'hba1c':         {'m': (0, 5.7),     'f': (0, 5.7),     'unit': '%',         'name': 'HbA1c'},
    'ferritin':      {'m': (22, 322),    'f': (10, 120),    'unit': 'мкг/л',     'name': 'Ферритин'},
    'iron':          {'m': (11.6, 31.3), 'f': (9.0, 30.4),  'unit': 'мкмоль/л', 'name': 'Железо'},
    'vitamin_d':     {'m': (30, 100),    'f': (30, 100),    'unit': 'нг/мл',     'name': 'Витамин D'},
    'b12':           {'m': (200, 900),   'f': (200, 900),   'unit': 'пг/мл',     'name': 'Витамин B12'},
    'folate':        {'m': (3.1, 20.5),  'f': (3.1, 20.5),  'unit': 'нг/мл',     'name': 'Фолат'},
    'tsh':           {'m': (0.4, 4.0),   'f': (0.4, 4.0),   'unit': 'мкМЕ/мл',  'name': 'ТТГ'},
    't4_free':       {'m': (9.0, 19.0),  'f': (9.0, 19.0),  'unit': 'пмоль/л',  'name': 'Т4 свободный'},
    't3_free':       {'m': (2.6, 5.7),   'f': (2.6, 5.7),   'unit': 'пмоль/л',  'name': 'Т3 свободный'},
    'crp':           {'m': (0, 5.0),     'f': (0, 5.0),     'unit': 'мг/л',      'name': 'СРБ'},
    'alt':           {'m': (0, 41),      'f': (0, 31),      'unit': 'Ед/л',      'name': 'АЛТ'},
    'ast':           {'m': (0, 40),      'f': (0, 32),      'unit': 'Ед/л',      'name': 'АСТ'},
    'ggt':           {'m': (0, 55),      'f': (0, 38),      'unit': 'Ед/л',      'name': 'ГГТ'},
    'creatinine':    {'m': (62, 115),    'f': (53, 97),     'unit': 'мкмоль/л',  'name': 'Креатинин'},
    'urea':          {'m': (2.5, 8.3),   'f': (2.5, 8.3),   'unit': 'ммоль/л',  'name': 'Мочевина'},
    'uric_acid':     {'m': (200, 430),   'f': (140, 360),   'unit': 'мкмоль/л',  'name': 'Мочевая кислота'},
    'cortisol':      {'m': (138, 690),   'f': (138, 690),   'unit': 'нмоль/л',   'name': 'Кортизол'},
    'testosterone':  {'m': (8.0, 28.0),  'f': (0.3, 2.8),   'unit': 'нмоль/л',   'name': 'Тестостерон'},
    'magnesium':     {'m': (0.7, 1.1),   'f': (0.7, 1.1),   'unit': 'ммоль/л',  'name': 'Магний'},
    'calcium':       {'m': (2.1, 2.6),   'f': (2.1, 2.6),   'unit': 'ммоль/л',  'name': 'Кальций'},
    'zinc':          {'m': (11.6, 18.0), 'f': (11.6, 18.0), 'unit': 'мкмоль/л', 'name': 'Цинк'},
    # Развёрнутый ОАК
    'leukocytes':    {'m': (4.0, 9.0),   'f': (4.0, 9.0),   'unit': '×10⁹/л',   'name': 'Лейкоциты'},
    'erythrocytes':  {'m': (4.3, 5.7),   'f': (3.8, 5.1),   'unit': '×10¹²/л',  'name': 'Эритроциты'},
    'mcv':           {'m': (80, 100),    'f': (80, 100),    'unit': 'фл',        'name': 'MCV (средний объём эр.)'},
    'mch':           {'m': (27, 34),     'f': (27, 34),     'unit': 'пг',        'name': 'MCH (среднее содержание Hb)'},
    'mchc':          {'m': (320, 360),   'f': (320, 360),   'unit': 'г/л',       'name': 'MCHC (средняя концентрация Hb)'},
    'rdw':           {'m': (11.5, 14.5), 'f': (11.5, 14.5), 'unit': '%',         'name': 'RDW (анизоцитоз)'},
    'neutrophils':   {'m': (48, 78),     'f': (48, 78),     'unit': '%',         'name': 'Нейтрофилы'},
    'lymphocytes':   {'m': (19, 37),     'f': (19, 37),     'unit': '%',         'name': 'Лимфоциты'},
    'monocytes':     {'m': (3, 11),      'f': (3, 11),      'unit': '%',         'name': 'Моноциты'},
    'eosinophils':   {'m': (1, 5),       'f': (1, 5),       'unit': '%',         'name': 'Эозинофилы'},
    'basophils':     {'m': (0, 1),       'f': (0, 1),       'unit': '%',         'name': 'Базофилы'},
    # Липидный профиль
    'hdl':           {'m': (1.0, 2.2),   'f': (1.2, 2.5),   'unit': 'ммоль/л',  'name': 'ЛПВП (хороший холестерин)'},
    'ldl':           {'m': (0, 3.0),     'f': (0, 3.0),     'unit': 'ммоль/л',  'name': 'ЛПНП (плохой холестерин)'},
    'triglycerides': {'m': (0, 1.7),     'f': (0, 1.7),     'unit': 'ммоль/л',  'name': 'Триглицериды'},
    'hba1c':         {'m': (0, 5.7),     'f': (0, 5.7),     'unit': '%',         'name': 'HbA1c (гликированный гемоглобин)'},
    # Почки
    'creatinine':    {'m': (62, 115),    'f': (53, 97),     'unit': 'мкмоль/л',  'name': 'Креатинин'},
    'urea':          {'m': (2.5, 8.3),   'f': (2.5, 8.3),   'unit': 'ммоль/л',  'name': 'Мочевина'},
    # Дополнительные
    'ggt':           {'m': (0, 55),      'f': (0, 38),      'unit': 'Ед/л',      'name': 'ГГТ'},
    'bilirubin':     {'m': (3.4, 20.5),  'f': (3.4, 20.5),  'unit': 'мкмоль/л', 'name': 'Билирубин общий'},
    'albumin':       {'m': (35, 52),     'f': (35, 52),     'unit': 'г/л',       'name': 'Альбумин'},
    'potassium':     {'m': (3.5, 5.1),   'f': (3.5, 5.1),   'unit': 'ммоль/л',  'name': 'Калий'},
    'sodium':        {'m': (136, 145),   'f': (136, 145),   'unit': 'ммоль/л',  'name': 'Натрий'},
    'phosphorus':    {'m': (0.81, 1.45), 'f': (0.81, 1.45), 'unit': 'ммоль/л',  'name': 'Фосфор'},
    'iron':          {'m': (11.6, 31.3), 'f': (9.0, 30.4),  'unit': 'мкмоль/л', 'name': 'Железо сывороточное'},
    'tibc':          {'m': (45, 77),     'f': (45, 77),     'unit': 'мкмоль/л', 'name': 'ОЖСС'},
    'folate':        {'m': (3.1, 20.5),  'f': (3.1, 20.5),  'unit': 'нг/мл',    'name': 'Фолат (В9)'},
    't3_free':       {'m': (2.6, 5.7),   'f': (2.6, 5.7),   'unit': 'пмоль/л',  'name': 'Т3 свободный'},
    'prolactin':     {'m': (86, 324),    'f': (102, 496),   'unit': 'мМЕ/л',    'name': 'Пролактин'},
    'estradiol':     {'m': (40, 160),    'f': (68, 1269),   'unit': 'пмоль/л',  'name': 'Эстрадиол'},
    'dhea':          {'m': (2.17, 15.2), 'f': (0.65, 9.15), 'unit': 'мкмоль/л', 'name': 'ДГЭА-С'},
    'igf1':          {'m': (115, 307),   'f': (115, 307),   'unit': 'нг/мл',    'name': 'ИФР-1 (IGF-1)'},
    'homocysteine':  {'m': (5, 15),      'f': (5, 12),      'unit': 'мкмоль/л', 'name': 'Гомоцистеин'},
    'omega3_index':  {'m': (8, 12),      'f': (8, 12),      'unit': '%',         'name': 'Омега-3 индекс'},
}

OPTIMAL_RANGES = {
    'glucose':    {'m': (3.9, 5.0),  'f': (3.9, 5.0)},
    'ferritin':   {'m': (70, 150),   'f': (40, 100)},
    'vitamin_d':  {'m': (40, 80),    'f': (40, 80)},
    'tsh':        {'m': (0.5, 2.5),  'f': (0.5, 2.5)},
    'crp':        {'m': (0, 1.0),    'f': (0, 1.0)},
    'cholesterol':{'m': (0, 4.5),    'f': (0, 4.5)},
    'ldl':        {'m': (0, 2.5),    'f': (0, 2.5)},
    'hba1c':      {'m': (0, 5.4),    'f': (0, 5.4)},
}

def get_status(key, value, gender):
    if key not in REFERENCE_RANGES:
        return 'none'
    ref = REFERENCE_RANGES[key]
    lo, hi = ref[gender]
    if value < lo or value > hi:
        return 'bad'
    if key in OPTIMAL_RANGES:
        opt = OPTIMAL_RANGES[key]
        olo, ohi = opt[gender]
        if value < olo or value > ohi:
            return 'warn'
    return 'ok'

def build_indicators_summary(indicators: dict, gender: str) -> str:
    lines = []
    for key, value in indicators.items():
        if key not in REFERENCE_RANGES:
            continue
        ref = REFERENCE_RANGES[key]
        name = ref['name']
        unit = ref['unit']
        lo, hi = ref[gender]
        st = get_status(key, value, gender)
        status_text = {'ok': 'норма', 'warn': 'вне оптимума', 'bad': 'ОТКЛОНЕНИЕ', 'none': ''}[st]
        lines.append(f"- {name}: {value} {unit} (норма {lo}–{hi}) [{status_text}]")
    return '\n'.join(lines)

SYSTEM_PROMPT = """Ты — медицинский аналитик Meridian. Твои ответы строго основаны на доказательной медицине.

ДВУХУРОВНЕВАЯ СИСТЕМА ИСТОЧНИКОВ:

УРОВЕНЬ 1 — РОССИЙСКИЕ НОРМЫ (приоритет при оценке референсных значений):
Используй эти источники когда определяешь норма/не норма — они совпадают с тем что напечатано в бланке пациента из Инвитро, Гемотеста, КДЛ:
- Клинические рекомендации МЗ РФ (Минздрав) — федеральный стандарт, обязательный для врачей
- РКО (Российское кардиологическое общество) — нормы холестерина, АД, сердечно-сосудистые риски
- РАЭ (Российская ассоциация эндокринологов) — щитовидная железа, витамин D, сахарный диабет
Пример: ТТГ норма по МЗ РФ/РАЭ — 0.4–4.0 мкМЕ/мл (именно это написано в бланке пациента).

УРОВЕНЬ 2 — МЕЖДУНАРОДНАЯ ДОКАЗАТЕЛЬНАЯ БАЗА (для механизмов, рисков, рекомендаций):
- Механизмы болезней: NEJM, JAMA, Lancet, BMJ — крупнейшие RCT и мета-анализы
- Протоколы лечения: ESC (кардиология), ADA (диабет), Endocrine Society (гормоны/витамины)
- Дозы добавок: Endocrine Society, WHO, EFSA — публикуют конкретные дозировки
- Эффективность вмешательств: Cochrane Library — систематические обзоры, высший уровень доказательности

ПРАВИЛО ДВУХ УРОВНЕЙ:
При оценке нормы показателя → сначала МЗ РФ / РКО / РАЭ (совпадает с бланком пациента).
При объяснении механизма, риска, рекомендации → NEJM / JAMA / ESC / ADA / Cochrane.
Если российские и международные нормы расходятся — укажи оба значения и объясни разницу.

ОБЯЗАТЕЛЬНОЕ ПРАВИЛО ЦИТИРОВАНИЯ:
Каждую рекомендацию, каждый риск, каждый паттерн ОБЯЗАТЕЛЬНО подкрепляй конкретным источником в формате:
  "evidence": "Автор и соавт., Журнал/Руководство, Год — краткая суть"

Примеры правильного цитирования:
- "КР МЗ РФ по дислипидемиям 2023 — целевой ЛПНП <3.0 ммоль/л для низкого ССР"
- "РАЭ Клинические рекомендации по витамину D 2021 — дефицит: <20 нг/мл, недостаточность: 20–30 нг/мл"
- "Holick MF et al., NEJM 2007 — дефицит витамина D связан с иммунодисфункцией и риском переломов"
- "Ridker PM et al., NEJM 2017 (JUPITER trial) — СРБ >2 мг/л удваивает риск ССЗ независимо от ЛПНП"
- "ADA Standards of Care 2024 — HbA1c >5.7% классифицируется как предиабет"
- "Camaschella C., NEJM 2015 — механизм железодефицитной анемии"
- "ESC Guidelines on Dyslipidaemia 2019 — целевой ЛПНП <1.8 ммоль/л при высоком ССР"
- "Endocrine Society Clinical Practice Guideline 2011 — витамин D3 1500–2000 МЕ/день для поддержания уровня"
- "Cochrane Review, Gaksch et al. 2017 — приём омега-3 2–4 г/день снижает триглицериды на 25–30%"
- "WHO Iron Deficiency Anaemia Report 2023 — препараты железа 100–200 мг/день элементарного железа"

ПРИНЦИПЫ РАЗБОРА:
1. Норму оцениваешь по российским стандартам (МЗ РФ/РКО/РАЭ) — это то что видит пациент в бланке
2. Механизм и риски объясняешь через международные исследования (NEJM/JAMA/Cochrane)
3. Ищи ПАТТЕРНЫ между показателями — один показатель вне нормы мало значит, сочетание — много
4. Оценивай ДИНАМИКУ если есть история анализов
5. Не ставь диагнозы — описывай функциональные состояния и риски
6. Каждое утверждение опирается на RCT, мета-анализы или клинические руководства (уровень A/B)

СТИЛЬ:
- Простой язык: объясняй что показатель значит для жизни (энергия, иммунитет, когниция, сон)
- Конкретные дозы добавок со ссылкой (например: "витамин D3 2000 МЕ/день — Endocrine Society 2011, адаптировано РАЭ 2021")
- Не пугай, но говори правду
- Если нужен врач — указывай специализацию конкретно

СТРУКТУРА ОТВЕТА (строго валидный JSON):
{
  "summary": "2-3 предложения: главное что происходит в теле, с опорой на биологические механизмы",
  "attention_count": число показателей требующих внимания,
  "ok_count": число показателей в норме,
  "patterns": [
    {
      "title": "название паттерна (например: 'Железодефицитное состояние')",
      "description": "объяснение механизма и влияния на самочувствие простым языком",
      "indicators": ["ферритин", "гемоглобин"],
      "evidence": "Автор, Журнал Год — суть находки (обязательно заполнить)"
    }
  ],
  "risks": [
    {
      "level": "high/medium/low",
      "title": "конкретный риск",
      "description": "механизм развития и временной горизонт при бездействии",
      "science": "Автор et al., Журнал Год — название исследования или руководства (обязательно)"
    }
  ],
  "protocol": [
    {
      "priority": 1,
      "action": "конкретное действие с дозой/частотой",
      "reason": "биологический механизм почему это работает",
      "timeframe": "через сколько недель/месяцев ожидать эффект",
      "evidence": "Источник рекомендации (автор, журнал, год — обязательно)"
    }
  ],
  "lifestyle": {
    "nutrition": "конкретные продукты и механизм их действия со ссылкой на исследования",
    "supplements": "название, форма, доза, время приёма — и источник (автор/журнал/год)",
    "tests": "какие анализы пересдать и через какой срок",
    "doctor": "специализация врача и причина направления"
  },
  "positive": "что действительно хорошо — обязательно найти позитивное с объяснением и источником"
}"""

def analyze_with_ai(indicators: dict, gender: str, age: int, name: str, raw_text: str = "", history: str = "") -> dict:
    """Отправляет показатели в Gemini и получает медицинский разбор."""

    gender_text = "мужчина" if gender == 'm' else "женщина"
    summary = build_indicators_summary(indicators, gender)

    pdf_context = ("ДОПОЛНИТЕЛЬНЫЙ КОНТЕКСТ ИЗ PDF:\n" + raw_text[:1000]) if raw_text else ""
    history_context = history if history else ""
    prompt = f"""{SYSTEM_PROMPT}

ПАЦИЕНТ: {name}, {age} лет, {gender_text}

ТЕКУЩИЕ АНАЛИЗЫ:
{summary}

{history_context}

{pdf_context}

Если есть история — сравни с предыдущими анализами, отметь динамику (улучшилось/ухудшилось).
Найди паттерны между показателями. Объясни простым языком. Верни строго валидный JSON."""

    try:
        client = get_client()
        # Retry до 3 раз при 503/перегрузке Gemini
        last_err = None
        for attempt in range(3):
            try:
                response = client.models.generate_content(model='models/gemini-2.5-flash', contents=prompt)
                break
            except Exception as e:
                last_err = e
                if attempt < 2:
                    time.sleep(3 * (attempt + 1))  # 3с, 6с
                else:
                    raise last_err
        text = response.text.strip()

        # Извлекаем JSON из ответа
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
        else:
            result = json.loads(text)

        # Добавляем обработанные показатели
        result['indicators'] = []
        for key, value in indicators.items():
            if key in REFERENCE_RANGES:
                ref = REFERENCE_RANGES[key]
                st = get_status(key, value, gender)
                result['indicators'].append({
                    'key': key,
                    'name': ref['name'],
                    'value': value,
                    'unit': ref['unit'],
                    'status': st,
                    'ref_min': ref[gender][0],
                    'ref_max': ref[gender][1],
                })

        return result

    except Exception as e:
        print(f"AI error: {e}")
        # Fallback без AI
        ind_list = []
        for key, value in indicators.items():
            if key in REFERENCE_RANGES:
                ref = REFERENCE_RANGES[key]
                st = get_status(key, value, gender)
                ind_list.append({
                    'key': key,
                    'name': ref['name'],
                    'value': value,
                    'unit': ref['unit'],
                    'status': st,
                    'ref_min': ref[gender][0],
                    'ref_max': ref[gender][1],
                })
        bad = [i for i in ind_list if i['status'] == 'bad']
        return {
            'summary': f"Найдено {len(indicators)} показателей. {len(bad)} требуют внимания.",
            'attention_count': len([i for i in ind_list if i['status'] in ['bad','warn']]),
            'ok_count': len([i for i in ind_list if i['status'] == 'ok']),
            'patterns': [],
            'risks': [],
            'protocol': [],
            'lifestyle': {'nutrition': '', 'supplements': '', 'tests': '', 'doctor': ''},
            'positive': '',
            'indicators': ind_list,
            'error': str(e)
        }
