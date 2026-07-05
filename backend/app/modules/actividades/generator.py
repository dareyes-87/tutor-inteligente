"""
Generador de actividades: usa el LLM para crear ejercicios
basados en el contenido de los libros (fragmentos RAG).
"""
import logging
import random
import re
import unicodedata

from app.llm.client import llm_client
from app.models.actividad import TipoActividad

logger = logging.getLogger(__name__)

# Símbolos matemáticos especiales: ningún teclado estándar de Android/iOS los
# tiene, así que NUNCA pueden ser la respuesta esperada de "completar" o
# "respuesta_corta" (el estudiante no podría escribirlos). Esas preguntas deben
# generarse como "opcion_multiple" (ver _actividad_invalida / generar_actividad).
SIMBOLOS_ESPECIALES = set("∈∉⊂⊄⊆⊇∪∩≤≥≠")


def _contiene_simbolo_especial(texto: str | None) -> bool:
    return any(c in SIMBOLOS_ESPECIALES for c in (texto or ""))


def _palabras_junto_al_hueco(oracion: str) -> set[str]:
    """Palabras (en minúsculas) inmediatamente antes y después de cada "___"."""
    tokens = re.findall(r"___|\w+", oracion or "")
    palabras = set()
    for i, tok in enumerate(tokens):
        if tok != "___":
            continue
        if i > 0:
            palabras.add(tokens[i - 1].lower())
        if i + 1 < len(tokens):
            palabras.add(tokens[i + 1].lower())
    return palabras


def _hueco_es_redundante(oracion: str | None, respuesta_correcta: str) -> bool:
    """True si la respuesta esperada ya está escrita junto al hueco (___), lo
    que vuelve la oración redundante/sin sentido pedagógico (Bug A: "decimos
    que pertenece (___) al conjunto" con respuesta "pertenece").
    """
    if not oracion or not respuesta_correcta:
        return False
    resp = respuesta_correcta.strip().lower()
    if not resp:
        return False
    for palabra in _palabras_junto_al_hueco(oracion):
        if resp == palabra or resp.rstrip("s") == palabra.rstrip("s"):
            return True
    return False


def _respuesta_es_fragmento_de_palabra(oracion: str | None, respuesta: str | None) -> bool:
    """True si la respuesta de un 'completar' es un PEDAZO de palabra en vez de
    una palabra completa. Caso real: oración "...se encuentra ___ a la
    derecha..." con respuesta "ás" — el LLM partió "más" en "m" + "ás" y dejó
    "ás" como hueco, que no tiene sentido para nadie.

    Dos señales:
      1. La respuesta tiene 3 caracteres o menos y NO es un número ni un
         símbolo matemático: una palabra de 1-3 letras como respuesta a
         completar casi nunca es un término clave con valor pedagógico (y sí
         suele ser un fragmento). Si de verdad lo fuera, regenerar como
         opción múltiple no se pierde nada.
      2. Al colocar la respuesta en el hueco, queda PEGADA a una letra (antes
         o después del "___"), formando una sola palabra: el hueco cortó una
         palabra por la mitad.
    """
    if not respuesta:
        return False
    resp = respuesta.strip()
    if not resp:
        return False
    if len(resp) <= 3 and not resp.isdigit() and not _contiene_simbolo_especial(resp):
        return True
    if not oracion:
        return False
    idx = oracion.find("___")
    if idx == -1:
        return False
    letra_antes = idx > 0 and oracion[idx - 1].isalpha()
    letra_despues = idx + 3 < len(oracion) and oracion[idx + 3].isalpha()
    return bool(letra_antes or letra_despues)


# Frases que delatan que el LLM se basó en un ejercicio/ejemplo/diagrama
# ESPECÍFICO del libro (que el estudiante no tiene a la vista) en vez de en la
# teoría del tema. "por ejemplo" NO matchea (es una muletilla legítima); lo que
# se busca es la referencia a UN ejemplo concreto: "según el ejemplo 2",
# "en el ejercicio", "del diagrama", etc.
_PATRONES_EJEMPLO_LIBRO = (
    re.compile(r"\bseg[uú]n el (ejemplo|ejercicio|diagrama)\b", re.IGNORECASE),
    re.compile(r"\ben el (ejemplo|ejercicio|diagrama)\b", re.IGNORECASE),
    re.compile(r"\bdel (ejemplo|ejercicio|diagrama)\b", re.IGNORECASE),
    re.compile(r"\bejemplo\s+\d", re.IGNORECASE),
)


def _textos_de_actividad(result: dict):
    """Todos los strings visibles/almacenables de la actividad generada
    (pregunta, opciones, explicación, elementos, etc.)."""
    for valor in result.values():
        if isinstance(valor, str):
            yield valor
        elif isinstance(valor, list):
            for elem in valor:
                if isinstance(elem, str):
                    yield elem


def _referencia_a_ejemplo_del_libro(result: dict) -> str | None:
    """Devuelve la frase que delata dependencia de un ejercicio específico del
    libro, o None. Caso real: una actividad V/F sobre "los elementos de P
    pertenecen a C" donde P y C eran conjuntos del diagrama de Venn de un
    ejercicio del libro (imposible de responder sin el libro abierto), y la
    explicación decía "Según el ejemplo 2 del libro...". El filtro
    es_ejercicio_del_libro (pre-generación) no captura estos fragmentos porque
    no llevan encabezados de ejercicio; esto revisa el OUTPUT del LLM."""
    for texto in _textos_de_actividad(result):
        for patron in _PATRONES_EJEMPLO_LIBRO:
            m = patron.search(texto)
            if m:
                return m.group(0)
    return None


# ============================================================================
# Aritmética, valor posicional y rango numérico por grado (Matemáticas).
# Los LLM no saben hacer aritmética de forma confiable: esto es una
# limitación conocida, así que NO se confía en el LLM para verificar sus
# propios resultados numéricos — se calcula con Python.
# ============================================================================

# Stems (no palabras completas) para cubrir cualquier conjugación del verbo
# ("suma", "sumar", "suman", "sumamos", "sumando" contienen todos "suma") sin
# depender de tildes: se comparan contra el texto ya normalizado (sin
# acentos) — ver `_detectar_operacion`. Caso real: "¿cuál es el resultado de
# SUMAR...?" sí matcheaba, pero "si se SUMAN los números..." no, porque la
# lista solo tenía el infinitivo "sumar".
_PALABRAS_SUMA = ("suma", "adicion", "agregar")
_PALABRAS_RESTA = ("resta", "diferencia", "sustrac")
_PALABRAS_MULT = ("multiplic", "producto")
_PALABRAS_DIV = ("divid", "divisi", "cociente")


def _limpiar_numero(texto: str) -> int | None:
    """"3,458,057" / "3.458.057" / "3458057" -> 3458057. None si no queda un
    entero limpio (los ejercicios de este dominio son enteros, no decimales)."""
    limpio = re.sub(r"[.,\s]", "", texto)
    try:
        return int(limpio)
    except ValueError:
        return None


