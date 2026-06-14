import google.generativeai as genai
import json
import re
import os

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

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

SYSTEM_PROMPT = """Ты — медицинский аналитик Meridian, платформы превентивной медицины.

Твоя задача: дать ГЛУБОКИЙ СИСТЕМНЫЙ РАЗБОР анализов крови на основе:
- Доказательной медицины (PubMed, JAMA, NEJM, NIH, Lancet)
- Функциональной медицины (оптимальные диапазоны, а не только референсные)
- Паттернов между показателями которые обычный врач не замечает

СТИЛЬ ОТВЕТА:
- Говори просто и человечно, без медицинского жаргона
- Объясняй что значит показатель для жизни человека (энергия, сон, концентрация)
- Не пугай, но говори правду
- Конкретные действия, не общие слова

СТРУКТУРА ОТВЕТА (строго в формате JSON):
{
  "summary": "2-3 предложения: главное что происходит в теле прямо сейчас",
  "attention_count": число показателей требующих внимания,
  "ok_count": число показателей в норме,
  "patterns": [
    {
      "title": "название паттерна",
      "description": "объяснение простым языком что это значит",
      "indicators": ["список показателей в этом паттерне"]
    }
  ],
  "risks": [
    {
      "level": "high/medium/low",
      "title": "риск",
      "description": "что может произойти через 5-10 лет если не действовать",
      "science": "ссылка на исследование или источник"
    }
  ],
  "protocol": [
    {
      "priority": 1,
      "action": "конкретное действие",
      "reason": "почему это важно",
      "timeframe": "когда ждать результат"
    }
  ],
  "lifestyle": {
    "nutrition": "конкретные рекомендации по питанию",
    "supplements": "что принимать и в каких дозах",
    "tests": "что пересдать или сдать дополнительно",
    "doctor": "к какому врачу обратиться если нужно"
  },
  "positive": "что хорошего в анализах — обязательно найти что-то позитивное"
}"""

def analyze_with_ai(indicators: dict, gender: str, age: int, name: str, raw_text: str = "") -> dict:
    """Отправляет показатели в Gemini и получает медицинский разбор."""

    gender_text = "мужчина" if gender == 'm' else "женщина"
    summary = build_indicators_summary(indicators, gender)

    prompt = f"""{SYSTEM_PROMPT}

ПАЦИЕНТ: {name}, {age} лет, {gender_text}

РЕЗУЛЬТАТЫ АНАЛИЗОВ:
{summary}

{f"ДОПОЛНИТЕЛЬНЫЙ КОНТЕКСТ ИЗ PDF:
{raw_text[:1500]}" if raw_text else ""}

Дай системный разбор. Найди паттерны между показателями. Объясни простым языком.
Верни строго валидный JSON."""

    try:
        response = model.generate_content(prompt)
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
