"""
TealOpenAI Client

Drop-in replacement for OpenAI client with integrated security and cost tracking.
"""

from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
from openai import AsyncOpenAI

from ..guardrails.engine import GuardrailEngine, GuardrailEngineResult
from ..cost.tracker import CostTracker
from ..cost.budget import BudgetManager, BudgetEnforcementResult
from ..cost.storage import CostStorage
from ..cost.types import TokenUsage, CostRecord
from ..cost.utils import generate_id
from ..core.context.execution_context import ExecutionContext
from ..core.context.context_manager import ContextManager
from ..core.engine.types import Decision
from ..core.engine.teal_engine import TealEngine
from ..core.guard.teal_guard import TealGuard
from ..core.audit.teal_audit import TealAudit


class TealOpenAIConfig(BaseModel):
    """Configuration for TealOpenAI client."""
    
    api_key: str = Field(..., description="OpenAI API key")
    agent_id: Optional[str] = Field(default='default-agent', description="Agent ID for tracking")
    enable_guardrails: bool = Field(default=True, description="Enable guardrails")
    enable_cost_tracking: bool = Field(default=True, description="Enable cost tracking")
    guardrail_engine: Optional[GuardrailEngine] = Field(default=None, description="Guardrail engine instance")
    cost_tracker: Optional[CostTracker] = Field(default=None, description="Cost tracker instance")
    budget_manager: Optional[BudgetManager] = Field(default=None, description="Budget manager instance")
    cost_storage: Optional[CostStorage] = Field(default=None, description="Cost storage instance")
    base_url: Optional[str] = Field(default=None, description="OpenAI base URL")
    organization: Optional[str] = Field(default=None, description="Organization ID")
    # Enterprise features
    engine: Optional[TealEngine] = Field(default=None, description="TealEngine instance for policy evaluation")
    guard: Optional[TealGuard] = Field(default=None, description="TealGuard instance for content validation")
    audit: Optional[TealAudit] = Field(default=None, description="TealAudit instance for audit logging")
    
    class Config:
        arbitrary_types_allowed = True


class ChatCompletionMessage(BaseModel):
    """Chat completion message."""
    
    role: Literal['system', 'user', 'assistant', 'function']
    content: str
    name: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    """Chat completion request parameters."""
    
    model: str
    messages: List[ChatCompletionMessage]
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    n: Optional[int] = None
    stream: Optional[bool] = None
    stop: Optional[List[str]] = None
    max_tokens: Optional[int] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    user: Optional[str] = None


class SecurityMetadata(BaseModel):
    """Security metadata for chat completion response."""
    
    guardrail_result: Optional[GuardrailEngineResult] = None
    cost_record: Optional[CostRecord] = None
    budget_check: Optional[Dict[str, Any]] = None
    
    class Config:
        arbitrary_types_allowed = True


class ChatCompletionResponse(BaseModel):
    """Chat completion response."""
    
    id: str
    object: str
    created: int
    model: str
    choices: List[Dict[str, Any]]
    usage: Dict[str, int]
    security: Optional[SecurityMetadata] = None


