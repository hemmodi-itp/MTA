import logging
import os
from typing import Optional

from connectors.llm.base import LLMConnector

_log = logging.getLogger("workflow.llm")


class BedrockConnector(LLMConnector):
    """
    AWS Bedrock via boto3 Converse API.

    Reads credentials from environment (supports both upper- and lower-case
    names, since python-dotenv on Windows loads them as-is):
        AWS_ACCESS_KEY_ID / aws_access_key_id
        AWS_SECRET_ACCESS_KEY / aws_secret_access_key
        AWS_SESSION_TOKEN / aws_session_token   (required for STS temp creds)
        AWS_DEFAULT_REGION / aws_region         (default: us-east-1)
    """

    DEFAULT_MODEL = "us.anthropic.claude-sonnet-4-20250514-v1:0"
    DEFAULT_REGION = "us-east-1"
    MAX_TOKENS = 8192

    def __init__(
        self,
        model: Optional[str] = None,
        region: Optional[str] = None,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        session_token: Optional[str] = None,
    ) -> None:
        self.model = model or self.DEFAULT_MODEL
        self._region = (
            region
            or os.environ.get("AWS_DEFAULT_REGION")
            or os.environ.get("aws_region")
            or self.DEFAULT_REGION
        )
        self._access_key_id = (
            access_key_id
            or os.environ.get("AWS_ACCESS_KEY_ID")
            or os.environ.get("aws_access_key_id")
        )
        self._secret_access_key = (
            secret_access_key
            or os.environ.get("AWS_SECRET_ACCESS_KEY")
            or os.environ.get("aws_secret_access_key")
        )
        self._session_token = (
            session_token
            or os.environ.get("AWS_SESSION_TOKEN")
            or os.environ.get("aws_session_token")
        )

    def _make_client(self):
        try:
            import boto3  # type: ignore
            from botocore.config import Config  # type: ignore
        except ImportError:
            raise ImportError("boto3 not installed. Run: pip install boto3")

        kwargs = {
            "region_name": self._region,
            "config": Config(
                read_timeout=300,
                connect_timeout=10,
                retries={"max_attempts": 2},
            ),
        }
        if self._access_key_id:
            kwargs["aws_access_key_id"] = self._access_key_id
        if self._secret_access_key:
            kwargs["aws_secret_access_key"] = self._secret_access_key
        if self._session_token:
            kwargs["aws_session_token"] = self._session_token
        return boto3.client("bedrock-runtime", **kwargs)

    def generate(self, prompt: str) -> str:
        client = self._make_client()
        response = client.converse(
            modelId=self.model,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": self.MAX_TOKENS},
        )
        usage = response.get("usage", {})
        _log.info(
            f"[tokens] model={self.model}  "
            f"input={usage.get('inputTokens', '?')}  "
            f"output={usage.get('outputTokens', '?')}  "
            f"total={usage.get('inputTokens', 0) + usage.get('outputTokens', 0)}"
        )
        return response["output"]["message"]["content"][0]["text"]
