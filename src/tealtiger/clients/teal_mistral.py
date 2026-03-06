"""
TealMistral Client

Drop-in replacement for Mistral AI client with integrated security and cost tracking.
Supports chat with European data residency.
"""

from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field
from mistralai.client import MistralClient
from mistralai.models.chat_completion import ChatMessage

from ..guardrails.engine import GuardrailEngine, GuardrailEngineResult
from ..cost.tracker import CostTracker
from ..cost.budget import BudgetManager
from ..cost.storage import CostStorage
from ..cost.types import TokenUsage, CostRecord
from ..cost.utils import generate_id


class TealMistralConfig(BaseModel):
    """Configuration for TealMistral client."""
    
    api_key: str = Field(..., description="Mistral AI API key")
    model: str = Field(default='mistral-small', description="Model name (mistral-small, mistral-medium, mistral-large, mixtral)")
    agent_id: Optional[str] = Field(default='default-agent', description="Agent ID for tracking")
    enable_guardrails: bool = Field(default=True, description="Enable guardrails")
    enable_cost_tracking: bool = Field(default=True, description="Enable cost tracking")
    guardrail_engine: Optional[GuardrailEngine] = Field(default=None, description="Guardrail engine instance")
    cost_tracker: Optional[CostTracker] = Field(default=None, description="Cost tracker instance")
    budget_manager: Optional[BudgetManager] = Field(default=None, description="Budget manager instance")
    cost_storage: Optional[CostStorage] = Field(default=None, description="Cost storage instance")
    endpoint: Optional[str] = Field(default=None, description="Custom endpoint URL")
    
    class Config:
        arbitrary_types_allowed = True


class SecurityMetadata(BaseModel):
    """Security metadata for Mistral response."""
    
    guardrail_result: Optional[GuardrailEngineResult] = None
    cost_record: Optional[CostRecord] = None
    budget_check: Optional[Dict[str, Any]] = None
    
    class Config:
        arbitrary_types_allowed = True


class ChatResponse(BaseModel):
    """Mistral chat response."""
    
    text: str
    role: str
    finish_reason: Optional[str] = None
    usage: Dict[str, int]
    model: str
    security: Optional[SecurityMetadata] = None


