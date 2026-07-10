import re, unicodedata
from difflib import SequenceMatcher

_ARTICULOS = ("la", "el", "los", "las", "una", "un", "unas", "unos", "lo")
_STOPWORDS = {"de","la","el","los","las","del","al","y","en","que","es","un","una",
              "por","para","con","se","lo","unos","unas"}

def _norm(t):
    t = unicodedata.normalize("NFKD", t or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower()
    t = re.sub(r"[^\w\s]", " ", t)          # quitar puntuación
    t = re.sub(r"\s+", " ", t).strip()
    # quitar UN artículo inicial
    partes = t.split(" ", 1)
    if len(partes) == 2 and partes[0] in _ARTICULOS:
        t = partes[1]
    elif len(partes) == 1 and partes[0] in _ARTICULOS:
        t = ""
    return t

def _tokens_contenido(t):
    return [w for w in t.split() if w and w not in _STOPWORDS]

def coincide(est, cor, umbral_tokens=0.70, umbral_seq=0.75):
    e, c = _norm(est), _norm(cor)
    detalle = {}
    # Capa 1
    if e and c and e == c:
        return True, "C1-exacta", detalle
    # Capa 2 (contención, guarda longitud minima 3)
    if e and c and (min(len(e), len(c)) >= 3) and (c in e or e in c):
        return True, "C2-contencion", detalle
    # Capa 3 (overlap de tokens de contenido de la ESPERADA presentes en el estudiante)
    te, tset = _tokens_contenido(c), set(_tokens_contenido(e))
    frac = (sum(1 for w in te if w in tset) / len(te)) if te else 0.0
    detalle["tokens_frac"] = round(frac, 3)
    if te and frac >= umbral_tokens:
        return True, "C3-tokens", detalle
    # Capa 4 (SequenceMatcher)
    ratio = SequenceMatcher(None, e, c).ratio()
    detalle["seq_ratio"] = round(ratio, 3)
    if ratio >= umbral_seq:
        return True, "C4-seq", detalle
    return False, "sin-match", detalle

PARES = [
    ("célula", "una célula", True),
    ("la célula", "una célula", True),
    ("celula", "una célula", True),
    ("la unidad más pequeña de vida", "la unidad básica de la vida", True),
    ("fotosíntesis", "la fotosíntesis", True),
    ("gato", "una célula", False),
    ("no sé", "una célula", False),
    ("la unidad más grande del universo", "la unidad básica de la vida", False),
]

print(f"{'ESTUDIANTE':38} {'ESPERADA':32} exp  got  capa        detalle")
ok=0
for est, cor, esperado in PARES:
    got, capa, det = coincide(est, cor)
    marca = "OK" if got == esperado else "XX <<<"
    if got == esperado: ok += 1
    print(f"{est[:37]:38} {cor[:31]:32} {str(esperado):5} {str(got):5} {capa:12} {det}  {marca}")
print(f"\n{ok}/{len(PARES)} correctos")
