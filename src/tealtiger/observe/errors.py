"""Error classes for the observe() module."""


class UnsupportedProviderError(Exception):
    """Thrown when observe() receives a client that is not one of the 12 supported providers.

    Attributes:
        client_type: The type name of the unsupported client that was passed to observe().
    """

    def __init__(self, client_type: str) -> None:
        self.client_type = client_type
        super().__init__(
            f"Unsupported provider client: {client_type}. "
            f"observe() supports: OpenAI, Anthropic, Gemini, Bedrock, Azure OpenAI, "
            f"Cohere, Mistral, DeepSeek, Groq, xAI, Together, HF-TGI."
        )


class FrozenAgentError(Exception):
    """Thrown when a request is made through a proxy whose agent is frozen.

    The request never reaches the provider.

    Attributes:
        agent_id: The ID of the agent that is frozen.
        is_wildcard: Whether the freeze was caused by a wildcard freeze('*') call.
    """

    def __init__(self, agent_id: str, is_wildcard: bool) -> None:
        self.agent_id = agent_id
        self.is_wildcard = is_wildcard
        reason = (
            "All agents are frozen (wildcard freeze active)"
            if is_wildcard
            else f"Agent '{agent_id}' is frozen"
        )
        super().__init__(
            f"Request blocked: {reason}. Call unfreeze('{agent_id}') to restore."
        )
