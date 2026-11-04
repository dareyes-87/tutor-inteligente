"""
Cuentas de estudiante para la demo: una por grado, todas del piloto.

Fuente única para limpiar_pruebas.py (no les borra el uso posterior al piloto: se usan para ensayar
la demo) y verificar_seed.py (reporta ese uso aparte y falla si lo tiene otra cuenta del piloto).
Criterio: ecabrera y jgarcia por pedido; en los demás grados, el de uso alto con más niveles
aprobados en la ruta (8vo: empate a 3 niveles, asosaysosa tiene además una lección dominada).
Por nombre de grado y username: los ids cambian entre la BD local y producción.
"""
CUENTAS_DEMO = {
    "4to Primaria": "ecabrera",
    "5to Primaria": "lcerna",
    "6to Primaria": "layala",
    "7mo Básico": "aderosazal",
    "8vo Básico": "asosaysosa",
    "9no Básico": "jgarcia",
}
USUARIOS_DEMO = frozenset(CUENTAS_DEMO.values())
