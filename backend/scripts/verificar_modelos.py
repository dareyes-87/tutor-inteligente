"""
Verificación previa de los modelos LLM configurados (principales y de respaldo).

1. Consulta el catálogo /v1/models de Together y confirma que cada modelo existe.
2. Hace una petición mínima (max_tokens=5) a cada uno y mide la latencia.
3. Imprime una tabla OK / FALLA y sale con código != 0 si algún modelo
   PRINCIPAL no responde (un respaldo caído solo se advierte).

Usa la configuración del backend (app/config.py: LLM_MODEL*, *_FALLBACKS,
TOGETHER_API_KEY). Solo depende de httpx y pydantic-settings, así que corre:
    desde el host (raíz del repo, lee ./.env):  python3 backend/scripts/verificar_modelos.py
    dentro del contenedor:                      docker compose exec backend python scripts/verificar_modelos.py

Costo: ~6 llamadas de ~20 tokens → muy por debajo de $0.01 (se imprime al final).
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import httpx  # noqa: E402

from app.config import cadenas_modelos, settings  # noqa: E402
from costos_llm import Presupuesto, PresupuestoAgotado, agregar_argumento_max_usd, catalogo_modelos  # noqa: E402

URL_CHAT = "https://api.together.xyz/v1/chat/completions"


def probar(modelo: str, presupuesto: Presupuesto) -> tuple[bool, float, str]:
    """(ok, segundos, detalle). OK = HTTP 200 (el contenido puede venir vacío
    en modelos de razonamiento con max_tokens tan bajo; no importa aquí)."""
    presupuesto.verificar()
    inicio = time.monotonic()
    try:
        resp = httpx.post(
            URL_CHAT,
            headers={"Authorization": f"Bearer {settings.TOGETHER_API_KEY}"},
            json={"model": modelo, "messages": [{"role": "user", "content": "Di hola."}], "max_tokens": 5},
            timeout=45,
        )
    except httpx.HTTPError as e:
        return False, time.monotonic() - inicio, f"{type(e).__name__}"
    segundos = time.monotonic() - inicio
    if resp.status_code != 200:
        try:
            error = resp.json().get("error", {})
            detalle = error.get("code") or error.get("message", "")[:60]
        except ValueError:
            detalle = resp.text[:60]
        return False, segundos, f"HTTP {resp.status_code} {detalle}"
    uso = resp.json().get("usage") or {}
    presupuesto.registrar(modelo, uso.get("prompt_tokens", 0), uso.get("completion_tokens", 0))
    return True, segundos, "responde"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    agregar_argumento_max_usd(parser, defecto=0.01)
    args = parser.parse_args()

    if not settings.TOGETHER_API_KEY:
        print("FALLA: TOGETHER_API_KEY no está definida.")
        return 2

    catalogo = catalogo_modelos(settings.TOGETHER_API_KEY)
    presupuesto = Presupuesto(args.max_usd, catalogo=catalogo)

    filas = []  # (rol, tipo, modelo, en_catalogo, ok, segundos, detalle)
    probados: dict[str, tuple[bool, float, str]] = {}
    for rol, cadena in cadenas_modelos().items():
        for i, modelo in enumerate(cadena):
            if modelo not in probados:
                try:
                    probados[modelo] = probar(modelo, presupuesto)
                except PresupuestoAgotado as e:
                    probados[modelo] = (False, 0.0, str(e))
            filas.append((rol, "principal" if i == 0 else f"respaldo {i}", modelo, modelo in catalogo, *probados[modelo]))

    print(f"{'rol':12} {'tipo':11} {'modelo':42} {'catálogo':9} {'estado':6} {'latencia':>8}  {'$/M in-out':>12}  detalle")
    for rol, tipo, modelo, en_cat, ok, seg, detalle in filas:
        p_in, p_out = presupuesto.precio(modelo)
        print(
            f"{rol:12} {tipo:11} {modelo:42} {'sí' if en_cat else 'NO':9} {'OK' if ok else 'FALLA':6} "
            f"{seg:7.2f}s  {p_in:5.2f}-{p_out:<5.2f}  {detalle}"
        )
    presupuesto.imprimir_resumen()

    principales_caidos = [m for _, tipo, m, _, ok, _, _ in filas if tipo == "principal" and not ok]
    respaldos_caidos = [m for _, tipo, m, _, ok, _, _ in filas if tipo != "principal" and not ok]
    if respaldos_caidos:
        print(f"\nADVERTENCIA: respaldo(s) no disponible(s): {', '.join(sorted(set(respaldos_caidos)))}")
    if principales_caidos:
        print(f"\nFALLA: modelo(s) principal(es) no disponible(s): {', '.join(sorted(set(principales_caidos)))}")
        return 1
    print("\nOK: todos los modelos principales responden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
