"""
TealAzureOpenAI Client

Drop-in replacement for Azure OpenAI client with integrated security and cost tracking.
"""

from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field

from ..guardrails.engine import GuardrailEngine, GuardrailEngineResult
from ..cost.tracker import CostTracker
from ..cost.budget import BudgetManager, BudgetEnforcementResult
from ..cost.storage import CostStorage
from ..cost.types import TokenUsage, CostRecord
from ..cost.utils import generate_id
from ._optional import missing_provider_dependency_error


def _load_async_azure_openai():
    try:
        from openai import AsyncAzureOpenAI
    except ImportError as exc:
        raise missing_provider_dependency_error("Azure OpenAI", "azure-openai", "openai") from exc

    return AsyncAzureOpenAI


class TealAzureOpenAIConfig(BaseModel):
    """Configuration for TealAzureOpenAI client."""
    
    api_key: str = Field(..., description="Azure OpenAI API key")
    endpoint: str = Field(..., description="Azure OpenAI endpoint (e.g., https://your-resource.openai.azure.com)")
    api_version: Optional[str] = Field(default='2024-02-15-preview', description="Azure OpenAI API version")
    agent_id: Optional[str] = Field(default='default-agent', description="Agent ID for tracking")
    enable_guardrails: bool = Field(default=True, description="Enable guardrails")
    enable_cost_tracking: bool = Field(default=True, description="Enable cost tracking")
    guardrail_engine: Optional[GuardrailEngine] = Field(default=None, description="Guardrail engine instance")
    cost_tracker: Optional[CostTracker] = Field(default=None, description="Cost tracker instance")
    budget_manager: Optional[BudgetManager] = Field(default=None, description="Budget manager instance")
    cost_storage: Optional[CostStorage] = Field(default=None, description="Cost storage instance")
    azure_ad_token: Optional[str] = Field(default=None, description="Azure AD token for authentication")
    
    class Config:
        arbitrary_types_allowed = True


class AzureChatCompletionMessage(BaseModel):
    """Azure chat completion message."""
    
    role: Literal['system', 'user', 'assistant', 'function']
    content: str
    name: Optional[str] = None


class AzureChatCompletionRequest(BaseModel):
    """Azure chat completion request parameters."""
    
    deployment: str  # Azure uses deployment name instead of model
    messages: List[AzureChatCompletionMessage]
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    n: Optional[int] = None
    stream: Optional[bool] = None
    stop: Optional[List[str]] = None
    max_tokens: Optional[int] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    logit_bias: Optional[Dict[str, float]] = None
    user: Optional[str] = None


class SecurityMetadata(BaseModel):
    """Security metadata for Azure chat completion response."""
    
    guardrail_result: Optional[GuardrailEngineResult] = None
    cost_record: Optional[CostRecord] = None
    budget_check: Optional[Dict[str, Any]] = None
    
    class Config:
        arbitrary_types_allowed = True


class AzureChatCompletionResponse(BaseModel):
    """Azure chat completion response."""
    
    id: str
    object: str
    created: int
    model: str
    choices: List[Dict[str, Any]]
    usage: Dict[str, int]
    security: Optional[SecurityMetadata] = None


class ChatCompletions:
    """Chat completions API."""
    
    def __init__(self, parent: 'TealAzureOpenAI'):
        self.parent = parent
    
    async def create(self, **kwargs) -> AzureChatCompletionResponse:
        """
        Create a chat completion with security and cost tracking.
        
        Args:
            **kwargs: Chat completion parameters (deployment, messages, etc.)
            
        Returns:
            AzureChatCompletionResponse with security metadata
            
        Raises:
            ValueError: If guardrails fail or budget is exceeded
        """
        return await self.parent._create_chat_completion(**kwargs)


class DeploymentsChatCompletions:
    """Deployments chat completions API (Azure-specific)."""
    
    def __init__(self, parent: 'TealAzureOpenAI'):
        self.parent = parent
    
    async def create(self, **kwargs) -> AzureChatCompletionResponse:
        """
        Create a chat completion with security and cost tracking.
        
        Args:
            **kwargs: Chat completion parameters (deployment, messages, etc.)
            
        Returns:
            AzureChatCompletionResponse with security metadata
            
        Raises:
            ValueError: If guardrails fail or budget is exceeded
        """
        return await self.parent._create_chat_completion(**kwargs)


class DeploymentsChat:
    """Deployments chat API."""
    
    def __init__(self, parent: 'TealAzureOpenAI'):
        self.parent = parent
    
    @property
    def completions(self) -> DeploymentsChatCompletions:
        """Access deployments chat completions API."""
        return DeploymentsChatCompletions(self.parent)


