import pdfplumber
import re
from typing import Optional

# Словарь показателей для поиска в PDF
MARKER_ALIASES = {
    'hemoglobin':    ['гемоглобин', 'hemoglobin', 'hgb', 'hb'],
    'hematocrit':    ['гематокрит', 'hematocrit', 'hct'],
    'platelets':     ['тромбоциты', 'platelets', 'plt'],
    'esr':           ['соэ', 'soe', 'esr', 'скорость оседания'],
    'leukocytes':    ['лейкоциты', 'wbc', 'leukocytes'],
    'erythrocytes':  ['эритроциты', 'rbc', 'erythrocytes'],
    'glucose':       ['глюкоза', 'glucose', 'сахар'],
    'cholesterol':   ['холестерин', 'cholesterol', 'общий холестерин'],
    'hdl':           ['hdl', 'лпвп', 'холестерин лпвп', 'липопротеин высокой'],
    'ldl':           ['ldl', 'лпнп', 'холестерин лпнп', 'липопротеин низкой'],
    'triglycerides': ['триглицериды', 'triglycerides', 'tg'],
    'insulin':       ['инсулин', 'insulin'],
    'hba1c':         ['гликированный', 'hba1c', 'гликозилированный', 'hemoglobin a1c'],
    'ferritin':      ['ферритин', 'ferritin'],
    'iron':          ['железо сыворот', 'serum iron', 'железо,'],
    'tibc':          ['ожсс', 'tibc', 'общая железосвязывающая'],
    'transferrin':   ['трансферрин', 'transferrin'],
    'vitamin_d':     ['витамин d', '25-oh', '25(oh)', 'кальцидиол', 'cholecalciferol'],
    'b12':           ['витамин b12', 'b12', 'кобаламин', 'cobalamin'],
    'folate':        ['фолат', 'фолиевая', 'folate', 'folic acid'],
    'tsh':           ['ттг', 'tsh', 'тиреотропный'],
    't3_free':       ['т3 свободный', 'ft3', 'free t3', 'трийодтиронин св'],
    't4_free':       ['т4 свободный', 'ft4', 'free t4', 'тироксин св'],
    'tpo_ab':        ['ат-тпо', 'anti-tpo', 'тиреопероксидаза'],
    'crp':           ['срб', 'crp', 'c-реактивный', 'c reactive'],
    'alt':           ['алт', 'alt', 'аланинаминотрансфераза'],
    'ast':           ['аст', 'ast', 'аспартатаминотрансфераза'],
    'ggt':           ['ггт', 'ggt', 'гамма-глутамил'],
    'bilirubin':     ['билирубин общий', 'total bilirubin', 'bilirubin total'],
    'albumin':       ['альбумин', 'albumin'],
    'creatinine':    ['креатинин', 'creatinine'],
    'urea':          ['мочевина', 'urea', 'bun'],
    'uric_acid':     ['мочевая кислота', 'uric acid', 'urate'],
    'cortisol':      ['кортизол', 'cortisol'],
    'testosterone':  ['тестостерон', 'testosterone'],
    'estradiol':     ['эстрадиол', 'estradiol', 'e2'],
    'progesterone':  ['прогестерон', 'progesterone'],
    'vitamin_b9':    ['витамин b9', 'фолиевая кислота'],
    'magnesium':     ['магний', 'magnesium', 'mg'],
    'calcium':       ['кальций', 'calcium', 'ca'],
    'potassium':     ['калий', 'potassium', 'k '],
    'sodium':        ['натрий', 'sodium', 'na '],
    'phosphorus':    ['фосфор', 'phosphorus'],
    'zinc':          ['цинк', 'zinc', 'zn'],
    'omega3':        ['омега-3', 'omega-3', 'dha', 'epa'],
    'igf1':          ['igf-1', 'инсулиноподобный', 'соматомедин', 'igf1'],
    'dhea':          ['дгэа', 'dhea', 'дегидроэпиандростерон', 'дгэа-с'],
    # Развёрнутый ОАК
    'leukocytes':    ['лейкоциты', 'wbc', 'leukocytes', 'лейк'],
    'erythrocytes':  ['эритроциты', 'rbc', 'erythrocytes', 'эритр'],
    'mcv':           ['mcv', 'средний объём эритр', 'ср. объём'],
    'mch':           ['mch', 'среднее содержание hb', 'ср. содержание гемоглобина'],
    'mchc':          ['mchc', 'средняя концентрация hb', 'ср. конц. гемоглобина'],
    'rdw':           ['rdw', 'анизоцитоз', 'ширина распределения эритр'],
    'neutrophils':   ['нейтрофилы', 'neutrophils', 'нейтр', 'neu'],
    'lymphocytes':   ['лимфоциты', 'lymphocytes', 'лимф', 'lym'],
    'monocytes':     ['моноциты', 'monocytes', 'моноц', 'mon'],
    'eosinophils':   ['эозинофилы', 'eosinophils', 'эозин', 'eos'],
    'basophils':     ['базофилы', 'basophils', 'базоф', 'bas'],
    # Липиды
    'hdl':           ['hdl', 'лпвп', 'холестерин лпвп', 'липопротеин высокой', 'лпвп-хс'],
    'ldl':           ['ldl', 'лпнп', 'холестерин лпнп', 'липопротеин низкой', 'лпнп-хс'],
    'triglycerides': ['триглицериды', 'triglycerides', 'тг'],
    'hba1c':         ['гликированный', 'hba1c', 'гликозилированный', 'hemoglobin a1c', 'hba'],
    # Почки
    'creatinine':    ['креатинин', 'creatinine', 'креат'],
    'urea':          ['мочевина', 'urea', 'bun', 'мочев'],
    # Прочее
    'ggt':           ['ггт', 'ggt', 'гамма-глутамил', 'γ-гт'],
    'bilirubin':     ['билирубин общий', 'total bilirubin', 'bilirubin total', 'билирубин общ'],
    'albumin':       ['альбумин', 'albumin', 'albumen'],
    'potassium':     ['калий', 'potassium', 'k '],
    'sodium':        ['натрий', 'sodium', 'na '],
    'phosphorus':    ['фосфор', 'phosphorus', 'фосф'],
    'homocysteine':  ['гомоцистеин', 'homocysteine', 'hcy'],
    'prolactin':     ['пролактин', 'prolactin'],
    'estradiol':     ['эстрадиол', 'estradiol', 'e2'],
    'omega3_index':  ['омега-3 индекс', 'omega-3 index', 'индекс омега'],
}