# "1-3 dígitos, luego uno o más grupos de EXACTAMENTE 3 dígitos separados por
# espacio/coma/punto" (los libros de Guatemala escriben miles con espacio:
# "5 746 252"). Solo agrupa cuando el patrón de miles es exacto (grupos de 3);
# así NO fusiona números distintos en una enumeración tipo "3458057, 1875352"
# (donde tras la coma no hay exactamente 3 dígitos, sino el número completo).
_PATRON_NUMERO = re.compile(r"\d{1,3}(?:[ .,]\d{3})+|\d+")


def _extraer_numeros(texto: str) -> list[int]:
    """Números (enteros) mencionados en el texto, en orden de aparición,
    tolerando separadores de miles con espacio, coma o punto."""
    crudos = _PATRON_NUMERO.findall(texto)
    numeros = [n for n in (_limpiar_numero(c) for c in crudos) if n is not None]
    return numeros


def _valor_numerico_de(texto: str | None) -> int | None:
    """Interpreta un texto como UN SOLO número completo (para comparar una
    opción/respuesta contra un resultado calculado). None si el texto no es
    puramente numérico (no aplica la verificación, por diseño conservador)."""
    if not isinstance(texto, str) or not texto.strip():
        return None
    numeros = _extraer_numeros(texto)
    return numeros[0] if len(numeros) == 1 else None


def _detectar_operacion(texto: str) -> str | None:
    t = _normalizar_pregunta(texto)  # minúsculas y sin tildes
    if any(p in t for p in _PALABRAS_SUMA):
        return "suma"
    if any(p in t for p in _PALABRAS_RESTA):
        return "resta"
    if any(p in t for p in _PALABRAS_MULT):
        return "multiplicacion"
    if any(p in t for p in _PALABRAS_DIV):
        return "division"
    return None


def _calcular(operacion: str, numeros: list[int]) -> int | float | None:
    if len(numeros) < 2:
        return None
    if operacion == "suma":
        return sum(numeros)
    if operacion == "resta":
        return numeros[0] - numeros[1]
    if operacion == "multiplicacion":
        return numeros[0] * numeros[1]
    if operacion == "division":
        return numeros[0] / numeros[1] if numeros[1] != 0 else None
    return None


def _detectar_operador_simbolo(texto: str) -> str | None:
    """Como `_detectar_operacion`, pero por el SÍMBOLO en vez de la palabra
    (para ecuaciones tipo "3 + 4 = 7" sin la palabra "suma")."""
    if "+" in texto:
        return "suma"
    if "×" in texto or "*" in texto or re.search(r"\d\s*x\s*\d", texto, re.IGNORECASE):
        return "multiplicacion"
    if "÷" in texto or "/" in texto:
        return "division"
    if "-" in texto:
        return "resta"
    return None


def _evaluar_ecuacion(texto: str, operacion_pista: str | None = None) -> tuple[bool, int | float] | None:
    """Evalúa si `texto` afirma un resultado aritmético cierto o falso, en
    cualquiera de dos formas en las que el LLM las redacta:
      - Ecuación con signo "=": "3458057 + 1875352 + 675374 = 6008783".
      - Afirmación en prosa (sin "="): "La suma de 3458057, 1875352 y 675374
        es 6008783" (operandos = todos los números menos el último).
    Devuelve (es_cierta, resultado_real), o None si `texto` no tiene forma
    evaluable (menos de 2 operandos + 1 resultado, u operación no detectada).
    """
    operacion = operacion_pista or _detectar_operacion(texto) or _detectar_operador_simbolo(texto)
    if operacion is None:
        return None
    if "=" in texto:
        izquierda, _, derecha = texto.partition("=")
        operandos = _extraer_numeros(izquierda)
        declarado = _valor_numerico_de(derecha)
    else:
        numeros = _extraer_numeros(texto)
        if len(numeros) < 3:
            return None
        *operandos, declarado = numeros
    if len(operandos) < 2 or declarado is None:
        return None
    real = _calcular(operacion, operandos)
    if real is None:
        return None
    return (real == declarado, real)


def _verificar_aritmetica(tipo: TipoActividad, result: dict) -> str | None:
    """Guardrail determinístico: si la pregunta/afirmación/opciones plantean
    una operación aritmética explícita (sumar/restar/multiplicar/dividir)
    sobre 2+ números, se CALCULA con Python y se compara contra lo que el LLM
    marcó como correcto.

    Casos reales detectados:
      - Opción múltiple con el resultado suelto en cada opción ("el
        resultado de sumar 3458057, 1875352 y 675374" con 4 opciones
        numéricas): NINGUNA coincidía con el resultado real — el LLM inventó
        números cercanos entre sí y marcó uno como correcto.
      - Opción múltiple con la ECUACIÓN COMPLETA en cada opción ("3458057 +
        1875352 + 675374 = 6008783", "...= 6009000", ...): la pregunta sola
        no tiene los operandos (están dentro de las opciones), así que hay
        que evaluar cada opción como su propia ecuación. Caso real: el LLM
        marcó como correcta una opción cuya ecuación es FALSA (dijo que el
        resultado "aproximado" era el resultado real, confundiendo
        aproximación con el cálculo exacto).
      - Respuesta corta con "5000" para un cálculo cuyo resultado real era
        distinto.
    """
    if tipo == TipoActividad.opcion_multiple:
        opciones = result.get("opciones")
        pregunta = result.get("pregunta") or ""
        if isinstance(opciones, list):
            # Cada opción trae SU PROPIA afirmación numérica completa
            # (operandos + resultado), como ecuación ("A + B = R") o en
            # prosa ("La suma de A y B es R"): se evalúa cada una por
            # separado. Se exige que al menos 2 opciones sean evaluables así
            # para no disparar con un número suelto que caiga por casualidad.
            pista = _detectar_operacion(pregunta)
            evaluaciones = [
                (o, _evaluar_ecuacion(o, pista)) for o in opciones if isinstance(o, str)
            ]
            evaluables = [(o, ev) for o, ev in evaluaciones if ev is not None]
            if len(evaluables) >= 2:
                ciertas = [o for o, (es_cierta, _real) in evaluables if es_cierta]
                if not ciertas:
                    _, (_, real) = evaluables[0]
                    return (
                        f"ninguna opción es matemáticamente correcta "
                        f"(resultado real: {real}); el LLM probablemente calculó mal"
                    )
                respuesta_correcta = result.get("respuesta_correcta")
                if respuesta_correcta not in ciertas:
                    return (
                        f"la opción marcada como correcta ('{respuesta_correcta}') es una "
                        f"afirmación FALSA; la(s) opción(es) matemáticamente correcta(s) "
                        f"son: {ciertas}"
                    )
                return None
            # Menos de 2 opciones evaluables como afirmación propia: seguir
            # con el camino normal (números sueltos, operandos en la pregunta).

    texto = _texto_pregunta(result)
    if not texto:
        return None
    operacion = _detectar_operacion(texto)
    if operacion is None:
        return None

    if tipo == TipoActividad.verdadero_falso:
        # La afirmación suele declarar el resultado dentro del propio texto
        # ("la suma de 3 y 4 es 8"): los operandos son todos los números
        # menos el último (el resultado afirmado).
        numeros = _extraer_numeros(texto)
        if len(numeros) < 3:
            return None
        *operandos, resultado_afirmado = numeros
        esperado = _calcular(operacion, operandos)
        if esperado is None:
            return None
        es_verdadero_real = resultado_afirmado == esperado
        respuesta_correcta = result.get("respuesta_correcta")
        if isinstance(respuesta_correcta, bool) and respuesta_correcta != es_verdadero_real:
            return (
                f"la afirmación dice que el resultado es {resultado_afirmado}, pero el "
                f"resultado real de la operación es {esperado}"
            )
        return None

    numeros = _extraer_numeros(texto)
    if len(numeros) < 2:
        return None
    esperado = _calcular(operacion, numeros)
    if esperado is None:
        return None

    if tipo == TipoActividad.opcion_multiple:
        opciones = result.get("opciones")
        if not isinstance(opciones, list):
            return None
        valores = [_valor_numerico_de(o) for o in opciones if isinstance(o, str)]
        if not any(v == esperado for v in valores):
            return (
                f"ninguna opción coincide con el resultado real de la operación "
                f"({operacion} = {esperado}); el LLM probablemente calculó mal"
            )
        valor_marcado = _valor_numerico_de(result.get("respuesta_correcta"))
        if valor_marcado is not None and valor_marcado != esperado:
            return f"la opción marcada como correcta ({valor_marcado}) no es el resultado real ({esperado})"
        return None

    if tipo in (TipoActividad.completar, TipoActividad.respuesta_corta):
        valor_marcado = _valor_numerico_de(result.get("respuesta_correcta"))
        if valor_marcado is not None and valor_marcado != esperado:
            return f"la respuesta marcada ({valor_marcado}) no es el resultado real de la operación ({esperado})"
        return None

    return None