class Deployments:
    """Deployments API (Azure-specific)."""
    
    def __init__(self, parent: 'TealAzureOpenAI'):
        self.parent = parent
    
    @property
    def chat(self) -> DeploymentsChat:
        """Access deployments chat API."""
        return DeploymentsChat(self.parent)


class Chat:
    """Chat API."""
    
    def __init__(self, parent: 'TealAzureOpenAI'):
        self.parent = parent
    
    @property
    def completions(self) -> ChatCompletions:
        """Access chat completions API."""
        return ChatCompletions(self.parent)


class TealAzureOpenAI:
    """
    TealAzureOpenAI client - drop-in replacement for Azure OpenAI with security.
    
    Provides integrated guardrails, cost tracking, and budget management
    for Azure OpenAI API calls.
    
    Example:
        ```python
        from tealtiger import TealAzureOpenAI, TealAzureOpenAIConfig
        from tealtiger.guardrails import GuardrailEngine
        from tealtiger.cost import CostTracker, BudgetManager, InMemoryCostStorage
        
        # Create components
        engine = GuardrailEngine()
        tracker = CostTracker()
        storage = InMemoryCostStorage()
        budget_manager = BudgetManager(storage)
        
        # Create guarded client
        client = TealAzureOpenAI(TealAzureOpenAIConfig(
            api_key="your-api-key",
            endpoint="https://your-resource.openai.azure.com",
            agent_id="my-agent",
            guardrail_engine=engine,
            cost_tracker=tracker,
            budget_manager=budget_manager,
            cost_storage=storage
        ))
        
        # Use like normal Azure OpenAI client
        response = await client.chat.completions.create(
            deployment="gpt-4-deployment",
            messages=[{"role": "user", "content": "Hello!"}]
        )
        
        # Or use Azure-specific deployments API
        response = await client.deployments.chat.completions.create(
            deployment="gpt-4-deployment",
            messages=[{"role": "user", "content": "Hello!"}]
        )
        ```
    """
    
    def __init__(self, config: TealAzureOpenAIConfig):
        """
        Initialize TealAzureOpenAI client.
        
        Args:
            config: Configuration for the guarded client
        """
        self.config = config
        
        # Initialize Azure OpenAI client
        # Note: Azure AD token authentication requires azure-identity package
        # For now, we use API key authentication
        async_azure_openai = _load_async_azure_openai()
        self.client = async_azure_openai(
            api_key=config.api_key,
            azure_endpoint=config.endpoint,
            api_version=config.api_version
        )
        
        self.guardrail_engine = config.guardrail_engine
        self.cost_tracker = config.cost_tracker
        self.budget_manager = config.budget_manager
        self.cost_storage = config.cost_storage
    
    @property
    def chat(self) -> Chat:
        """Access chat API."""
        return Chat(self)
    
    @property
    def deployments(self) -> Deployments:
        """Access deployments API (Azure-specific)."""
        return Deployments(self)
    
    def map_deployment_to_model(self, deployment: str) -> str:
        """
        Map Azure deployment name to OpenAI model name for pricing.
        
        Azure deployments can have custom names, so we need to infer the
        underlying model from the deployment name for accurate pricing.
        
        Args:
            deployment: Azure deployment name
            
        Returns:
            OpenAI model name for pricing
        """
        # Common Azure deployment naming patterns
        lower_deployment = deployment.lower()
        
        # GPT-4 variants
        if 'gpt-4-32k' in lower_deployment or 'gpt4-32k' in lower_deployment:
            return 'gpt-4-32k'
        if 'gpt-4-turbo' in lower_deployment or 'gpt4-turbo' in lower_deployment:
            return 'gpt-4-turbo'
        if 'gpt-4' in lower_deployment or 'gpt4' in lower_deployment:
            return 'gpt-4'
        
        # GPT-3.5 variants
        if 'gpt-35-turbo-16k' in lower_deployment or 'gpt-3.5-turbo-16k' in lower_deployment:
            return 'gpt-3.5-turbo-16k'
        if 'gpt-35-turbo' in lower_deployment or 'gpt-3.5-turbo' in lower_deployment:
            return 'gpt-3.5-turbo'
        
        # Default to gpt-3.5-turbo if unknown
        return 'gpt-3.5-turbo'
    
    async def _create_chat_completion(self, **kwargs) -> AzureChatCompletionResponse:
        """
        Internal method to create a chat completion with security and cost tracking.
        
        Args:
            **kwargs: Chat completion parameters (deployment, messages, etc.)
            
        Returns:
            AzureChatCompletionResponse with security metadata
            
        Raises:
            ValueError: If guardrails fail or budget is exceeded
        """
        request_id = generate_id()
        agent_id = self.config.agent_id
        security = SecurityMetadata()
        
        # Get deployment name (required for Azure)
        deployment = kwargs.get('deployment')
        if not deployment:
            raise ValueError("deployment parameter is required for Azure OpenAI")
        
        try:
            # 1. Run input guardrails
            if self.config.enable_guardrails and self.guardrail_engine:
                user_messages = '\n'.join(
                    m['content'] for m in kwargs.get('messages', [])
                    if m.get('role') == 'user'
                )
                guardrail_result = await self.guardrail_engine.execute(user_messages)
                security.guardrail_result = guardrail_result
                
                if not guardrail_result.passed:
                    failed = ', '.join(guardrail_result.get_failed_guardrails())
                    raise ValueError(
                        f"Guardrail check failed: {failed} "
                        f"(Risk: {guardrail_result.max_risk_score})"
                    )
            
            # 2. Estimate cost and check budget
            if self.config.enable_cost_tracking and self.cost_tracker:
                # Map deployment to model for pricing
                model = self.map_deployment_to_model(deployment)
                
                # Estimate tokens (rough approximation: 4 chars = 1 token)
                input_text = '\n'.join(
                    m.get('content', '') for m in kwargs.get('messages', [])
                )
                estimated_input_tokens = len(input_text) // 4
                estimated_output_tokens = kwargs.get('max_tokens', 500)
                
                estimate = self.cost_tracker.estimate_cost(
                    model,
                    TokenUsage(
                        input_tokens=estimated_input_tokens,
                        output_tokens=estimated_output_tokens,
                        total_tokens=estimated_input_tokens + estimated_output_tokens
                    ),
                    'openai'  # Azure uses OpenAI pricing
                )
                
                if self.budget_manager:
                    budget_check = await self.budget_manager.check_budget(
                        agent_id, estimate.estimated_cost
                    )
                    security.budget_check = budget_check.dict()
                    
                    if not budget_check.allowed:
                        raise ValueError(
                            f"Budget exceeded: {budget_check.blocked_by.name} "
                            f"(Limit: {budget_check.blocked_by.limit})"
                        )
            
            # 3. Make actual API call
            # Azure OpenAI uses 'model' parameter instead of 'deployment' in the SDK
            api_kwargs = {**kwargs}
            api_kwargs['model'] = api_kwargs.pop('deployment')
            
            response = await self.client.chat.completions.create(**api_kwargs)
            
            # 4. Run output guardrails
            if self.config.enable_guardrails and self.guardrail_engine:
                assistant_message = response.choices[0].message.content
                output_result = await self.guardrail_engine.execute(assistant_message)
                
                if not output_result.passed:
                    failed = ', '.join(output_result.get_failed_guardrails())
                    raise ValueError(
                        f"Output guardrail check failed: {failed} "
                        f"(Risk: {output_result.max_risk_score})"
                    )
            
            # 5. Track actual cost
            if self.config.enable_cost_tracking and self.cost_tracker:
                # Map deployment to model for pricing
                model = self.map_deployment_to_model(deployment)
                
                cost_record = self.cost_tracker.calculate_actual_cost(
                    request_id,
                    agent_id,
                    model,
                    TokenUsage(
                        input_tokens=response.usage.prompt_tokens,
                        output_tokens=response.usage.completion_tokens,
                        total_tokens=response.usage.total_tokens
                    ),
                    'openai'  # Azure uses OpenAI pricing
                )
                security.cost_record = cost_record
                
                if self.cost_storage:
                    await self.cost_storage.store(cost_record)
                
                if self.budget_manager:
                    await self.budget_manager.record_cost(cost_record)
            
            # 6. Return response with security metadata
            return AzureChatCompletionResponse(
                id=response.id,
                object=response.object,
                created=response.created,
                model=response.model,
                choices=[
                    {
                        'index': c.index,
                        'message': {
                            'role': c.message.role,
                            'content': c.message.content,
                        },
                        'finish_reason': c.finish_reason,
                    }
                    for c in response.choices
                ],
                usage={
                    'prompt_tokens': response.usage.prompt_tokens,
                    'completion_tokens': response.usage.completion_tokens,
                    'total_tokens': response.usage.total_tokens,
                },
                security=security
            )
        
        except Exception as e:
            if isinstance(e, ValueError):
                raise
            raise ValueError(f"TealAzureOpenAI error: {str(e)}")
