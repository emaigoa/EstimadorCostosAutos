import pdfplumber
from pathlib import Path

# Carpeta raíz de entrada y salida
PDF_ROOT = Path("pdfs")
OUT_ROOT = Path("textos")

# Marcas y combustibles a recorrer (ajustá si querés sumar/sacar)
MARCAS = ["volkswagen", "fiat", "renault", "ford", "chevrolet", "peugeot", "toyota", "citroen", "nissan", "honda"]

COMBUSTIBLES = ["nafta", "diesel", "nafta-gnc"]

TOP_CUT = 0
BOTTOM_CUT = 0

# ✅ AJUSTÁ ESTO A MANO (en puntos PDF)
SIDEBAR_X = 200

# ✅ Split manual (poné None para auto)
SPLIT_X = 358.7  # o None


def build_lines(words, y_tol=3):
    words = sorted(words, key=lambda w: (w["top"], w["x0"]))
    lines = []
    current = []
    last_top = None

    for w in words:
        if last_top is None or abs(w["top"] - last_top) <= y_tol:
            current.append(w)
            last_top = w["top"] if last_top is None else (last_top + w["top"]) / 2
        else:
            current = sorted(current, key=lambda a: a["x0"])
            lines.append(" ".join(x["text"] for x in current))
            current = [w]
            last_top = w["top"]

    if current:
        current = sorted(current, key=lambda a: a["x0"])
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


total_pdfs = 0

for marca in MARCAS:
    for combustible in COMBUSTIBLES:
        pdf_dir = PDF_ROOT / marca / combustible
        if not pdf_dir.exists():
            print(f"⚠️ No existe: {pdf_dir} (salteo)")
            continue

        out_dir = OUT_ROOT / marca / combustible
        out_dir.mkdir(parents=True, exist_ok=True)

        pdf_files = sorted(pdf_dir.glob("*.pdf"))
        if not pdf_files:
            print(f"⚠️ Sin PDFs en: {pdf_dir} (salteo)")
            continue

        print(f"\n=== Procesando {marca}/{combustible} ({len(pdf_files)} PDFs) ===")

        for pdf_path in pdf_files:
            total_pdfs += 1
            print(f"Procesando: {pdf_path}")

            out_txt = out_dir / f"{pdf_path.stem}.txt"

            try:
                with pdfplumber.open(pdf_path) as pdf, open(out_txt, "w", encoding="utf-8") as f:
                    for i, page in enumerate(pdf.pages, start=1):
                        f.write(f"\n--- PAGE {i} ---\n")

                        w, h = page.width, page.height
                        y0, y1 = TOP_CUT, h - BOTTOM_CUT

                        crop = page.crop((0, y0, w, y1))
                        words = crop.extract_words()
                        if not words:
                            continue

                        # ✅ 1) Sidebar manual
                        result_words = [wd for wd in words if wd["x0"] >= SIDEBAR_X]

                        # ✅ 2) Split manual o automático
                        if SPLIT_X is not None:
                            x_split = float(SPLIT_X)
                        else:
                            x_split = find_two_columns_split(result_words, w)

                        left_words = [wd for wd in result_words if wd["x0"] < x_split]
                        right_words = [wd for wd in result_words if wd["x0"] >= x_split]

                        f.write(f"\n--- SETTINGS ---\n")
                        f.write(f"SIDEBAR_X = {SIDEBAR_X}\n")
                        f.write(
                            f"SPLIT_X   = {x_split:.1f}  ({'MANUAL' if SPLIT_X is not None else 'AUTO'})\n"
                        )

                        f.write("\n--- RESULTS LEFT ---\n")
                        f.write(build_lines(left_words))
                        f.write("\n")

                        f.write("\n--- RESULTS RIGHT ---\n")
                        f.write(build_lines(right_words))
                        f.write("\n")

            except Exception as e:
                # Si un PDF falla, no corta todo el proceso: sigue con el siguiente
                print(f"❌ Error con {pdf_path.name}: {e}")
                continue

print(f"\n✅ Listo. PDFs procesados: {total_pdfs}")
