"""Configuração lida do ambiente (.env, nunca no git; modelo em .env.example)."""

from functools import cached_property
from zoneinfo import ZoneInfo

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Chave do celular (MacroDroid) para o webhook. Mínimo de 32 caracteres.
    API_KEY: str = Field(..., min_length=32)
    # Senha do site. Exponha a porta só numa rede privada (VPN, LAN); a senha é a segunda camada.
    WEB_PASSWORD: str = Field(..., min_length=8)
    # Assina o cookie de sessão.
    SESSION_SECRET: str = Field(..., min_length=32)

    DATABASE_PATH: str = "/data/financas.db"
    HOST: str = "127.0.0.1"
    PORT: int = 8095
    TIMEZONE: str = "America/Sao_Paulo"

    # Fila de avisos: diretório do host que a unit financas-avisos.path entrega (ver deploy/).
    AVISOS_FILA: str = "/avisos-fila"
    AVISOS_REMETENTE: str = "financas"
    # Endereço do site como o celular e o PC o veem (para o link do aviso).
    URL_PUBLICA: str = "http://localhost:8095"
    # Seu nome como o banco escreve no Pix (ex.: FULANO DE TAL): o que entra vindo dele é transferência
    # entre contas suas, não renda. Vazio = não reconhece.
    TITULAR: str = ""

    # Camada opcional de LLM para classificar o que a regra não sabe (Gemini).
    GEMINI_API_KEY: str = ""
    LLM_MODEL: str = "gemini-3.1-flash-lite"
    LLM_TIMEOUT: float = 8.0
    LLM_MIN_CONFIDENCE: float = 0.8

    # Papéis de parede do site (enviados pela tela Ajustes).
    PAPEIS_DIR: str = "/data/papeis"

    DEDUP_WINDOW_MINUTES: int = 10
    QUEUE_MAXSIZE: int = 500
    MAX_ATTEMPTS: int = 3

    @cached_property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.TIMEZONE)

    @property
    def llm_configured(self) -> bool:
        return bool(self.GEMINI_API_KEY)


settings = Settings()
