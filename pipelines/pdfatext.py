import pdfplumber
from pathlib import Path

# Carpeta raíz de entrada y salida
PDF_ROOT = Path("pdfs")
OUT_ROOT = Path("textos")

# ✅ Ajustes columna
SIDEBAR_X = 200
SPLIT_X = 358.7  # o None

# ✅ Recortes por página (en puntos PDF)
TOP_CUT_FIRST = 70
BOTTOM_CUT_FIRST = 0

TOP_CUT_MIDDLE = 0
BOTTOM_CUT_MIDDLE = 0

TOP_CUT_LAST = 0
BOTTOM_CUT_LAST = 100  # más agresivo para quitar footer/recomendaciones

# ✅ Corte de “header variable” por anclas
ENABLE_ANCHOR_CUT = True
ANCHOR_PADDING = 10  # cuanto “antes” del ancla recortás (en puntos)


def norm_space(s: str) -> str:
    return " ".join((s or "").replace("\u00ad", "").split()).strip()


def build_lines(words, y_tol=2):
    """
    Agrupa por 'doctop' (más estable), evita pegar header/cards.
    """
    for w in words:
        if "doctop" not in w:
            w["doctop"] = w.get("top", 0)

    words = sorted(words, key=lambda w: (w["doctop"], w["x0"]))

    lines = []
    current = []
    last_y = None

    for w in words:
        y = w["doctop"]
        if last_y is None or abs(y - last_y) <= y_tol:
            current.append(w)
            last_y = y if last_y is None else (last_y + y) / 2
        else:
            current.sort(key=lambda a: a["x0"])
            lines.append(" ".join(x["text"] for x in current))
            current = [w]
            last_y = y

    if current:
        current.sort(key=lambda a: a["x0"])
        lines.append(" ".join(x["text"] for x in current))

    return "\n".join(lines)


def find_two_columns_split(words, page_width):
    xs = sorted(set(w["x0"] for w in words))
    if len(xs) < 10:
        return page_width / 2

    gaps = [(xs[i + 1] - xs[i], xs[i], xs[i + 1]) for i in range(len(xs) - 1)]
    gaps.sort(reverse=True, key=lambda t: t[0])

    for gap, a, b in gaps[:40]:
        mid = (a + b) / 2
        if page_width * 0.35 < mid < page_width * 0.90 and gap > 25:
            return mid

    return page_width / 2


def parse_otro_flags(otros_folder: str):
    """
    Soporta:
    - "sin-extras"
    - "con-aire-acondicionado"
    - "con-cristales-electricos"
    - "con-aire-acondicionado__con-cristales-electricos"
    - "aire__cristales" (nuevo)
    """
    s = (otros_folder or "").lower()

    aire = ("con-aire-acondicionado" in s) or ("aire" in s)
    cristales = ("con-cristales-electricos" in s) or ("cristales" in s) or ("vidrios" in s) or ("alzacristales" in s)

    if "aire__cristales" in s or "aire-cristales" in s:
        aire = True
        cristales = True

    return aire, cristales


def words_text(w):
    return norm_space(w.get("text", ""))


def find_anchor_y(words):
    """
    Busca anclas típicas del header/overlay y devuelve su Y (doctop/top).
    No usa 'Ad' para no comerse autos.
    """
    anchors_phrase = [
        ["ordenar", "por"],
        ["creá", "tu", "cuenta"],
        ["crea", "tu", "cuenta"],       # por si viene sin acento
        ["ingresá"],
        ["ingresa"],                   # por si viene sin acento
        ["mis", "compras"],
        ["ir", "a", "la", "tienda"],
    ]

    toks = []
    for w in words:
        t = words_text(w).lower()
        if not t:
            continue
        y = w.get("doctop", w.get("top", 0))
        toks.append((t, y))

    tokens_only = [t for t, _ in toks]
    ys_only = [y for _, y in toks]

    for phrase in anchors_phrase:
        L = len(phrase)
        for i in range(0, len(tokens_only) - L + 1):
            if tokens_only[i:i + L] == phrase:
                return ys_only[i]

    return None


def drop_header_until_anchor(words, padding=10):
    """
    Si encuentra ancla, descarta todo lo que esté por arriba de esa Y (menos padding).
    """
    y_anchor = find_anchor_y(words)
    if y_anchor is None:
        return words
    y_cut = max(0, y_anchor - padding)
    return [w for w in words if w.get("doctop", w.get("top", 0)) >= y_cut]


total_pdfs = 0