def extract_number(text: str) -> Optional[float]:
    """Извлекает первое число из строки."""
    text = text.replace(',', '.').replace(' ', '')
    m = re.search(r'(\d+\.?\d*)', text)
    return float(m.group(1)) if m else None

def extract_text_pymupdf(file_path: str) -> str:
    """Резервное извлечение текста через pymupdf — лучше справляется со сложными PDF."""
    try:
        import fitz
        doc = fitz.open(file_path)
        text = ""
        for page in doc:
            text += page.get_text() + "\n"
        doc.close()
        return text
    except Exception as e:
        print(f"pymupdf error: {e}")
        return ""

def parse_pdf(file_path: str) -> dict:
    """Парсит PDF и возвращает словарь найденных показателей."""
    results = {}
    raw_text = ""

    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
                raw_text += text + "\n"

                # Пробуем таблицы
                for table in page.extract_tables():
                    if not table:
                        continue
                    for row in table:
                        if not row:
                            continue
                        row_text = ' '.join([str(c).lower() for c in row if c])
                        for key, aliases in MARKER_ALIASES.items():
                            if key in results:
                                continue
                            for alias in aliases:
                                if alias in row_text:
                                    for cell in row:
                                        if cell:
                                            val = extract_number(str(cell))
                                            if val and val > 0:
                                                results[key] = val
                                                break
                                    break

    except Exception as e:
        print(f"pdfplumber error: {e}")

    # Если pdfplumber не извлёк текст — пробуем pymupdf
    if len(raw_text.strip()) < 50:
        print("pdfplumber got no text, trying pymupdf...")
        raw_text = extract_text_pymupdf(file_path)

    # Построчный поиск в тексте
    lines = raw_text.lower().split('\n')
    for line in lines:
        for key, aliases in MARKER_ALIASES.items():
            if key in results:
                continue
            for alias in aliases:
                if alias in line:
                    val = extract_number(line)
                    if val and val > 0:
                        results[key] = val
                    break

    print(f"PDF parsed: {len(results)} indicators, text length: {len(raw_text)}")

    return {
        'indicators': results,
        'raw_text': raw_text[:8000],  # увеличено с 3000 до 8000 символов
        'found_count': len(results)
    }