_PATRON_VALOR_POSICIONAL = re.compile(
    r"valor\s+(?:del|de)\s+(\d)\s+en\s+(?:el\s+)?n[uú]mero\s+([\d.,]+)", re.IGNORECASE
)


def _verificar_valor_posicional(tipo: TipoActividad, result: dict) -> str | None:
    """Guardrail determinístico: preguntas de valor posicional ("¿Cuál es el
    valor del 5 en el número 5746252?"), donde el LLM se equivoca seguido.
    Caso real: marcó "5000" como correcto cuando el 5 está en la posición de
    los millones (valor real 5,000,000)."""
    texto = _texto_pregunta(result)
    if not texto:
        return None
    m = _PATRON_VALOR_POSICIONAL.search(texto)
    if not m:
        return None
    digito = m.group(1)
    numero_str = re.sub(r"[.,\s]", "", m.group(2))
    if digito not in numero_str:
        return None
    posicion_desde_izq = numero_str.index(digito)
    posicion_desde_derecha = len(numero_str) - 1 - posicion_desde_izq
    valor_real = int(digito) * (10 ** posicion_desde_derecha)

    if tipo == TipoActividad.opcion_multiple:
        opciones = result.get("opciones")
        if not isinstance(opciones, list):
            return None
        valores = [_valor_numerico_de(o) for o in opciones if isinstance(o, str)]
        if not any(v == valor_real for v in valores):
            return f"ninguna opción coincide con el valor posicional real ({valor_real})"
        valor_marcado = _valor_numerico_de(result.get("respuesta_correcta"))
        if valor_marcado is not None and valor_marcado != valor_real:
            return f"la opción marcada ({valor_marcado}) no es el valor posicional real ({valor_real})"
        return None

    if tipo in (TipoActividad.completar, TipoActividad.respuesta_corta):
        valor_marcado = _valor_numerico_de(result.get("respuesta_correcta"))
        if valor_marcado is not None and valor_marcado != valor_real:
            return f"la respuesta marcada ({valor_marcado}) no es el valor posicional real ({valor_real})"
        return None

    return None


# Rango numérico máximo esperado por grado en Matemáticas (currículo de
# Guatemala). Grados no listados (básico/diversificado) no se restringen:
# ya incluyen álgebra, fracciones/decimales y números grandes legítimamente.
_RANGO_MAX_PRIMARIA = {
    1: (99_999, "decenas de millar (máximo 99,999)"),
    2: (99_999, "decenas de millar (máximo 99,999)"),
    3: (99_999, "decenas de millar (máximo 99,999)"),
    4: (99_999, "decenas de millar (máximo 99,999)"),
    5: (999_999, "centenas de millar (máximo 999,999)"),
}
_RANGO_MAX_PRIMARIA_6_EN_ADELANTE = (9_999_999, "millones (máximo 9,999,999)")


def _grado_ordinal(grado_nombre: str | None) -> int | None:
    if not grado_nombre:
        return None
    m = re.match(r"\s*(\d+)", grado_nombre)
    return int(m.group(1)) if m else None


def _rango_numerico_grado(
    asignatura_nombre: str | None, grado_nombre: str | None
) -> tuple[int, str] | None:
    """Rango numérico máximo para Matemáticas según el grado, o None si no
    aplica restricción (no es Matemáticas, es básico/diversificado —ya
    trabajan números grandes, fracciones y decimales legítimamente—, o no se
    pudo determinar el grado). Caso real: un ejercicio de 4to primaria pedía
    sumar números de 7 dígitos (millones), fuera del currículo del grado."""
    if not asignatura_nombre or "matematic" not in _normalizar_pregunta(asignatura_nombre):
        return None
    nombre = (grado_nombre or "").lower()
    if "primaria" not in nombre:
        return None
    ordinal = _grado_ordinal(grado_nombre)
    if ordinal is None:
        return None
    if ordinal in _RANGO_MAX_PRIMARIA:
        return _RANGO_MAX_PRIMARIA[ordinal]
    if ordinal >= 6:
        return _RANGO_MAX_PRIMARIA_6_EN_ADELANTE
    return None


def _verificar_rango_numerico(result: dict, rango_max: tuple[int, str] | None) -> str | None:
    """Guardrail determinístico: ningún número generado (operando, resultado
    u opción) puede exceder el rango del grado del estudiante."""
    if not rango_max:
        return None
    max_valor, _desc = rango_max
    for texto in _textos_de_actividad(result):
        for n in _extraer_numeros(texto):
            if n > max_valor:
                return f"contiene un número ({n:,}) que excede el rango numérico del grado (máximo {max_valor:,})"
    return None


_PATRON_INCISO = re.compile(r"^\s*[A-Da-d]\s*[\.\):]\s*")


