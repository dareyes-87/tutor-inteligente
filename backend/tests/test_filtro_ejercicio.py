"""Filtro de ejercicios (rag/search.py::es_ejercicio_del_libro), reglas de libros de básico."""
from app.modules.rag.search import es_ejercicio_del_libro


def test_paso_de_guia_es_ejercicio():
    assert es_ejercicio_del_libro("Paso 4 Realizamos el siguiente experimento. - Colocamos cubos de hielo")


def test_paso_con_que_necesitamos_saber_es_teoria():
    assert not es_ejercicio_del_libro(
        "Paso 4 Leemos y comentamos el texto. ¿Qué necesitamos saber? La fuerza es cualquier acción…"
    )


def test_procedimiento_de_matematicas_es_teoria():
    assert not es_ejercicio_del_libro("Para reducir términos semejantes: Paso 1. Se agrupan los términos.")
    assert not es_ejercicio_del_libro("Paso 1: trazamos un eje horizontal con el nombre «Deportes»")


def test_instruccion_numerada_es_ejercicio_salvo_con_ejemplo():
    assert es_ejercicio_del_libro("Respuesta: x/3.\n 1. Escriba las siguientes expresiones algebraicas")
    assert not es_ejercicio_del_libro("Ejemplo:\n a. x ÷ (- 4)\n 1. Escriba las siguientes expresiones")


def test_teoria_sin_marcadores():
    assert not es_ejercicio_del_libro("La división de una expresión algebraica se escribe en forma de fracción.")
