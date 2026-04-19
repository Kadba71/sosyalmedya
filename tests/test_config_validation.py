from app.config import Settings


def test_production_config_rejects_placeholder_secrets() -> None:
    settings = Settings(
        app_env="production",
        secret_key="change-me",
        app_encryption_key="change-me-too",
        internal_agent_token="change-internal-agent-token",
        trends_provider="llm",
        prompt_provider="llm",
        video_provider="kling",
    )

    try:
        settings.validate_runtime_configuration()
    except ValueError as exc:
        assert "Insecure production configuration" in str(exc)
    else:
        raise AssertionError("Expected production configuration validation to fail")


def test_production_config_rejects_dummy_providers() -> None:
    settings = Settings(
        app_env="production",
        secret_key="secure-secret",
        app_encryption_key="secure-encryption-key",
        internal_agent_token="secure-internal-token",
        trends_provider="dummy",
        prompt_provider="llm",
        video_provider="kling",
    )

    try:
        settings.validate_runtime_configuration()
    except ValueError as exc:
        assert "Dummy providers" in str(exc)
    else:
        raise AssertionError("Expected dummy provider validation to fail")