def _quitar_inciso(texto: str) -> str:
    """Quita un inciso ("A.", "b)", "C:") que el LLM haya antepuesto a una
    opción de opción múltiple, a pesar de que el prompt se lo pide
    explícitamente. Decisión de producto: el estudiante solo toca la opción,
    no necesita letras de inciso (y menos si el LLM las genera desordenadas:
    A, D, B, C confunde más que ayuda)."""
    return _PATRON_INCISO.sub("", texto or "", count=1).strip()


def _orden_tiene_conclusion_fuera_de_lugar(orden_correcto: list | None) -> bool:
    """True si algún elemento de "conclusión" no queda al FINAL del orden.

    Heurística genérica (no depende del tema): en cualquier procedimiento
    lógico real, un paso que "concluye" algo (concluir/concluye/conclusión)
    tiene que ser el último, porque depende del resultado de los pasos
    anteriores. Si aparece antes, es la señal de que el LLM mezcló dos
    caminos/desenlaces distintos en una sola secuencia (caso real detectado:
    para "verificar si A es subconjunto de B" devolvía ["Verificar que todos
    pertenecen a B", "Concluir que es subconjunto", "Comprobar si alguno NO
    pertenece"], donde el último paso en realidad es una rama alternativa,
    no algo que ocurre DESPUÉS de concluir).
    """
    if not isinstance(orden_correcto, list) or not orden_correcto:
        return False
    indices_conclusion = [
        i for i, el in enumerate(orden_correcto)
        if isinstance(el, str) and "conclu" in el.lower()
    ]
    return bool(indices_conclusion) and max(indices_conclusion) != len(orden_correcto) - 1


# Máximo de elementos razonable para una secuencia de pasos real (procesos
# reales del libro rondan 3-5 pasos; listas de 7+ suelen ser clasificaciones
# completas de un tema, no un proceso).
MAX_ELEMENTOS_ORDENAR = 6

_MARCADORES_CATEGORICOS = (
    "tipos de", "tipo de", "clases de", "clase de", "categorías de", "categoría de",
    "partes de", "parte de", "ejemplos de", "ejemplo de", "características de",
)


def _ordenar_parece_categorico(instruccion: str | None, elementos: list | None) -> bool:
    """Señales BARATAS (sin depender del autorreporte del LLM) de que los
    elementos son una CLASIFICACIÓN/lista de hechos, no los pasos de un
    proceso real: demasiados elementos, o la instrucción usa un marcador
    explícitamente categórico ("tipos de", "partes de"...).

    NO se intentó (y se descartó) detectar "es secuencial" por palabras como
    "pasos"/"proceso"/"luego" en la instrucción o por si los elementos
    empiezan con un verbo: en pruebas reales el LLM escribe "Ordena los
    PASOS para formar el sistema óseo" para una lista de HECHOS sin orden
    (sistema óseo, Ciencias Naturales) tan seguido como para un proceso
    real (digestión), y las oraciones de un proceso real tampoco siempre
    empiezan con un verbo ("En la boca, el alimento es masticado..."). Ver
    `es_proceso_secuencial` (autorreporte forzado del propio LLM) como
    gate principal para ese caso.
    """
    if not isinstance(elementos, list) or not elementos or not all(isinstance(e, str) for e in elementos):
        return False
    if len(elementos) > MAX_ELEMENTOS_ORDENAR:
        return True
    texto_instr = (instruccion or "").lower()
    return any(m in texto_instr for m in _MARCADORES_CATEGORICOS)


def _actividad_invalida(
    tipo: TipoActividad, result: dict, rango_max: tuple[int, str] | None = None
) -> str | None:
    """Guardrail determinístico post-generación: devuelve la razón por la que
    la actividad NO sirve, o None si está bien.

    Para "completar" y "respuesta_corta" (los únicos tipos donde el
    estudiante escribe la respuesta en un campo libre):
      - Bug B: la pregunta "gira en torno a" un símbolo matemático especial
        (∈, ∉, ⊂, ⊄, ⊆, ⊇, ∪, ∩, ≤, ≥, ≠) que no se puede teclear — ya sea
        porque la respuesta_correcta ES el símbolo, o porque el símbolo
        aparece en el texto visible (oración/pregunta). Esto último cubre un
        caso real: el LLM esquiva "no uses el símbolo como respuesta"
        escribiendo el símbolo en la oración y dejando un hueco/respuesta
        inventada sin sentido en otro lado (ej. oración "...pertenece (∈) al
        conjunto... ___ se simboliza con el símbolo e" con respuesta "e").
      - Bug A (solo "completar"): el hueco queda pegado a una palabra igual a
        la respuesta esperada (hueco redundante).

    Para "ordenar": el prompt YA pide no mezclar caminos/desenlaces
    contrarios en una secuencia y restringirse a temas con secuencia real
    (ver Bug 6), pero un modelo 7B lo sigue incumpliendo de forma consistente
    pese a la instrucción, y no solo en Matemáticas — ver
    `_orden_tiene_conclusion_fuera_de_lugar` y `_ordenar_parece_categorico`
    (esta última generaliza a cualquier asignatura, no depende de palabras
    clave de un tema en particular).

    Para TODOS los tipos: la actividad no puede depender de un
    ejemplo/ejercicio/diagrama específico del libro que el estudiante no
    tiene a la vista — ver `_referencia_a_ejemplo_del_libro`. Tampoco puede
    tener errores aritméticos, de valor posicional, ni números fuera del
    rango del grado (los LLM no saben hacer aritmética de forma confiable:
    ver `_verificar_aritmetica`, `_verificar_valor_posicional`,
    `_verificar_rango_numerico`).
    """
    razon_rango = _verificar_rango_numerico(result, rango_max)
    if razon_rango:
        return razon_rango
    razon_aritmetica = _verificar_aritmetica(tipo, result)
    if razon_aritmetica:
        return razon_aritmetica
    razon_posicional = _verificar_valor_posicional(tipo, result)
    if razon_posicional:
        return razon_posicional
    frase_ejemplo = _referencia_a_ejemplo_del_libro(result)
    if frase_ejemplo:
        return f"la actividad depende de un ejercicio/ejemplo específico del libro ('{frase_ejemplo}')"
    if tipo == TipoActividad.ordenar:
        elementos = result.get("elementos_desordenados")
        orden = result.get("orden_correcto")
        if (
            isinstance(elementos, list) and isinstance(orden, list)
            and all(isinstance(e, str) for e in elementos)
            and all(isinstance(e, str) for e in orden)
        ):
            # Caso real detectado: el LLM da 3 elementos para arrastrar pero solo
            # 2 en "orden_correcto" (descartó el paso de la rama contraria del
            # resultado, pero lo dejó como elemento arrastrable): el estudiante
            # no tiene forma de acertar la posición de ese elemento "huérfano"
            # porque no aparece en la respuesta correcta. Cualquier desajuste de
            # conjuntos entre ambas listas vuelve el ejercicio injugable.
            if sorted(elementos) != sorted(orden):
                return "elementos_desordenados y orden_correcto no son el mismo conjunto de elementos"
        if _orden_tiene_conclusion_fuera_de_lugar(orden):
            return "un paso de conclusión no queda al final (secuencia con caminos contradictorios)"
        if _ordenar_parece_categorico(result.get("instruccion"), elementos):
            return "los elementos parecen una clasificación/lista de categorías, no los pasos de un proceso real"
        # NOTA: se pide al LLM que se autoevalúe ("es_proceso_secuencial") en el
        # mismo prompt que genera la actividad, pero en pruebas reales el
        # modelo casi siempre responde `true` sin importar el contenido (ya
        # comprometido con lo que generó, no lo reconsidera). Por eso ese
        # campo NO se usa aquí como filtro; en su lugar, `generar_actividad`
        # hace una llamada de VERIFICACIÓN INDEPENDIENTE (ver
        # `_verificar_ordenar_es_secuencial`) con el candidato ya completo,
        # que si es más confiable en pruebas reales.
        return None
    if tipo not in (TipoActividad.completar, TipoActividad.respuesta_corta):
        return None
    respuesta = result.get("respuesta_correcta")
    respuesta_str = str(respuesta) if respuesta is not None else None
    texto_visible = result.get("oracion") if tipo == TipoActividad.completar else result.get("pregunta")
    if _contiene_simbolo_especial(respuesta_str) or _contiene_simbolo_especial(texto_visible):
        return "la pregunta gira en torno a un símbolo matemático especial (no se puede teclear)"
    if tipo == TipoActividad.completar and _hueco_es_redundante(
        result.get("oracion"), respuesta_str or ""
    ):
        return "el hueco queda junto a una palabra igual a la respuesta (hueco redundante)"
    if tipo == TipoActividad.completar and _respuesta_es_fragmento_de_palabra(
        result.get("oracion"), respuesta_str
    ):
        return "la respuesta es un fragmento de palabra o demasiado corta (ej. 'ás' de 'más')"
    return None