class TealMistral:
    """
    TealMistral client - drop-in replacement for Mistral AI with security.
    
    Provides integrated guardrails, cost tracking, and budget management
    for Mistral AI API calls with European data residency.
    
    Key Features:
    - Chat with conversation history
    - European data residency (Paris, France)
    - OpenAI-compatible API
    - Streaming support
    - Multiple model sizes (small, medium, large, mixtral)
    
    Example:
        ```python
        from tealtiger import TealMistral, TealMistralConfig
        from tealtiger.guardrails import GuardrailEngine
        from tealtiger.cost import CostTracker, BudgetManager, InMemoryCostStorage
        
        # Create components
        engine = GuardrailEngine()
        tracker = CostTracker()
        storage = InMemoryCostStorage()
        budget_manager = BudgetManager(storage)
        
        # Create guarded client
        client = TealMistral(TealMistralConfig(
            api_key="your-api-key",
            model="mistral-small",
            agent_id="my-agent",
            guardrail_engine=engine,
            cost_tracker=tracker,
            budget_manager=budget_manager,
            cost_storage=storage
        ))
        
        # Use like normal Mistral client
        response = await client.chat(
            messages=[{"role": "user", "content": "Hello!"}],
            temperature=0.7
        )
        ```
    """
    
    def __init__(self, config: TealMistralConfig):
        """
        Initialize TealMistral client.
        
        Args:
            config: Configuration for the guarded client
        """
        self.config = config
        
        # Create Mistral client
        client_kwargs = {'api_key': config.api_key}
        if config.endpoint:
            client_kwargs['endpoint'] = config.endpoint
        
        self.client = MistralClient(**client_kwargs)
        
        self.guardrail_engine = config.guardrail_engine
        self.cost_tracker = config.cost_tracker
        self.budget_manager = config.budget_manager
        self.cost_storage = config.cost_storage
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> ChatResponse:
        """
        Chat with Mistral AI with security and cost tracking.
        
        Supports conversation history and streaming responses.
        
        Args:
            messages: List of messages
                     Format: [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
            **kwargs: Additional parameters
                - temperature: Sampling temperature (0.0-1.0)
                - max_tokens: Maximum tokens to generate
                - top_p: Nucleus sampling (0.0-1.0)
                - stream: Boolean for streaming responses
                - safe_mode: Boolean for safe mode (content filtering)
                - random_seed: Random seed for reproducibility
            
        Returns:
            ChatResponse with security metadata
            
        Raises:
            ValueError: If guardrails fail or budget is exceeded
        """
        request_id = generate_id()
        agent_id = self.config.agent_id
        security = SecurityMetadata()
        
        try:
            # Extract user message for guardrails
            user_message = ""
            for msg in messages:
                if msg.get('role') == 'user':
                    user_message = msg.get('content', '')
            
            # 1. Run input guardrails
            if self.config.enable_guardrails and self.guardrail_engine and user_message:
                guardrail_result = await self.guardrail_engine.execute(user_message)
                security.guardrail_result = guardrail_result
                
                if not guardrail_result.passed:
                    failed = ', '.join(guardrail_result.get_failed_guardrails())
                    raise ValueError(
                        f"Guardrail check failed: {failed} "
                        f"(Risk: {guardrail_result.max_risk_score})"
                    )
            
            # 2. Estimate cost and check budget
            if self.config.enable_cost_tracking and self.cost_tracker:
                estimated_input_tokens = sum(len(msg.get('content', '')) // 4 for msg in messages)
                estimated_output_tokens = kwargs.get('max_tokens', 500)
                
                estimate = self.cost_tracker.estimate_cost(
                    self.config.model,
                    TokenUsage(
                        input_tokens=estimated_input_tokens,
                        output_tokens=estimated_output_tokens,
                        total_tokens=estimated_input_tokens + estimated_output_tokens
                    ),
                    'mistral'
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
            
            # 3. Convert messages to Mistral format
            mistral_messages = [
                ChatMessage(role=msg['role'], content=msg['content'])
                for msg in messages
            ]
            
            # 4. Prepare request parameters
            request_params = {
                'model': self.config.model,
                'messages': mistral_messages,
            }
            
            # Add optional parameters
            if 'temperature' in kwargs:
                request_params['temperature'] = kwargs['temperature']
            if 'max_tokens' in kwargs:
                request_params['max_tokens'] = kwargs['max_tokens']
            if 'top_p' in kwargs:
                request_params['top_p'] = kwargs['top_p']
            if 'safe_mode' in kwargs:
                request_params['safe_mode'] = kwargs['safe_mode']
            if 'random_seed' in kwargs:
                request_params['random_seed'] = kwargs['random_seed']
            
            # 5. Make actual API call
            response = self.client.chat(**request_params)
            
            # Extract response text
            text = response.choices[0].message.content
            role = response.choices[0].message.role
            finish_reason = response.choices[0].finish_reason
            
            # 6. Run output guardrails
            if self.config.enable_guardrails and self.guardrail_engine:
                output_result = await self.guardrail_engine.execute(text)
                
                if not output_result.passed:
                    failed = ', '.join(output_result.get_failed_guardrails())
                    raise ValueError(
                        f"Output guardrail check failed: {failed} "
                        f"(Risk: {output_result.max_risk_score})"
                    )
            
            # 7. Track actual cost
            usage = {
                'input_tokens': response.usage.prompt_tokens if hasattr(response, 'usage') else 0,
                'output_tokens': response.usage.completion_tokens if hasattr(response, 'usage') else 0,
                'total_tokens': response.usage.total_tokens if hasattr(response, 'usage') else 0
            }
            
            if self.config.enable_cost_tracking and self.cost_tracker:
                cost_record = self.cost_tracker.calculate_actual_cost(
                    request_id,
                    agent_id,
                    self.config.model,
                    TokenUsage(
                        input_tokens=usage['input_tokens'],
                        output_tokens=usage['output_tokens'],
                        total_tokens=usage['total_tokens']
                    ),
                    'mistral'
                )
                security.cost_record = cost_record
                
                if self.cost_storage:
                    await self.cost_storage.store(cost_record)
                
                if self.budget_manager:
                    await self.budget_manager.record_cost(cost_record)
            
            # 8. Return response with security metadata
            return ChatResponse(
                text=text,
                role=role,
                finish_reason=finish_reason,
                usage=usage,
                model=self.config.model,
                security=security
            )
        
        except Exception as e:
            if isinstance(e, ValueError):
                raise
            raise ValueError(f"TealMistral error: {str(e)}")
