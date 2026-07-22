"""Verificación mínima de que `modal deploy` funciona en esta cuenta antes de gastar en GPU."""
import modal

app = modal.App("tutor-finetuned-healthcheck")


@app.function()
def ping() -> str:
    return "ok"