def _verificar_ordenar_es_secuencia(result: dict) -> bool:
    """Segunda llamada al LLM, SOLO como verificación (no genera contenido
    nuevo): le muestra el candidato de "ordenar" ya completo y le pregunta,
    de forma aislada y estricta, si de verdad es una secuencia con
    progresión real. Se usa en vez de un autorreporte en la misma llamada
    de generación porque, en pruebas reales, el modelo casi siempre se
    autocalifica `true` sin reconsiderar lo que acaba de generar; juzgar un
    candidato ya terminado (sin la presión de tener que producirlo) resultó
    más confiable en la práctica (mismo principio que ya usa la micro-lección
    con su verificación de cobertura post-generación).

    Devuelve True (se acepta) si no se pudo verificar (fallo de red/JSON):
    ante la duda de la VERIFICACIÓN se prefiere no bloquear de más la
    generación; los otros guardrails deterministas ya cubren los casos más
    claros.
    """
    elementos = result.get("elementos_desordenados")
    orden = result.get("orden_correcto")
    if not isinstance(elementos, list) or not isinstance(orden, list):
        return True

    lista_orden = "\n".join(f"- {e}" for e in orden)
    messages = [
        {
            "role": "system",
            "content": (
                "Eres un experto en pedagogía que audita ejercicios escolares de "
                "'ordenar pasos'. Respondes SOLO con JSON válido, sin texto adicional."
            ),
        },
        {
            "role": "user",
            "content": (
                "Este es un ejercicio de 'ordenar' para un estudiante de primaria/"
                "secundaria. El orden propuesto como correcto es:\n\n"
                f"{lista_orden}\n\n"
                "Pregunta: ¿estos elementos forman una SECUENCIA con progresión real "
                "(temporal, de lugar, o de causa-efecto), donde cada elemento depende "
                "físicamente o lógicamente del anterior (como los pasos de un proceso "
                "o las etapas de un ciclo)? O son en realidad una lista de HECHOS, "
                "PROPIEDADES o CARACTERÍSTICAS sobre el mismo tema que NO tienen un "
                "único orden correcto, aunque se hayan escrito en algún orden?\n"
                "Sé muy estricto: ante cualquier duda, responde que NO es una "
                "secuencia real.\n\n"
                'Responde SOLO con este JSON: {"es_secuencia_real": true o false, '
                '"razon": "una oración explicando por qué"}'
            ),
        },
    ]
    veredicto = llm_client.generate_json(messages, max_tokens=200)
    if veredicto is None:
        return True
    return veredicto.get("es_secuencia_real") is True


