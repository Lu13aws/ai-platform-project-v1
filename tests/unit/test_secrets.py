import os
from unittest.mock import MagicMock, patch

from aiplatform.secrets import load_json_secret_into_env


def test_noop_outside_lambda(monkeypatch):
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)

    with patch("aiplatform.secrets.boto3") as mock_boto3:
        load_json_secret_into_env("ai-platform/app-secrets")

    mock_boto3.client.assert_not_called()


def test_loads_secret_into_env_when_in_lambda(monkeypatch):
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "some-function")
    monkeypatch.delenv("SOME_SECRET_KEY", raising=False)

    mock_client = MagicMock()
    mock_client.get_secret_value.return_value = {
        "SecretString": '{"SOME_SECRET_KEY": "fetched-value"}'
    }

    with patch("aiplatform.secrets.boto3") as mock_boto3:
        mock_boto3.client.return_value = mock_client
        load_json_secret_into_env("ai-platform/app-secrets")

    mock_client.get_secret_value.assert_called_once_with(SecretId="ai-platform/app-secrets")
    assert os.environ["SOME_SECRET_KEY"] == "fetched-value"


def test_does_not_override_an_already_set_env_var(monkeypatch):
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "some-function")
    monkeypatch.setenv("SOME_SECRET_KEY", "already-set")

    mock_client = MagicMock()
    mock_client.get_secret_value.return_value = {
        "SecretString": '{"SOME_SECRET_KEY": "from-secrets-manager"}'
    }

    with patch("aiplatform.secrets.boto3") as mock_boto3:
        mock_boto3.client.return_value = mock_client
        load_json_secret_into_env("ai-platform/app-secrets")

    assert os.environ["SOME_SECRET_KEY"] == "already-set"
