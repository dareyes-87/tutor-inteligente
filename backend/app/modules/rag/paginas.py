"""Formato de referencias a páginas del libro (compartido por chat y actividades)."""


def formatear_rango_paginas(paginas: list[int]) -> str:
    """Agrupa números de página consecutivos en rangos legibles.
    Ej.: [36, 37, 93] -> "36-37, 93"."""
    ordenadas = sorted(set(paginas))
    rangos: list[str] = []
    inicio = fin = ordenadas[0]
    for p in ordenadas[1:]:
        if p == fin + 1:
            fin = p
        else:
            rangos.append(f"{inicio}-{fin}" if inicio != fin else str(inicio))
            inicio = fin = p
    rangos.append(f"{inicio}-{fin}" if inicio != fin else str(inicio))
    return ", ".join(rangos)


def etiqueta_paginas(paginas: list[int]) -> str:
    """"página 12" o "páginas 12-13, 20"."""
    etiqueta = "página" if len(set(paginas)) == 1 else "páginas"
    return f"{etiqueta} {formatear_rango_paginas(paginas)}"


def referencia_repaso(asignatura_nombre: str | None, paginas: list[int], correcta: bool = False) -> str:
    """Línea con la página del libro para la retroalimentación de una actividad
    ("Esto está en…" si acertó, "Repasa…" si no); "" si no hay páginas."""
    paginas = [p for p in paginas if p is not None]
    if not paginas:
        return ""
    inicio = "Esto está en tu libro" if correcta else "Repasa tu libro"
    return f"\n\n📖 {inicio} de {asignatura_nombre or 'texto'}, {etiqueta_paginas(paginas)}."