# Los ejemplos usan placeholders ABSTRACTOS a propósito: si traen un tema real
# (p. ej. "energía cinética" o "ciclo del agua"), el modelo 7B tiende a copiarlos
# literalmente en vez de basarse en los fragmentos del libro. Mantenerlos genéricos
# obliga al LLM a tomar el contenido del contexto.
ACTIVITY_PROMPTS = {
    TipoActividad.opcion_multiple: """Genera UNA pregunta de opción múltiple basada en el libro.
NO antepongas letras ni números de inciso ("A.", "B)", "1.", etc.) a las opciones: escribe SOLO el texto de la opción, el estudiante las toca directamente sin necesitar una letra.
REGLAS CRÍTICAS para los distractores (las opciones incorrectas):
- Cada distractor debe ser CLARAMENTE INCORRECTO según el libro, no ambiguo ni parcialmente correcto.
- NUNCA generes un distractor que podría ser interpretado como correcto por un estudiante que entiende el tema (por ejemplo, la negación exacta de una afirmación verdadera casi siempre también es defendible como cierta o falsa según el caso: evita ese patrón).
- Los distractores deben ser plausibles (no absurdos) pero inequívocamente incorrectos.
- ANTES de responder, verifica que SOLO UNA opción sea defendible como correcta.
- Evita preguntas tipo "¿Cuál de las siguientes afirmaciones es correcta?" con varias opciones que podrían defenderse como ciertas. Prefiere preguntas específicas y concretas (ej. "¿Qué significa que A esté contenido en B?") en vez de pedir juzgar afirmaciones abstractas.
Responde SOLO con JSON válido, sin texto adicional:
{
    "pregunta": "la pregunta",
    "opciones": ["opción 1 (sin letra de inciso)", "opción 2 (sin letra de inciso)", "opción 3 (sin letra de inciso)", "opción 4 (sin letra de inciso)"],
    "respuesta_correcta": "la opción correcta (texto exacto de una de las opciones, sin letra de inciso)",
    "explicacion": "por qué esa es la respuesta correcta"
}""",

    TipoActividad.verdadero_falso: """Genera UNA afirmación de verdadero o falso basada en el libro.
Responde SOLO con JSON válido, sin texto adicional:
{
    "afirmacion": "la afirmación a evaluar",
    "respuesta_correcta": true o false,
    "explicacion": "por qué es verdadero o falso"
}""",

    TipoActividad.completar: """Genera UNA oración para completar. La oración debe salir TEXTUALMENTE del libro (toma una frase real del contenido y reemplaza por ___ la palabra o término clave que el estudiante debe recordar). Usa ___ donde va la palabra faltante.
El espacio en blanco (___) DEBE reemplazar un TÉRMINO CLAVE del tema (nombre de estructura, órgano, proceso, concepto científico). NUNCA pongas el blank en verbos comunes (significa, tiene, es, son), artículos, preposiciones o conectores.
Ejemplo CORRECTO: "La ___ es la unidad básica de los seres vivos" (respuesta: célula).
Ejemplo INCORRECTO: "La célula ___ la unidad básica" (respuesta: es).
El hueco (___) NUNCA debe quedar junto a una palabra igual a la respuesta esperada (eso lo vuelve redundante). Ejemplo INCORRECTO: "decimos que pertenece (___) al conjunto" con respuesta "pertenece" (la palabra ya está escrita justo antes del hueco).
Si el término clave de este concepto es un símbolo matemático especial (∈, ∉, ⊂, ⊄, ⊆, ⊇, ∪, ∩, ≤, ≥, ≠), NO lo uses como respuesta del hueco: ningún teclado permite escribir esos símbolos. Elige en su lugar otro término clave que se escriba con palabras.
Responde SOLO con JSON válido, sin texto adicional (los valores son ejemplos de FORMATO, no de contenido):
{
    "oracion": "<una oración tomada del libro con ___ en el TÉRMINO CLAVE>",
    "respuesta_correcta": "<el término clave exacto que va en ___, tal como aparece en el libro>",
    "pista": "una pista para ayudar al estudiante"
}""",

    TipoActividad.ordenar: """Genera UN ejercicio de ordenar elementos basado en el libro. Los elementos deben ser conceptos, pasos o etapas QUE APARECEN en el libro (una secuencia o proceso descrito en el libro). No uses procesos que no estén en el libro.
IMPORTANTE: este tipo de ejercicio es SOLO para temas con una secuencia natural de pasos (un proceso, procedimiento, ciclo o algoritmo descrito en el libro: por ejemplo, las etapas de un proceso biológico, los pasos de un procedimiento matemático, el orden cronológico de un evento). NO lo uses para definiciones, propiedades o relaciones entre conceptos (por ejemplo, "qué es un subconjunto" NO tiene un orden natural de pasos: sería forzado e inventado).
Si el contenido del libro no describe un proceso con pasos reales, en vez de inventar un orden arbitrario, usa como elementos los PASOS DE UN ÚNICO PROCEDIMIENTO que el libro sí explique para aplicar o verificar ese concepto, de modo que exista un único orden lógicamente correcto.
REGLA CRÍTICA 1 (error real que debes evitar): NUNCA mezcles en la misma secuencia pasos que pertenecen a resultados o caminos DISTINTOS o CONTRARIOS entre sí. Ejemplo de ERROR real que NO debes repetir, para "verificar si A es subconjunto de B": ["Verificar si todos los elementos de A pertenecen a B", "Comprobar si por lo menos un elemento de A NO pertenece a B", "Concluir que A es subconjunto de B"] — esto está MAL porque el paso 2 (buscar un elemento que NO pertenece) es el camino para concluir LO CONTRARIO (que A NO es subconjunto), no un paso siguiente del mismo procedimiento. Un ejercicio de ordenar debe tener UN SOLO desenlace posible: o bien los pasos para confirmar que SÍ se cumple la propiedad, o bien elige otro proceso del libro con una secuencia sin bifurcaciones (por ejemplo, los pasos para representar o construir algo, no para decidir entre dos resultados opuestos).
REGLA CRÍTICA 2 (otro error real que debes evitar, en cualquier materia): NO conviertas una lista de HECHOS o PROPIEDADES sobre un mismo tema en un ejercicio de ordenar, aunque le pongas la palabra "pasos" a la instrucción. Ejemplo de ERROR real (Ciencias Naturales, tema "sistema óseo"): pedir ordenar ["El sistema óseo está formado por todos los huesos del cuerpo", "Sirve para proteger los órganos internos", "Están unidos entre sí por articulaciones", "La función de los huesos largos es dar apoyo"] — esto está MAL porque son 4 datos/propiedades distintas sobre el mismo tema (composición, función, articulación, tipos de huesos) SIN ningún orden temporal o lógico entre sí: cualquier orden sería igual de válido, así que no es un ejercicio de ordenar real. En cambio, SÍ es válido ordenar algo como el proceso de digestión (la comida pasa por la boca, luego el estómago, luego el intestino: cada paso depende físicamente del anterior) porque ahí sí hay una progresión real (de lugar, tiempo o causa-efecto) de un paso al siguiente.
Por eso, el JSON debe incluir el campo "es_proceso_secuencial": ponlo en `true` SOLO si estás seguro de que hay una progresión real (temporal, de lugar, o de causa-efecto) donde cada elemento depende del anterior; ponlo en `false` si tienes cualquier duda de que sea solo una lista de datos/propiedades/características sobre el mismo tema. Sé estricto: ante la duda, `false`.
Responde SOLO con JSON válido, sin texto adicional (los valores son ejemplos de FORMATO, no de contenido):
{
    "instruccion": "<instrucción de qué ordenar, sobre el proceso del libro>",
    "elementos_desordenados": ["<elemento del libro>", "<elemento del libro>", "<elemento del libro>"],
    "orden_correcto": ["<los mismos elementos en el orden correcto>"],
    "es_proceso_secuencial": true,
    "explicacion": "explicación del orden correcto"
}""",

    TipoActividad.respuesta_corta: """Genera UNA pregunta de respuesta corta basada en el libro.
La pregunta DEBE pedir UN SOLO TÉRMINO o CONCEPTO específico. Formúlala como: "¿Cómo se llama el hueso que protege al cerebro?" (respuesta: cráneo). NUNCA preguntes dos cosas en una ("¿qué parte Y cuál es su función?"). La respuesta esperada debe ser de 1 a 3 palabras como máximo.
NUNCA hagas una pregunta cuya respuesta sea un símbolo matemático especial (∈, ∉, ⊂, ⊄, ⊆, ⊇, ∪, ∩, ≤, ≥, ≠): el estudiante escribe la respuesta en un campo de texto libre y ningún teclado tiene esos símbolos, así que sería imposible de responder. Si el concepto involucra uno de esos símbolos, pregunta por otra cosa (una definición, un ejemplo, el nombre del concepto en palabras).
Responde SOLO con JSON válido, sin texto adicional:
{
    "pregunta": "la pregunta (pide un solo término)",
    "respuesta_correcta": "la respuesta esperada (1-3 palabras)",
    "palabras_clave": ["palabra1", "palabra2", "palabra3"],
    "explicacion": "respuesta completa para retroalimentación"
}""",
}


