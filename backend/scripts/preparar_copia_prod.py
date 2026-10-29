"""
preparar_copia_prod.py — depura la COPIA local `tutor_prod` antes del pg_dump a producción.

docs/despliegue-produccion.md, sección 9, paso 1. Sobre la base indicada por POSTGRES_DB
(se niega a correr sobre "tutor", la base de trabajo):
  1. Conserva: el administrador, los docentes activos y los estudiantes activos salvo las
     cuentas de prueba (CUENTAS_DE_PRUEBA de seed_piloto.py); exige los 87 estudiantes
     reales por grado (ESTUDIANTES_ESPERADOS).
  2. Borra el resto de cuentas con sus datos (conversaciones y mensajes, resultados,
     perfiles, progreso).
  3. Pone contraseñas nuevas y aleatorias al admin y a maria (en la copia; la base de
     trabajo conserva las de desarrollo) y las AÑADE a --credenciales (permisos 600),
     nunca por pantalla.

Uso (dentro del contenedor backend):
    POSTGRES_DB=tutor_prod python scripts/preparar_copia_prod.py --credenciales /tmp/cred.csv [--dry-run]
"""
import argparse
import asyncio
import csv
import os
import secrets
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import delete, select  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import AsyncSessionLocal  # noqa: E402
from app.models.actividad import ResultadoActividad  # noqa: E402
from app.models.conversacion import Conversacion  # noqa: E402
from app.models.perfil_comprension import PerfilComprension  # noqa: E402
from app.models.progreso_leccion import ProgresoLeccion  # noqa: E402
from app.models.usuario import RolUsuario, Usuario  # noqa: E402
from app.security import hash_password  # noqa: E402
from seed_piloto import CUENTAS_DE_PRUEBA, ESTUDIANTES_ESPERADOS  # noqa: E402

CAMBIAR_CONTRASENA = ("admin", "maria")


def se_conserva(u: Usuario) -> bool:
    if u.rol == RolUsuario.administrador:
        return True
    return u.activo and u.username not in CUENTAS_DE_PRUEBA


async def main(credenciales: str, dry_run: bool) -> None:
    if settings.POSTGRES_DB == "tutor" or settings.DATABASE_URL:
        raise SystemExit("Solo sobre la copia local: POSTGRES_DB=tutor_prod y sin DATABASE_URL.")
    async with AsyncSessionLocal() as db:
        usuarios = (await db.execute(select(Usuario))).scalars().all()
        quedan = [u for u in usuarios if se_conserva(u)]
        borrar = [u for u in usuarios if not se_conserva(u)]
        por_grado = Counter(u.grado_id for u in quedan if u.rol == RolUsuario.estudiante)
        if dict(por_grado) != ESTUDIANTES_ESPERADOS:
            raise SystemExit(f"Estudiantes que quedarían por grado {dict(por_grado)} ≠ {ESTUDIANTES_ESPERADOS}")
        print(f"Base: {settings.POSTGRES_DB}. Quedan {len(quedan)}: "
              f"{dict(Counter(u.rol.value for u in quedan))}")
        print(f"Se borran {len(borrar)}: {', '.join(sorted(u.username for u in borrar))}")
        if dry_run:
            print("dry-run: no se cambió nada.")
            return

        ids = [u.id for u in borrar]
        for modelo in (Conversacion, ResultadoActividad, PerfilComprension, ProgresoLeccion):
            await db.execute(delete(modelo).where(modelo.estudiante_id.in_(ids)))
        await db.execute(delete(Usuario).where(Usuario.id.in_(ids)))

        nuevas = {}
        for u in quedan:
            if u.username in CAMBIAR_CONTRASENA:
                nuevas[u.username] = secrets.token_urlsafe(12)
                u.password_hash = hash_password(nuevas[u.username])
        await db.commit()

    nuevo = not os.path.exists(credenciales)
    with open(credenciales, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if nuevo:
            w.writerow(["username", "password"])
        w.writerows(nuevas.items())
    os.chmod(credenciales, 0o600)
    print(f"Contraseñas nuevas de {', '.join(nuevas)} añadidas a {credenciales}.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--credenciales", required=True, help="CSV donde se añaden las contraseñas nuevas")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    asyncio.run(main(args.credenciales, args.dry_run))
