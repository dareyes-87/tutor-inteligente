"""
Verificación cuantitativa del guardrail de actividades inválidas (Bug A: hueco
redundante en "completar"; Bug B: respuesta = símbolo matemático especial no
tecleable en "completar"/"respuesta_corta"). Genera actividades repetidas veces
sobre varias lecciones de Matemáticas y reporta:
  - cuántas veces el LLM intentó generar una actividad inválida (símbolo o hueco
    redundante), pese a las instrucciones del prompt (capa 1)
  - cuántas de esas el guardrail (capa 2, determinística) forzó a regenerar
    como opcion_multiple, y con qué éxito
  - una verificación final independiente: ninguna actividad "completar" o
    "respuesta_corta" servida debe tener un símbolo especial como respuesta ni
    un hueco redundante

Uso:
    docker compose exec backend python3 scripts/debug/verificar_fix_actividades_invalidas.py

Script de un solo uso para esta verificación; no forma parte de la app.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.usuario import Usuario
from app.models.actividad import TipoActividad
import app.modules.actividades.generator as generator_mod
from app.modules.actividades.generator import _contiene_simbolo_especial, _hueco_es_redundante
from app.modules.actividades.service import crear_actividad

ITERACIONES = 15
TIPOS_VULNERABLES = [TipoActividad.completar, TipoActividad.respuesta_corta]

# (leccion_id, descripción) — 249 es el caso original del bug reportado;
# 250 y 254 se eligieron porque sus fragmentos mencionan comparaciones/
# desigualdades ("menor que el divisor", magnitudes), para confirmar que el
# fix generaliza más allá de "pertenencia y subconjuntos".
LECCIONES = [
    (249, "Conjuntos y operaciones (pertenencia, subconjuntos, unión, intersección)"),
    (250, "Números Naturales (aproximación, comparación de magnitudes)"),
    (254, "Matemáticas divertidas / división (comparaciones 'menor que el divisor')"),
]

# Contadores globales, llenados vía monkeypatch de _actividad_invalida.
contador = {
    "validaciones": 0,
    "invalidas_simbolo": 0,
    "invalidas_hueco": 0,
}
_original_actividad_invalida = generator_mod._actividad_invalida


def _actividad_invalida_instrumentada(tipo, result):
    razon = _original_actividad_invalida(tipo, result)
    if tipo in TIPOS_VULNERABLES:
        contador["validaciones"] += 1
    if razon:
        if "símbolo" in razon:
            contador["invalidas_simbolo"] += 1
        elif "redundante" in razon:
            contador["invalidas_hueco"] += 1
    return razon


generator_mod._actividad_invalida = _actividad_invalida_instrumentada


def _verificacion_independiente(actividad) -> str | None:
    """Chequeo final, SIN depender del guardrail: ¿esta actividad servida
    tiene realmente un problema? None si está bien.

    Revisa también el texto VISIBLE (oración/pregunta), no solo la respuesta:
    el LLM puede esquivar "no uses el símbolo como respuesta" escribiéndolo en
    la oración y dejando un hueco/respuesta inventada sin sentido en otro lado
    (visto en producción: oración con "∈" visible + hueco con respuesta "e").
    """
    if actividad.tipo not in TIPOS_VULNERABLES:
        return None
    respuesta = str(actividad.respuesta_correcta.get("respuesta_correcta", ""))
    texto_visible = (
        actividad.contenido.get("oracion", "")
        if actividad.tipo == TipoActividad.completar
        else actividad.contenido.get("pregunta", "")
    )
    if _contiene_simbolo_especial(respuesta):
        return f"respuesta '{respuesta}' contiene un símbolo especial"
    if _contiene_simbolo_especial(texto_visible):
        return f"el texto visible contiene un símbolo especial: '{texto_visible}'"
    if actividad.tipo == TipoActividad.completar and _hueco_es_redundante(texto_visible, respuesta):
        return f"hueco redundante en '{texto_visible}'"
    return None


async def main():
    async with AsyncSessionLocal() as db:
        estudiante = (
            await db.execute(select(Usuario).where(Usuario.grado_id == 1).limit(1))
        ).scalars().first()
        print(f"Estudiante de prueba: {estudiante.username}\n")

        fallos_reales = []
        forzadas_a_opcion_multiple = 0
        regeneracion_fallida = 0
        total_none = 0
        total_intentos = 0

        for leccion_id, descripcion in LECCIONES:
            print(f"=== Lección {leccion_id}: {descripcion} ===")
            por_leccion = {"opcion_multiple_forzado": 0, "none": 0, "ok": 0}
            for i in range(ITERACIONES):
                for tipo in TIPOS_VULNERABLES:
                    total_intentos += 1
                    actividad = await crear_actividad(
                        db,
                        asignatura_id=2,
                        tipo=tipo,
                        estudiante=estudiante,
                        leccion_id=leccion_id,
                    )
                    if actividad is None:
                        total_none += 1
                        por_leccion["none"] += 1
                        continue
                    por_leccion["ok"] += 1
                    if actividad.tipo != tipo:
                        forzadas_a_opcion_multiple += 1
                        por_leccion["opcion_multiple_forzado"] += 1
                        print(
                            f"  [{i+1}] {tipo.value} → forzado a {actividad.tipo.value} "
                            f"(id={actividad.id})"
                        )
                    problema = _verificacion_independiente(actividad)
                    if problema:
                        fallos_reales.append((leccion_id, tipo.value, actividad.id, problema))
                        print(f"  !!! FALLO REAL id={actividad.id}: {problema}")
            print(f"  Resumen lección {leccion_id}: {por_leccion}\n")

        print("=" * 70)
        print("RESULTADOS AGREGADOS")
        print("=" * 70)
        print(f"Total intentos (completar + respuesta_corta): {total_intentos}")
        print(f"Actividades no generadas (None, fallo de LLM): {total_none}")
        print(f"Validaciones corridas (tipo completar/respuesta_corta): {contador['validaciones']}")
        print(f"  → Inválidas por SÍMBOLO especial detectadas: {contador['invalidas_simbolo']}")
        print(f"  → Inválidas por HUECO redundante detectadas: {contador['invalidas_hueco']}")
        print(f"Forzadas a opcion_multiple por el guardrail: {forzadas_a_opcion_multiple}")
        print(f"Regeneración a opcion_multiple fallida (LLM no respondió): {regeneracion_fallida}")
        print()
        print(f"VERIFICACIÓN INDEPENDIENTE (actividades servidas con el bug real): {len(fallos_reales)}")
        for l, t, aid, problema in fallos_reales:
            print(f"  lección={l} tipo={t} id={aid}: {problema}")
        if not fallos_reales:
            print("  Ninguna actividad servida tiene símbolo especial como respuesta ni hueco redundante. ✅")


if __name__ == "__main__":
    asyncio.run(main())