def _texto_pregunta(result: dict) -> str | None:
    """El texto visible que "es" la pregunta de la actividad, según su forma:
    pregunta (opción múltiple / respuesta corta), afirmación (V/F), oración
    (completar) o instrucción (ordenar)."""
    for campo in ("pregunta", "afirmacion", "oracion", "instruccion"):
        valor = result.get(campo)
        if isinstance(valor, str) and valor.strip():
            return valor
    return None


def _normalizar_pregunta(texto: str) -> str:
    """Normaliza para comparar repetición: minúsculas, sin tildes ni signos."""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]", "", texto.lower()).strip()


def _es_pregunta_repetida(result: dict, evitar_preguntas: list[str]) -> bool:
    """True si la pregunta generada coincide (normalizada) con una ya hecha
    en la sesión. Caso real: en una sesión de 5, el LLM generó 3 veces
    "¿Qué significa que A esté contenido en B?" — cada llamada era
    independiente y producía la pregunta más obvia del tema."""
    texto = _texto_pregunta(result)
    if not texto or not evitar_preguntas:
        return False
    norm = _normalizar_pregunta(texto)
    return any(norm == _normalizar_pregunta(p) for p in evitar_preguntas if p)


def _bloque_evitar_preguntas(evitar_preguntas: list[str]) -> str:
    lista = "\n".join(f"- {p}" for p in evitar_preguntas if p and p.strip())
    if not lista:
        return ""
    return (
        "\n\nIMPORTANTE: En esta sesión de práctica, el estudiante ya respondió "
        "las siguientes preguntas. NO repitas ninguna de estas preguntas ni "
        "generes una pregunta con el mismo enfoque:\n"
        f"{lista}\n"
        "Genera una pregunta DIFERENTE que evalúe OTRO aspecto del tema (por "
        "ejemplo: si ya se preguntó una definición, pregunta sobre un caso "
        "concreto o sobre la diferencia entre dos conceptos)."
    )


# Números de 4+ dígitos legibles: comas de miles (aplica a cualquier asignatura;
# a un niño de primaria "5746252" es mucho más difícil de leer que "5,746,252").
_INSTRUCCIONES_NUMEROS_LEGIBLES = (
    " Cuando escribas números de 4 o más dígitos, SIEMPRE usa comas como separador "
    "de miles para facilitar la lectura (1000 -> 1,000; 45678 -> 45,678; "
    "5746252 -> 5,746,252; 1000000 -> 1,000,000). NUNCA escribas números grandes sin "
    "separador de miles."
)


# Nomenclatura posicional EXACTA (solo Matemáticas): el LLM confunde seguido
# la posición donde difieren dos números (dijo "centenas" cuando la diferencia
# de 1234 vs 1243 está en las decenas). No hay forma barata de verificar en
# prosa si una explicación posicional es correcta, así que se refuerza el prompt.
_INSTRUCCIONES_MATEMATICAS_POSICIONES = (
    " NOMENCLATURA POSICIONAL (respétala con exactitud): de derecha a izquierda, las "
    "posiciones son unidades, decenas, centenas, unidades de millar, decenas de millar, "
    "centenas de millar, unidades de millón. Una centena de millar vale 100,000 (NO 1,000). "
    "Cuando compares dos números, identifica con CUIDADO la posición exacta donde difieren. "
    "Ejemplo: al comparar 1,234 y 1,243, ambos tienen el mismo millar (1) y la misma centena "
    "(2), pero difieren en las DECENAS (3 vs 4); NO digas 'centenas' cuando la diferencia "
    "está en las decenas."
)


def _bloque_rango_numerico(rango_max: tuple[int, str] | None) -> str:
    if not rango_max:
        return ""
    max_valor, desc = rango_max
    return (
        f"\nRESTRICCIÓN DE RANGO NUMÉRICO (currículo de Guatemala para este grado): "
        f"todos los números que uses en la actividad (operandos, resultados, opciones) "
        f"deben ser de {desc}. NUNCA generes ni uses números que excedan {max_valor:,}. "
        "Si el libro menciona números más grandes como ejemplo, ADAPTA los ejercicios a "
        "números dentro de este rango, aunque tengas que inventar cifras nuevas (mientras "
        "el CONCEPTO evaluado siga siendo el del libro). "
        "IMPORTANTE sobre aritmética: antes de responder, VERIFICA con cuidado que el "
        "resultado de cualquier operación (suma, resta, multiplicación, división) que "
        "generes sea matemáticamente correcto. Vuelve a sumar/restar dígito por dígito si "
        "es necesario. NUNCA marques como correcta una opción cuyo resultado no hayas "
        "verificado con certeza."
    )


