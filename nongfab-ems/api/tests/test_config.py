"""Regression test for the actual bug behind test_cors.py's live-verification
failure: the CORS unit tests build `Settings(...)` directly with keyword
arguments, which sails right past whether the *env var name* pydantic-
settings actually listens for matches what docker-compose/.env.example set
(API_CORS_ORIGINS) - a field named `cors_origins_raw` silently listens for
API_CORS_ORIGINS_RAW instead, so overriding via env var did nothing and the
default was always used. Only an env-var-driven Settings() construction
catches that class of bug.
"""

from nongfab_api.config import Settings


def test_cors_origins_is_read_from_the_documented_env_var(monkeypatch):
    monkeypatch.setenv("API_CORS_ORIGINS", "https://dashboard.example,https://staging.example")
    settings = Settings(_env_file=None)
    assert settings.cors_allow_origins == ["https://dashboard.example", "https://staging.example"]


def test_cors_origins_default_covers_the_default_vite_dev_port():
    settings = Settings(_env_file=None)
    assert "http://localhost:5173" in settings.cors_allow_origins
