# Pruebas de integración

Son pruebas de **integración**: corren contra el servidor real
(`http://localhost:8000`), no con mocks. El backend debe estar **levantado** y
con los datos sembrados (usuarios `carlos`/`maria`, un libro indexado con
lecciones) antes de ejecutarlas.

## Requisitos

```bash
docker compose up        # backend corriendo en localhost:8000
```

## Instalar dependencias y ejecutar

```bash
cd backend
pip install pytest pytest-asyncio httpx --break-system-packages
pytest tests/ -v
```

## Notas

- Las pruebas que llaman al LLM (chat, generar actividad, micro-lección) usan
  timeout de 30s; pueden tardar varios segundos cada una.
- Credenciales usadas por los fixtures: `carlos`/`carlos123` (estudiante) y
  `maria`/`maria123` (docente). Ajusta `conftest.py` si cambian.
- `asyncio_mode = strict` (ver `pytest.ini`): cada prueba async lleva
  `@pytest.mark.asyncio` y los fixtures async usan `@pytest_asyncio.fixture`.