def _llamar_llm(
    tipo: TipoActividad,
    context: str,
    tema: str | None = None,
    evitar_preguntas: list[str] | None = None,
    rango_max: tuple[int, str] | None = None,
    es_matematicas: bool = False,
) -> dict | None:
    """Una llamada al LLM para un tipo de actividad dado. Devuelve el JSON crudo
    (sin separar contenido/respuesta_correcta) o None si falla."""
    activity_prompt = ACTIVITY_PROMPTS[tipo]

    tema_str = f" sobre el tema: {tema}" if tema else ""
    messages = [
        {
            "role": "system",
            "content": (
                "Eres un profesor que crea ejercicios educativos para estudiantes de "
                f"primaria/secundaria en Guatemala. Crea ejercicios claros, en español.{tema_str} "
                "Genera la actividad EXCLUSIVAMENTE con el contenido del libro "
                "que se te da. NO uses tu conocimiento propio. NO inventes información ni ejemplos "
                "que no estén en el libro. "
                "IGNORA cualquier ejercicio, actividad resuelta, ejemplo resuelto o sección tipo "
                "'Mesa lista', 'Ahora es tu turno', 'Ejercicio', 'Practica' que aparezca en el "
                "libro: esas son actividades del libro, no la teoría del tema. Genera tu "
                "actividad basándote ÚNICAMENTE en las definiciones, conceptos, teoría y "
                "explicaciones del libro. "
                "SIEMPRE genera todo el contenido en ESPAÑOL. Nunca uses términos en inglés. "
                "Los términos científicos deben estar en español (ejemplo: profase, no prophase; "
                "célula, no cell). "
                "NUNCA uses las palabras 'fragmento', 'contexto', 'chunk' ni ningún término "
                "técnico de procesamiento de datos en tu respuesta: refiérete siempre al "
                "material como 'el libro' o 'tu libro de texto'. "
                "NUNCA generes preguntas que dependan de un ejemplo específico del libro "
                "(como conjuntos con nombres de letras P, C, R, V de un diagrama particular, "
                "o datos numéricos de un ejercicio resuelto): el estudiante responde SIN el "
                "libro abierto y no puede saber a qué se refieren. La pregunta debe evaluar "
                "la COMPRENSIÓN CONCEPTUAL del tema y entenderse completa por sí sola; si "
                "necesitas un ejemplo, defínelo COMPLETO dentro de la misma pregunta (por "
                "ejemplo: 'Si A = {1, 2, 3} y B = {1, 2, 3, 4, 5}, ¿A es subconjunto de B?'). "
                "Tampoco escribas 'según el ejemplo', 'en el ejercicio' ni 'en el diagrama' "
                "en la explicación: explica el concepto, no el ejercicio del libro."
                + _INSTRUCCIONES_NUMEROS_LEGIBLES
                + (_INSTRUCCIONES_MATEMATICAS_POSICIONES if es_matematicas else "")
                + _bloque_rango_numerico(rango_max)
            ),
        },
        {
            "role": "user",
            "content": (
                f"Basándote ÚNICAMENTE en el siguiente contenido del libro:\n\n{context}\n\n"
                f"{activity_prompt}\n\n"
                "Recuerda: la actividad debe tratar sobre lo que dice el libro arriba, "
                "no sobre otros temas. Si alguna parte es un ejercicio del libro (por ejemplo "
                "'Mesa lista', 'Ahora es tu turno' u otro ejercicio ya resuelto o propuesto), "
                "IGNÓRALA como fuente y basa la actividad solo en la teoría/definiciones del "
                "resto del libro. "
                + (
                    f"Si el contenido del libro es insuficiente para generar una actividad de calidad, "
                    f"genera una pregunta conceptual básica sobre el tema: {tema}."
                    if tema else ""
                )
                + _bloque_evitar_preguntas(evitar_preguntas or [])
            ),
        },
    ]

    result = llm_client.generate_json(messages)

    if result is None:
        # Reintentar una vez con prompt más estricto
        messages[-1]["content"] += "\n\nIMPORTANTE: Responde SOLO con el JSON, sin markdown, sin explicaciones adicionales."
        result = llm_client.generate_json(messages)

    if result and tipo == TipoActividad.opcion_multiple:
        # Guardrail determinístico: el prompt ya pide no anteponer incisos,
        # pero el LLM a veces los pone igual (y a veces desordenados,
        # p. ej. A, D, B, C). Se limpian aquí sin importar qué responda.
        if isinstance(result.get("opciones"), list):
            result["opciones"] = [
                _quitar_inciso(o) if isinstance(o, str) else o
                for o in result["opciones"]
            ]
        if isinstance(result.get("respuesta_correcta"), str):
            result["respuesta_correcta"] = _quitar_inciso(result["respuesta_correcta"])

        # Mezclar las opciones: el LLM tiende a poner la correcta de primera.
        # respuesta_correcta guarda el TEXTO (no el índice), y el evaluador
        # compara por texto, así que el shuffle no rompe la evaluación.
        if isinstance(result.get("opciones"), list):
            random.shuffle(result["opciones"])

    return result


def generar_actividad(
    tipo: TipoActividad,
    context: str,
    tema: str | None = None,
    evitar_preguntas: list[str] | None = None,
    asignatura_nombre: str | None = None,
    grado_nombre: str | None = None,
) -> tuple[TipoActividad, dict | None]:
    """
    Genera una actividad usando el LLM.

    Guardrail post-generación (capa determinística): si `tipo` es "completar",
    "respuesta_corta" u "ordenar" y la actividad resulta inválida (respuesta =
    símbolo matemático especial que no se puede teclear, hueco redundante, o
    secuencia con caminos contradictorios — ver `_actividad_invalida`), se
    REGENERA forzando "opcion_multiple" en vez de devolver la actividad rota.
    El prompt YA le pide al LLM evitar estos casos, pero varios casos reales
    demostraron que "solo prompt" no basta: se necesita esta capa para
    garantizar el comportamiento sin importar qué responda el LLM.

    `evitar_preguntas` (las preguntas ya generadas en la sesión de práctica)
    se inyecta en TODOS los prompts —incluida la regeneración— y además se
    verifica de forma determinística: si la pregunta salió repetida igual,
    se reintenta UNA vez; si vuelve a repetirse, se acepta con warning (una
    pregunta repetida es mejor que un hueco en la sesión de 5).

    `asignatura_nombre`/`grado_nombre` habilitan, SOLO para Matemáticas, la
    restricción de rango numérico por grado (ver `_rango_numerico_grado`) y
    la verificación aritmética/de valor posicional en `_actividad_invalida`
    (que en realidad corre para cualquier asignatura: un error de suma
    también sería un error en otras materias, aunque en la práctica solo se
    ha visto en Matemáticas).

    Devuelve `(tipo_efectivo, dict | None)`: `tipo_efectivo` puede diferir del
    `tipo` pedido si se forzó la regeneración; el dict es None si falló.
    """
    evitar = [p for p in (evitar_preguntas or []) if p and p.strip()]
    rango_max = _rango_numerico_grado(asignatura_nombre, grado_nombre)
    es_mat = bool(asignatura_nombre and "matematic" in _normalizar_pregunta(asignatura_nombre))
    result = _llamar_llm(tipo, context, tema, evitar, rango_max, es_mat)

    if result:
        razon = _actividad_invalida(tipo, result, rango_max)
        if not razon and tipo == TipoActividad.ordenar and not _verificar_ordenar_es_secuencia(result):
            razon = "verificación independiente: no es una secuencia con progresión real (parece una lista de hechos/propiedades)"
        if razon:
            logger.warning(
                f"Actividad {tipo.value} inválida ({razon}); regenerando como opcion_multiple"
            )
            result_omc = _llamar_llm(TipoActividad.opcion_multiple, context, tema, evitar, rango_max, es_mat)
            # La regeneración también se valida: podría volver a caer en un
            # defecto independiente del tipo (p. ej. citar "el ejemplo 2 del
            # libro", o un error aritmético distinto). Mejor descartar que
            # servir una actividad rota.
            if result_omc and not _actividad_invalida(TipoActividad.opcion_multiple, result_omc, rango_max):
                tipo = TipoActividad.opcion_multiple
                result = result_omc
            else:
                logger.warning("No se pudo regenerar como opcion_multiple; se descarta la actividad")
                result = None

    # Capa determinística contra repetición: el prompt ya pide variar, pero si
    # el LLM devolvió igual una pregunta ya hecha en la sesión, se reintenta
    # UNA vez sumando la repetida a la lista de exclusión.
    if result and _es_pregunta_repetida(result, evitar):
        logger.warning(
            f"Actividad {tipo.value} repite una pregunta de la sesión; reintentando una vez"
        )
        reintento = _llamar_llm(tipo, context, tema, evitar + [_texto_pregunta(result) or ""], rango_max, es_mat)
        if (
            reintento
            and not _actividad_invalida(tipo, reintento, rango_max)
            and not _es_pregunta_repetida(reintento, evitar)
        ):
            result = reintento
        else:
            logger.warning("El reintento también repitió (o falló); se acepta la actividad repetida")

    if result:
        logger.info(f"Actividad {tipo.value} generada exitosamente")
    else:
        logger.warning(f"Fallo al generar actividad {tipo.value}")

    return tipo, result
