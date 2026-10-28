"""Autenticação: o site exige sessão, o webhook exige a chave do celular."""

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


def test_site_exige_senha_e_webhook_exige_chave(con):
    with TestClient(app) as c:
        assert c.get("/api/painel").status_code == 401
        assert c.post("/api/login", json={"senha": "errada"}).status_code == 401
        assert c.post("/api/login", json={"senha": settings.WEB_PASSWORD}).status_code == 200
        assert c.get("/api/painel").status_code == 200
        corpo = {"package": "com.nu.production", "title": "Compra aprovada", "text": "Compra de R$ 12,50 aprovada em Mercadinho Exemplo"}
        assert c.post("/api/v1/transaction/webhook", json=corpo).status_code == 401
        r = c.post("/api/v1/transaction/webhook", json=corpo, headers={"Authorization": f"Bearer {settings.API_KEY}"})
        assert r.status_code == 202 and r.json()["status"] == "queued"
