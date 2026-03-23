"""Tests für den ClaudeClient (Retry-Logik, Token-Tracking)."""
import pytest
from unittest.mock import MagicMock, patch


def _make_client(api_key="sk-ant-test-key"):
    """Erstellt ClaudeClient mit gemocktem Anthropic-SDK."""
    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_anthropic_instance = MagicMock()
        mock_anthropic_cls.return_value = mock_anthropic_instance

        mock_message = MagicMock()
        mock_message.content = [MagicMock(text='{"result": "ok"}')]
        mock_message.usage.input_tokens = 100
        mock_message.usage.output_tokens = 50
        mock_anthropic_instance.messages.create.return_value = mock_message

        from utils.claude_client import ClaudeClient
        client = ClaudeClient(api_key=api_key, retry_attempts=1, retry_delay=0.0)
        client.client = mock_anthropic_instance
        return client, mock_anthropic_instance


class TestClaudeClient:
    def test_analyze_returns_string(self):
        client, _ = _make_client()
        result = client.analyze("Teste diese Analyse")
        assert isinstance(result, str)

    def test_analyze_calls_messages_create(self):
        client, mock_api = _make_client()
        client.analyze("Test prompt")
        mock_api.messages.create.assert_called_once()

    def test_token_stats_structure(self):
        client, _ = _make_client()
        client.analyze("Test")
        stats = client.token_stats()
        assert "total_input_tokens" in stats
        assert "total_output_tokens" in stats
        assert "total_calls" in stats

    def test_token_tracking_increments(self):
        client, _ = _make_client()
        client.analyze("Erster Aufruf")
        client.analyze("Zweiter Aufruf")
        stats = client.token_stats()
        assert stats["total_calls"] == 2
        assert stats["total_input_tokens"] >= 200  # 2 × 100

    def test_retry_on_rate_limit(self):
        """Bei RateLimitError soll retry stattfinden."""
        import anthropic

        with patch("anthropic.Anthropic") as mock_anthropic_cls:
            mock_instance = MagicMock()
            mock_anthropic_cls.return_value = mock_instance

            mock_message = MagicMock()
            mock_message.content = [MagicMock(text="ok")]
            mock_message.usage.input_tokens = 10
            mock_message.usage.output_tokens = 5

            mock_instance.messages.create.side_effect = [
                anthropic.RateLimitError(
                    message="rate limit",
                    response=MagicMock(status_code=429, headers={}),
                    body={},
                ),
                mock_message,
            ]

            from utils.claude_client import ClaudeClient
            client = ClaudeClient(api_key="sk-ant-test", retry_attempts=3, retry_delay=0.0)
            client.client = mock_instance

            with patch("time.sleep"):
                result = client.analyze("Test")

            assert mock_instance.messages.create.call_count == 2

    def test_analyze_with_system_prompt(self):
        client, mock_api = _make_client()
        result = client.analyze(
            prompt="Analyse",
            system_prompt="Du bist ein Trading-Analyst.",
        )
        assert isinstance(result, str)
        call_kwargs = mock_api.messages.create.call_args[1]
        assert "system" in call_kwargs
