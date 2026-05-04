"""
TealBedrock Client

Drop-in replacement for AWS Bedrock client with integrated security and cost tracking.
Supports Claude, Titan, Jurassic, Command, and Llama models via AWS Bedrock Runtime.
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

from ..guardrails.engine import GuardrailEngine, GuardrailEngineResult
from ..cost.tracker import CostTracker
from ..cost.budget import BudgetManager
from ..cost.storage import CostStorage
from ..cost.types import TokenUsage, CostRecord
from ..cost.utils import generate_id


class TealBedrockConfig(BaseModel):
    """Configuration for TealBedrock client."""

    region: str = Field(default="us-east-1", description="AWS region")
    model: str = Field(default="anthropic.claude-v2", description="Bedrock model ID")
    agent_id: Optional[str] = Field(default="default-agent", description="Agent ID for tracking")
    enable_guardrails: bool = Field(default=True, description="Enable guardrails")
    enable_cost_tracking: bool = Field(default=True, description="Enable cost tracking")
    guardrail_engine: Optional[GuardrailEngine] = Field(default=None, description="Guardrail engine instance")
    cost_tracker: Optional[CostTracker] = Field(default=None, description="Cost tracker instance")
    budget_manager: Optional[BudgetManager] = Field(default=None, description="Budget manager instance")
    cost_storage: Optional[CostStorage] = Field(default=None, description="Cost storage instance")
    aws_access_key_id: Optional[str] = Field(default=None, description="AWS access key ID")
    aws_secret_access_key: Optional[str] = Field(default=None, description="AWS secret access key")
    aws_session_token: Optional[str] = Field(default=None, description="AWS session token")

    class Config:
        arbitrary_types_allowed = True


class BedrockResponse(BaseModel):
    """Bedrock model invocation response."""

    text: str
    model: str
    usage: Dict[str, int]
    stop_reason: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    security: Optional[Dict[str, Any]] = None


class TealBedrock:
    """
    TealBedrock client - drop-in replacement for AWS Bedrock with security.

    Provides integrated guardrails, cost tracking, and budget management
    for AWS Bedrock Runtime API calls.

    Supported models:
    - Anthropic Claude (claude-v2, claude-instant-v1, claude-3-*)
    - Amazon Titan (titan-text-express-v1, titan-text-lite-v1)
    - AI21 Jurassic (j2-mid-v1, j2-ultra-v1)
    - Cohere Command (command-text-v14, command-light-text-v14)
    - Meta Llama (llama2-13b-chat-v1, llama2-70b-chat-v1)
    """

    def __init__(self, config: Optional[TealBedrockConfig] = None, **kwargs: Any):
        """Initialize TealBedrock client."""
        if config is None:
            config = TealBedrockConfig(**kwargs)
        self._config = config
        self._client = None
        self._init_client()

    def _init_client(self) -> None:
        """Initialize the Bedrock Runtime client."""
        try:
            import boto3

            session_kwargs: Dict[str, Any] = {"region_name": self._config.region}
            if self._config.aws_access_key_id:
                session_kwargs["aws_access_key_id"] = self._config.aws_access_key_id
            if self._config.aws_secret_access_key:
                session_kwargs["aws_secret_access_key"] = self._config.aws_secret_access_key
            if self._config.aws_session_token:
                session_kwargs["aws_session_token"] = self._config.aws_session_token

            session = boto3.Session(**session_kwargs)
            self._client = session.client("bedrock-runtime")
        except ImportError:
            self._client = None
        except Exception:
            self._client = None

    async def invoke_model(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> BedrockResponse:
        """
        Invoke a Bedrock model with governance.

        Args:
            prompt: The input prompt
            model: Model ID (overrides config)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            **kwargs: Additional model parameters

        Returns:
            BedrockResponse with text, usage, and security metadata
        """
        import json

        model_id = model or self._config.model

        # Build request body based on model provider
        body = self._build_request_body(model_id, prompt, max_tokens, temperature, **kwargs)

        if self._client is None:
            raise RuntimeError("Bedrock client not initialized. Check AWS credentials and boto3 installation.")

        # Invoke model
        response = self._client.invoke_model(
            modelId=model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )

        # Parse response
        response_body = json.loads(response["body"].read())
        text, usage = self._parse_response(model_id, response_body)

        return BedrockResponse(
            text=text,
            model=model_id,
            usage=usage,
            stop_reason=response_body.get("stop_reason"),
        )

    def _build_request_body(
        self, model_id: str, prompt: str, max_tokens: int, temperature: float, **kwargs: Any
    ) -> Dict[str, Any]:
        """Build provider-specific request body."""
        if "anthropic" in model_id:
            return {
                "prompt": f"\n\nHuman: {prompt}\n\nAssistant:",
                "max_tokens_to_sample": max_tokens,
                "temperature": temperature,
                **kwargs,
            }
        elif "titan" in model_id:
            return {
                "inputText": prompt,
                "textGenerationConfig": {
                    "maxTokenCount": max_tokens,
                    "temperature": temperature,
                },
            }
        elif "ai21" in model_id or "j2" in model_id:
            return {
                "prompt": prompt,
                "maxTokens": max_tokens,
                "temperature": temperature,
            }
        elif "cohere" in model_id or "command" in model_id:
            return {
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        elif "meta" in model_id or "llama" in model_id:
            return {
                "prompt": prompt,
                "max_gen_len": max_tokens,
                "temperature": temperature,
            }
        else:
            return {"prompt": prompt, "max_tokens": max_tokens, "temperature": temperature}

    def _parse_response(self, model_id: str, body: Dict[str, Any]) -> tuple:
        """Parse provider-specific response body."""
        if "anthropic" in model_id:
            text = body.get("completion", "")
            usage = {
                "input_tokens": body.get("usage", {}).get("input_tokens", 0),
                "output_tokens": body.get("usage", {}).get("output_tokens", 0),
            }
        elif "titan" in model_id:
            results = body.get("results", [{}])
            text = results[0].get("outputText", "") if results else ""
            usage = {
                "input_tokens": body.get("inputTextTokenCount", 0),
                "output_tokens": results[0].get("tokenCount", 0) if results else 0,
            }
        elif "ai21" in model_id or "j2" in model_id:
            completions = body.get("completions", [{}])
            text = completions[0].get("data", {}).get("text", "") if completions else ""
            usage = {"input_tokens": 0, "output_tokens": 0}
        elif "cohere" in model_id or "command" in model_id:
            generations = body.get("generations", [{}])
            text = generations[0].get("text", "") if generations else ""
            usage = {"input_tokens": 0, "output_tokens": 0}
        elif "meta" in model_id or "llama" in model_id:
            text = body.get("generation", "")
            usage = {
                "input_tokens": body.get("prompt_token_count", 0),
                "output_tokens": body.get("generation_token_count", 0),
            }
        else:
            text = str(body)
            usage = {"input_tokens": 0, "output_tokens": 0}

        return text, usage

    def get_config(self) -> TealBedrockConfig:
        """Get current configuration."""
        return self._config
