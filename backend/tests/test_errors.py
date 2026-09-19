"""Each typed exception maps to a correct user-safe message and correct
SSE error shape (to_sse_error). No provider, no DB — pure unit tests."""
from app.core.errors import (
    ConfigurationError,
    DatabaseUnavailableError,
    MalformedOutputError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    PromptValidationError,
    RetrievalEmptyError,
    to_sse_error,
)


def test_provider_unavailable_error_shape():
    exc = ProviderUnavailableError(message="Local model unreachable.", detail="connection refused")
    assert exc.message == "Local model unreachable."
    assert exc.detail == "connection refused"
    assert str(exc) == "connection refused"  # detail preferred in logs over message


def test_provider_timeout_error_shape():
    exc = ProviderTimeoutError(message="Took too long.", detail="httpx.TimeoutException: ...")
    assert to_sse_error(exc) == {"type": "error", "message": "Took too long."}


def test_database_unavailable_error_never_leaks_detail_into_sse():
    exc = DatabaseUnavailableError(
        message="We're having trouble reaching the database right now. Please try again shortly.",
        detail="asyncpg.exceptions.ConnectionDoesNotExistError: connection was closed",
    )
    event = to_sse_error(exc)
    assert event["message"] == exc.message
    assert "asyncpg" not in event["message"]
    assert "ConnectionDoesNotExistError" not in str(event)


def test_configuration_error_shape():
    exc = ConfigurationError(
        message="The server is misconfigured: no cloud provider credentials.",
        detail="DEFAULT_LLM_PROVIDER=anthropic but GROQ_API_KEY is not set.",
    )
    assert to_sse_error(exc)["message"] == exc.message


def test_retrieval_empty_and_malformed_output_and_prompt_validation_construct_cleanly():
    # These don't have special behavior beyond the base shape — this just
    # confirms every declared exception type is constructible and conforms
    # to the same (message, detail) -> to_sse_error contract.
    for cls in (RetrievalEmptyError, MalformedOutputError, PromptValidationError):
        exc = cls(message="user-safe", detail="internal-only")
        event = to_sse_error(exc)
        assert event == {"type": "error", "message": "user-safe"}
        assert "internal-only" not in str(event)


def test_str_falls_back_to_message_when_no_detail():
    exc = ProviderUnavailableError(message="Local model unreachable.")
    assert str(exc) == "Local model unreachable."