class ChatCompletions:
    """Chat completions API."""
    
    def __init__(self, parent: 'TealOpenAI'):
        self.parent = parent
    
    async def create(self, **kwargs) -> ChatCompletionResponse:
        """
        Create a chat completion with security and cost tracking.
        
        Args:
            **kwargs: Chat completion parameters (model, messages, etc.)
                     context: Optional[ExecutionContext] - Execution context for tracing
            
        Returns:
            ChatCompletionResponse with security metadata
            
        Raises:
            ValueError: If guardrails fail or budget is exceeded
        """
        request_id = generate_id()
        agent_id = self.parent.config.agent_id
        security = SecurityMetadata()
        
        # Extract or create execution context
        context = kwargs.pop('context', None)
        if context is None:
            context = ContextManager.create_context()
        elif not isinstance(context, ExecutionContext):
            # Convert dict to ExecutionContext if needed
            context = ExecutionContext(**context) if isinstance(context, dict) else context
        
        try:
            # 1. Policy evaluation with TealEngine (if configured)
            if self.parent.engine:
                from ..core.engine.types import RequestContext
                policy_context = RequestContext(
                    agent_id=agent_id,
                    action='llm.request',
                    context=context,
                    model=kwargs.get('model'),
                    content='\n'.join(m.get('content', '') for m in kwargs.get('messages', []))
                )
                decision = self.parent.engine.evaluate(policy_context)
                
                # Log decision with audit
                if self.parent.audit:
                    self.parent.audit.log_decision(decision, context)
                
                # Handle non-ALLOW decisions
                if decision.action != 'ALLOW':
                    raise ValueError(
                        f"Policy evaluation failed: {decision.action} - {decision.reason}"
                    )
            
            # 2. Content validation with TealGuard (if configured)
            if self.parent.guard:
                user_messages = '\n'.join(
                    m['content'] for m in kwargs.get('messages', []) 
                    if m.get('role') == 'user'
                )
                guard_decision = self.parent.guard.check(user_messages, context)
                
                # Log guard decision
                if self.parent.audit:
                    self.parent.audit.log_decision(guard_decision, context)
                
                if guard_decision.action != 'ALLOW':
                    raise ValueError(
                        f"Content validation failed: {guard_decision.action} - {guard_decision.reason}"
                    )
            
            # 3. Run input guardrails (legacy support)
            if self.parent.config.enable_guardrails and self.parent.guardrail_engine:
                user_messages = '\n'.join(
                    m['content'] for m in kwargs.get('messages', []) 
                    if m.get('role') == 'user'
                )
                guardrail_result = await self.parent.guardrail_engine.execute(user_messages)
                security.guardrail_result = guardrail_result
                
                if not guardrail_result.passed:
                    failed = ', '.join(guardrail_result.get_failed_guardrails())
                    raise ValueError(
                        f"Guardrail check failed: {failed} "
                        f"(Risk: {guardrail_result.max_risk_score})"
                    )
            
            # 4. Estimate cost and check budget
            if self.parent.config.enable_cost_tracking and self.parent.cost_tracker:
                input_text = '\n'.join(
                    m.get('content', '') for m in kwargs.get('messages', [])
                )
                estimated_input_tokens = len(input_text) // 4
                estimated_output_tokens = kwargs.get('max_tokens', 500)
                
                estimate = self.parent.cost_tracker.estimate_cost(
                    kwargs['model'],
                    TokenUsage(
                        input_tokens=estimated_input_tokens,
                        output_tokens=estimated_output_tokens,
                        total_tokens=estimated_input_tokens + estimated_output_tokens
                    ),
                    'openai'
                )
                
                if self.parent.budget_manager:
                    budget_check = await self.parent.budget_manager.check_budget(
                        agent_id, estimate.estimated_cost
                    )
                    security.budget_check = budget_check.dict()
                    
                    if not budget_check.allowed:
                        raise ValueError(
                            f"Budget exceeded: {budget_check.blocked_by.name} "
                            f"(Limit: {budget_check.blocked_by.limit})"
                        )
            
            # 5. Make actual API call
            response = await self.parent.client.chat.completions.create(**kwargs)
            
            # 6. Run output guardrails
            if self.parent.config.enable_guardrails and self.parent.guardrail_engine:
                assistant_message = response.choices[0].message.content
                output_result = await self.parent.guardrail_engine.execute(assistant_message)
                
                if not output_result.passed:
                    failed = ', '.join(output_result.get_failed_guardrails())
                    raise ValueError(
                        f"Output guardrail check failed: {failed} "
                        f"(Risk: {output_result.max_risk_score})"
                    )
            
            # 7. Track actual cost
            if self.parent.config.enable_cost_tracking and self.parent.cost_tracker:
                cost_record = self.parent.cost_tracker.calculate_actual_cost(
                    request_id,
                    agent_id,
                    kwargs['model'],
                    TokenUsage(
                        input_tokens=response.usage.prompt_tokens,
                        output_tokens=response.usage.completion_tokens,
                        total_tokens=response.usage.total_tokens
                    ),
                    'openai'
                )
                security.cost_record = cost_record
                
                if self.parent.cost_storage:
                    await self.parent.cost_storage.store(cost_record)
                
                if self.parent.budget_manager:
                    await self.parent.budget_manager.record_cost(cost_record)
            
            # 8. Log completion event
            if self.parent.audit:
                from ..core.audit.types import AuditEventType
                self.parent.audit.log_event(
                    event_type=AuditEventType.LLM_RESPONSE,
                    context=context,
                    metadata={
                        'model': kwargs.get('model'),
                        'provider': 'openai',
                        'request_id': request_id,
                        'usage': {
                            'prompt_tokens': response.usage.prompt_tokens,
                            'completion_tokens': response.usage.completion_tokens,
                            'total_tokens': response.usage.total_tokens
                        }
                    }
                )
            
            # 9. Return response with security metadata
            return ChatCompletionResponse(
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
            # Log error event
            if self.parent.audit:
                from ..core.audit.types import AuditEventType
                self.parent.audit.log_event(
                    event_type=AuditEventType.LLM_REQUEST,
                    context=context,
                    metadata={
                        'error': str(e),
                        'model': kwargs.get('model'),
                        'provider': 'openai'
                    }
                )
            
            if isinstance(e, ValueError):
                raise
            raise ValueError(f"TealOpenAI error: {str(e)}")


class TealOpenAI:
    """
    TealOpenAI client - drop-in replacement for OpenAI with security.
    
    Provides integrated guardrails, cost tracking, and budget management
    for OpenAI API calls.
    
    Example:
        ```python
        from tealtiger import TealOpenAI, TealOpenAIConfig
        from tealtiger.guardrails import GuardrailEngine
        from tealtiger.cost import CostTracker, BudgetManager, InMemoryCostStorage
        
        # Create components
        engine = GuardrailEngine()
        tracker = CostTracker()
        storage = InMemoryCostStorage()
        budget_manager = BudgetManager(storage)
        
        # Create guarded client
        client = TealOpenAI(TealOpenAIConfig(
            api_key="your-api-key",
            agent_id="my-agent",
            guardrail_engine=engine,
            cost_tracker=tracker,
            budget_manager=budget_manager,
            cost_storage=storage
        ))
        
        # Use like normal OpenAI client
        response = await client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello!"}]
        )
        ```
    """
    
    def __init__(self, config: TealOpenAIConfig):
        """
        Initialize TealOpenAI client.
        
        Args:
            config: Configuration for the guarded client
        """
        self.config = config
        self.client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            organization=config.organization
        )
        self.guardrail_engine = config.guardrail_engine
        self.cost_tracker = config.cost_tracker
        self.budget_manager = config.budget_manager
        self.cost_storage = config.cost_storage
        # Enterprise components
        self.engine = config.engine
        self.guard = config.guard
        self.audit = config.audit
    
    @property
    def chat(self) -> ChatCompletions:
        """Access chat completions API."""
        return ChatCompletions(self)