# pdfs/<marca>/<combustible>/<transmision>/<direccion>/<otrosFolder>/*.pdf
pdf_files = sorted(PDF_ROOT.glob("*/*/*/*/*/*.pdf"))

if not pdf_files:
    print(f"⚠️ No se encontraron PDFs con estructura: {PDF_ROOT}/<marca>/<combustible>/<transmision>/<direccion>/<otros>/*.pdf")
else:
    print(f"📦 PDFs encontrados: {len(pdf_files)}")

for pdf_path in pdf_files:
    total_pdfs += 1

    try:
        otros_folder = pdf_path.parent.name
        direccion = pdf_path.parent.parent.name
        transmision = pdf_path.parent.parent.parent.name
        combustible = pdf_path.parent.parent.parent.parent.name
        marca = pdf_path.parent.parent.parent.parent.parent.name
    except Exception:
        print(f"⚠️ Ruta inesperada, salteo: {pdf_path}")
        continue

    aire, cristales = parse_otro_flags(otros_folder)

    out_dir = OUT_ROOT / marca / combustible / transmision / direccion / otros_folder
    out_dir.mkdir(parents=True, exist_ok=True)

    out_txt = out_dir / f"{pdf_path.stem}.txt"
    print(f"Procesando: {pdf_path}")

    try:
        with pdfplumber.open(pdf_path) as pdf, open(out_txt, "w", encoding="utf-8") as f:
            # Header con metadata
            f.write("--- META ---\n")
            f.write(f"marca={marca}\n")
            f.write(f"combustible={combustible}\n")
            f.write(f"transmision={transmision}\n")
            f.write(f"direccion={direccion}\n")
            f.write(f"otros_folder={otros_folder}\n")
            f.write(f"aire={str(aire).lower()}\n")
            f.write(f"cristales={str(cristales).lower()}\n")
            f.write("--- /META ---\n\n")

            n_pages = len(pdf.pages)

            for i, page in enumerate(pdf.pages, start=1):
                f.write(f"\n--- PAGE {i} ---\n")

                w, h = page.width, page.height

                # ✅ recorte dinámico por página
                if i == 1:
                    y0 = TOP_CUT_FIRST
                    y1 = h - BOTTOM_CUT_FIRST
                elif i == n_pages:
                    y0 = TOP_CUT_LAST
                    y1 = h - BOTTOM_CUT_LAST
                else:
                    y0 = TOP_CUT_MIDDLE
                    y1 = h - BOTTOM_CUT_MIDDLE

                # seguridad
                y0 = max(0, min(y0, h - 1))
                y1 = max(1, min(y1, h))
                if y1 <= y0:
                    y0, y1 = 0, h

                crop = page.crop((0, y0, w, y1))

                # ✅ extracción más estable
                words = crop.extract_words(
                    use_text_flow=True,
                    keep_blank_chars=False,
                    extra_attrs=["doctop"],
                )
                if not words:
                    continue

                # ✅ corte header variable por anclas (solo si está activado)
                if ENABLE_ANCHOR_CUT:
                    words = drop_header_until_anchor(words, padding=ANCHOR_PADDING)

                # ✅ Sidebar manual
                result_words = [wd for wd in words if wd["x0"] >= SIDEBAR_X]

                # ✅ Split manual/auto
                x_split = float(SPLIT_X) if SPLIT_X is not None else find_two_columns_split(result_words, w)

                left_words = [wd for wd in result_words if wd["x0"] < x_split]
                right_words = [wd for wd in result_words if wd["x0"] >= x_split]

                f.write(f"\n--- SETTINGS ---\n")
                f.write(f"SIDEBAR_X = {SIDEBAR_X}\n")
                f.write(f"SPLIT_X   = {x_split:.1f}  ({'MANUAL' if SPLIT_X is not None else 'AUTO'})\n")
                f.write(f"CROP_Y0   = {y0:.1f}\n")
                f.write(f"CROP_Y1   = {y1:.1f}\n")
                f.write(f"ANCHOR_CUT= {str(ENABLE_ANCHOR_CUT).lower()}\n")

                f.write("\n--- RESULTS LEFT ---\n")
                f.write(build_lines(left_words))
                f.write("\n")

                f.write("\n--- RESULTS RIGHT ---\n")
                f.write(build_lines(right_words))
                f.write("\n")

    except Exception as e:
        print(f"❌ Error con {pdf_path.name}: {e}")
        continue

print(f"\n✅ Listo. PDFs procesados: {total_pdfs}")
