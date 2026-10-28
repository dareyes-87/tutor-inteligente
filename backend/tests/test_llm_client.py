"""
Pruebas unitarias del cliente LLM (sin red: se reemplaza la llamada a Together).

- content=None (modelo de razonamiento que agotó max_tokens) no revienta:
  generate_json y chat devuelven None.
- Respaldo de modelos: SOLO ante "modelo no disponible" se pasa al siguiente.
"""
import logging
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
import together

from app.config import settings
from app.llm.client import LLMClient


def _resp(content):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def _error_modelo(status=400):
    req = httpx.Request("POST", "https://api.together.xyz/v1/chat/completions")
    cls = together.BadRequestError if status == 400 else together.NotFoundError
    body = {"error": {"message": "Unable to access non-serverless model", "code": "model_not_available"}}
    return cls("model_not_available", response=httpx.Response(status, request=req), body=body)


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.setattr(settings, "LLM_MODEL", "principal/modelo")
    monkeypatch.setattr(settings, "LLM_MODEL_FALLBACKS", "respaldo/uno, respaldo/dos")
    c = LLMClient()
    return c


def _con_respuestas(cliente, *efectos):
    return patch.object(cliente._client.chat.completions, "create", side_effect=list(efectos))


def test_generate_json_content_none_devuelve_none(cliente):
    with _con_respuestas(cliente, _resp(None)):
        assert cliente.generate_json([{"role": "user", "content": "x"}]) is None


def test_generate_json_content_vacio_devuelve_none(cliente):
    with _con_respuestas(cliente, _resp("   ")):
        assert cliente.generate_json([{"role": "user", "content": "x"}]) is None


def test_generate_json_error_api_devuelve_none(cliente):
    with _con_respuestas(cliente, together.APITimeoutError(request=httpx.Request("POST", "http://x"))):
        assert cliente.generate_json([{"role": "user", "content": "x"}]) is None


def test_generate_json_quita_fences(cliente):
    with _con_respuestas(cliente, _resp('```json\n{"a": 1}\n```')):
        assert cliente.generate_json([{"role": "user", "content": "x"}]) == {"a": 1}


def test_chat_content_none_devuelve_none(cliente):
    with _con_respuestas(cliente, _resp(None)):
        assert cliente.chat([{"role": "user", "content": "x"}]) is None


@pytest.mark.parametrize("status", [400, 404])
def test_respaldo_ante_modelo_no_disponible(cliente, caplog, status):
    with _con_respuestas(cliente, _error_modelo(status), _resp("hola")) as create:
        with caplog.at_level(logging.WARNING, logger="app.llm.client"):
            assert cliente.chat([{"role": "user", "content": "x"}]) == "hola"
    modelos = [c.kwargs["model"] for c in create.call_args_list]
    assert modelos == ["principal/modelo", "respaldo/uno"]
    assert "principal/modelo" in caplog.text and "respaldo/uno" in caplog.text


def test_modelo_caido_se_salta_en_llamadas_siguientes(cliente):
    with _con_respuestas(cliente, _error_modelo(), _resp("a"), _resp("b")) as create:
        cliente.chat([{"role": "user", "content": "x"}])
        cliente.chat([{"role": "user", "content": "x"}])
    assert [c.kwargs["model"] for c in create.call_args_list] == [
        "principal/modelo", "respaldo/uno", "respaldo/uno",
    ]


def test_timeout_no_activa_respaldo(cliente):
    timeout = together.APITimeoutError(request=httpx.Request("POST", "http://x"))
    with _con_respuestas(cliente, timeout) as create:
        with pytest.raises(together.APITimeoutError):
            cliente.chat([{"role": "user", "content": "x"}])
    assert create.call_count == 1


def test_otro_400_no_activa_respaldo(cliente):
    req = httpx.Request("POST", "http://x")
    err = together.BadRequestError(
        "bad", response=httpx.Response(400, request=req),
        body={"error": {"message": "max_tokens too large", "code": "invalid_request"}},
    )
    with _con_respuestas(cliente, err) as create:
        with pytest.raises(together.BadRequestError):
            cliente.chat([{"role": "user", "content": "x"}])
    assert create.call_count == 1


def test_todos_los_modelos_caidos_propaga_el_error(cliente):
    with _con_respuestas(cliente, _error_modelo(), _error_modelo(), _error_modelo()):
        with pytest.raises(together.BadRequestError):
            cliente.chat([{"role": "user", "content": "x"}])
