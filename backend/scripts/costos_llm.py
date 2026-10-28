"""
Registro de tokens y costo de las llamadas a Together, con tope de gasto.

Lo usan los scripts que llaman al LLM (benchmark, verificación de modelos,
RAGAS, seed). Los precios salen del catálogo real de Together (/v1/models,
USD por millón de tokens), no de una tabla escrita a mano.

Uso típico:
    presupuesto = Presupuesto(max_usd=args.max_usd)
    presupuesto.instrumentar(cliente_together)   # cada create() queda registrado
    ...
    presupuesto.imprimir_resumen()

Si el costo acumulado alcanza `max_usd`, la SIGUIENTE llamada lanza
`PresupuestoAgotado` antes de enviarse (el gasto real puede pasar el tope
como mucho por el costo de una llamada). Si el código que llama al LLM captura
excepciones (la app lo hace: generate_json devuelve None), llamar también a
`verificar()` entre iteraciones para que el tope detenga el script.
"""
import argparse
import threading

import httpx

URL_MODELOS = "https://api.together.xyz/v1/models"


class PresupuestoAgotado(RuntimeError):
    pass


def catalogo_modelos(api_key: str) -> dict[str, dict]:
    """{id: entrada del catálogo} de Together (incluye `pricing`)."""
    resp = httpx.get(URL_MODELOS, headers={"Authorization": f"Bearer {api_key}"}, timeout=30)
    resp.raise_for_status()
    datos = resp.json()
    datos = datos if isinstance(datos, list) else datos.get("data", [])
    return {m["id"]: m for m in datos}


def agregar_argumento_max_usd(parser: argparse.ArgumentParser, defecto: float = 2.0) -> None:
    parser.add_argument(
        "--max-usd", type=float, default=defecto,
        help=f"tope de gasto en USD para esta ejecución (por defecto {defecto})",
    )


class Presupuesto:
    def __init__(self, max_usd: float, api_key: str | None = None, catalogo: dict | None = None):
        if catalogo is None:
            if api_key is None:  # sin clave explícita: la del backend (requiere app/ en sys.path)
                from app.config import settings
                api_key = settings.TOGETHER_API_KEY
            catalogo = catalogo_modelos(api_key)
        self.max_usd = max_usd
        self._precios = {
            mid: ((m.get("pricing") or {}).get("input", 0.0), (m.get("pricing") or {}).get("output", 0.0))
            for mid, m in catalogo.items()
        }
        self.por_modelo: dict[str, dict] = {}
        self._lock = threading.Lock()  # las llamadas pueden venir de asyncio.to_thread

    @property
    def total_usd(self) -> float:
        return sum(m["usd"] for m in self.por_modelo.values())

    def precio(self, modelo: str) -> tuple[float, float]:
        """(entrada, salida) en USD por millón de tokens; (0, 0) si no está en el catálogo."""
        return self._precios.get(modelo, (0.0, 0.0))

    def verificar(self) -> None:
        if self.total_usd >= self.max_usd:
            raise PresupuestoAgotado(
                f"Tope de gasto alcanzado: ${self.total_usd:.4f} >= --max-usd ${self.max_usd:.2f}"
            )

    def registrar(self, modelo: str, tokens_entrada: int, tokens_salida: int) -> float:
        p_in, p_out = self.precio(modelo)
        usd = (tokens_entrada * p_in + tokens_salida * p_out) / 1_000_000
        with self._lock:
            m = self.por_modelo.setdefault(modelo, {"llamadas": 0, "entrada": 0, "salida": 0, "usd": 0.0})
            m["llamadas"] += 1
            m["entrada"] += tokens_entrada
            m["salida"] += tokens_salida
            m["usd"] += usd
        return usd

    def instrumentar(self, cliente) -> None:
        """Envuelve `cliente.chat.completions.create` (SDK de Together) para
        verificar el tope antes de cada llamada y registrar su `usage` después."""
        completions = cliente.chat.completions
        original = completions.create

        def create(*args, **kwargs):
            self.verificar()
            resp = original(*args, **kwargs)
            uso = getattr(resp, "usage", None)
            if uso is not None:
                self.registrar(kwargs.get("model", "?"), uso.prompt_tokens or 0, uso.completion_tokens or 0)
            return resp

        completions.create = create

    def imprimir_resumen(self) -> None:
        print("\n=== Costo LLM de esta ejecución ===")
        print(f"{'modelo':45} {'llamadas':>8} {'tok entrada':>12} {'tok salida':>11} {'USD':>9}")
        for modelo, m in sorted(self.por_modelo.items()):
            print(f"{modelo:45} {m['llamadas']:>8} {m['entrada']:>12} {m['salida']:>11} {m['usd']:>9.5f}")
        print(f"{'TOTAL':45} {'':>8} {'':>12} {'':>11} {self.total_usd:>9.5f}  (tope ${self.max_usd:.2f})")


if __name__ == "__main__":
    # Autoverificación sin red.
    p = Presupuesto(0.01, catalogo={"m": {"pricing": {"input": 1.0, "output": 2.0}}})
    assert abs(p.registrar("m", 1000, 1000) - 0.003) < 1e-12
    p.verificar()
    p.registrar("m", 5000, 0)  # total 0.008
    p.registrar("m", 0, 1000)  # total 0.010 -> tope
    try:
        p.verificar()
        raise AssertionError("debió agotar el presupuesto")
    except PresupuestoAgotado:
        pass
    assert p.precio("desconocido") == (0.0, 0.0)
    print("costos_llm: OK")
