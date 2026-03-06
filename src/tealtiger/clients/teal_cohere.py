"""
TealCohere Client

Drop-in replacement for Cohere client with integrated security and cost tracking.
Supports chat, RAG (Retrieval-Augmented Generation), and embeddings.
"""

from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field
import cohere

from ..guardrails.engine import GuardrailEngine, GuardrailEngineResult
from ..cost.tracker import CostTracker
from ..cost.budget import BudgetManager
from ..cost.storage import CostStorage
from ..cost.types import TokenUsage, CostRecord
from ..cost.utils import generate_id


class TealCohereConfig(BaseModel):
    """Configuration for TealCohere client."""
    
    api_key: str = Field(..., description="Cohere API key")
    model: str = Field(default='command', description="Model name (command, command-light)")
    agent_id: Optional[str] = Field(default='default-agent', description="Agent ID for tracking")
    enable_guardrails: bool = Field(default=True, description="Enable guardrails")
    enable_cost_tracking: bool = Field(default=True, description="Enable cost tracking")
    guardrail_engine: Optional[GuardrailEngine] = Field(default=None, description="Guardrail engine instance")
    cost_tracker: Optional[CostTracker] = Field(default=None, description="Cost tracker instance")
    budget_manager: Optional[BudgetManager] = Field(default=None, description="Budget manager instance")
    cost_storage: Optional[CostStorage] = Field(default=None, description="Cost storage instance")
    
    class Config:
        arbitrary_types_allowed = True


class SecurityMetadata(BaseModel):
    """Security metadata for Cohere response."""
    
    guardrail_result: Optional[GuardrailEngineResult] = None
    cost_record: Optional[CostRecord] = None
    budget_check: Optional[Dict[str, Any]] = None
    
    class Config:
        arbitrary_types_allowed = True


class ChatResponse(BaseModel):
    """Cohere chat response."""
    
    text: str
    generation_id: Optional[str] = None
    citations: Optional[List[Dict[str, Any]]] = None
    documents: Optional[List[Dict[str, Any]]] = None
    search_queries: Optional[List[Dict[str, Any]]] = None
    search_results: Optional[List[Dict[str, Any]]] = None
    usage: Dict[str, int]
    model: str
    security: Optional[SecurityMetadata] = None


class EmbedResponse(BaseModel):
    """Cohere embed response."""
    
    embeddings: List[List[float]]
    usage: Dict[str, int]
    model: str
    security: Optional[SecurityMetadata] = None


class TealCohere:
    """
    TealCohere client - drop-in replacement for Cohere with security.
    
    Provides integrated guardrails, cost tracking, and budget management
    for Cohere API calls including chat, RAG, and embeddings.
    
    Key Features:
    - Chat with conversation history
    - RAG (Retrieval-Augmented Generation) with documents
    - Web search connectors
    - Citation tracking
    - Embeddings generation
    
    Example:
        ```python
        from tealtiger import TealCohere, TealCohereConfig
        from tealtiger.guardrails import GuardrailEngine
        from tealtiger.cost import CostTracker, BudgetManager, InMemoryCostStorage
        
        # Create components
        engine = GuardrailEngine()
        tracker = CostTracker()
        storage = InMemoryCostStorage()
        budget_manager = BudgetManager(storage)
        
        # Create guarded client
        client = TealCohere(TealCohereConfig(
            api_key="your-api-key",
            model="command",
            agent_id="my-agent",
            guardrail_engine=engine,
            cost_tracker=tracker,
            budget_manager=budget_manager,
            cost_storage=storage
        ))
        
        # Use like normal Cohere client
        response = await client.chat(
            message="What is machine learning?",
            temperature=0.7
        )
        ```
    """
    
    def __init__(self, config: TealCohereConfig):
        """
        Initialize TealCohere client.
        
        Args:
            config: Configuration for the guarded client
        """
        self.config = config
        
        # Create Cohere client
        self.client = cohere.Client(api_key=config.api_key)
        
        self.guardrail_engine = config.guardrail_engine
        self.cost_tracker = config.cost_tracker
        self.budget_manager = config.budget_manager
        self.cost_storage = config.cost_storage
    
    async def chat(
        self,
        message: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
        documents: Optional[List[Dict[str, str]]] = None,
        connectors: Optional[List[Dict[str, str]]] = None,
        **kwargs
    ) -> ChatResponse:
        """
        Chat with Cohere with security and cost tracking.
        
        Supports conversation history, RAG with documents, and web search connectors.
        
        Args:
            message: User message
            chat_history: Optional conversation history
                         Format: [{"role": "USER", "message": "..."}, {"role": "CHATBOT", "message": "..."}]
            documents: Optional documents for RAG
                      Format: [{"title": "...", "snippet": "..."}, ...]
            connectors: Optional connectors for web search
                       Format: [{"id": "web-search"}]
            **kwargs: Additional parameters
                - temperature: Sampling temperature (0.0-5.0)
                - max_tokens: Maximum tokens to generate
                - k: Top-k sampling
                - p: Nucleus sampling (top-p)
                - frequency_penalty: Frequency penalty (0.0-1.0)
                - presence_penalty: Presence penalty (0.0-1.0)
                - stream: Boolean for streaming responses
            
        Returns:
            ChatResponse with security metadata
            
        Raises:
            ValueError: If guardrails fail or budget is exceeded
        """
        request_id = generate_id()
        agent_id = self.config.agent_id
        security = SecurityMetadata()
        
        try:
            # 1. Run input guardrails
            if self.config.enable_guardrails and self.guardrail_engine:
                guardrail_result = await self.guardrail_engine.execute(message)
                security.guardrail_result = guardrail_result
                
                if not guardrail_result.passed:
                    failed = ', '.join(guardrail_result.get_failed_guardrails())
                    raise ValueError(
                        f"Guardrail check failed: {failed} "
                        f"(Risk: {guardrail_result.max_risk_score})"
                    )
            
            # 2. Estimate cost and check budget
            if self.config.enable_cost_tracking and self.cost_tracker:
                estimated_input_tokens = len(message) // 4
                estimated_output_tokens = kwargs.get('max_tokens', 500)
                
                estimate = self.cost_tracker.estimate_cost(
                    self.config.model,
                    TokenUsage(
                        input_tokens=estimated_input_tokens,
                        output_tokens=estimated_output_tokens,
                        total_tokens=estimated_input_tokens + estimated_output_tokens
                    ),
                    'cohere'
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
            
            # 3. Prepare request parameters
            request_params = {
                'message': message,
                'model': self.config.model,
            }
            
            if chat_history:
                request_params['chat_history'] = chat_history
            if documents:
                request_params['documents'] = documents
            if connectors:
                request_params['connectors'] = connectors
            
            # Add optional parameters
            if 'temperature' in kwargs:
                request_params['temperature'] = kwargs['temperature']
            if 'max_tokens' in kwargs:
                request_params['max_tokens'] = kwargs['max_tokens']
            if 'k' in kwargs:
                request_params['k'] = kwargs['k']
            if 'p' in kwargs:
                request_params['p'] = kwargs['p']
            if 'frequency_penalty' in kwargs:
                request_params['frequency_penalty'] = kwargs['frequency_penalty']
            if 'presence_penalty' in kwargs:
                request_params['presence_penalty'] = kwargs['presence_penalty']
            
            # 4. Make actual API call
            response = self.client.chat(**request_params)
            
            # Extract response text
            text = response.text
            
            # 5. Run output guardrails
            if self.config.enable_guardrails and self.guardrail_engine:
                output_result = await self.guardrail_engine.execute(text)
                
                if not output_result.passed:
                    failed = ', '.join(output_result.get_failed_guardrails())
                    raise ValueError(
                        f"Output guardrail check failed: {failed} "
                        f"(Risk: {output_result.max_risk_score})"
                    )
            
            # 6. Track actual cost
            usage = {
                'input_tokens': getattr(response.meta, 'billed_units', {}).get('input_tokens', 0) if hasattr(response, 'meta') else 0,
                'output_tokens': getattr(response.meta, 'billed_units', {}).get('output_tokens', 0) if hasattr(response, 'meta') else 0,
                'total_tokens': 0
            }
            usage['total_tokens'] = usage['input_tokens'] + usage['output_tokens']
            
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
                    'cohere'
                )
                security.cost_record = cost_record
                
                if self.cost_storage:
                    await self.cost_storage.store(cost_record)
                
                if self.budget_manager:
                    await self.budget_manager.record_cost(cost_record)
            
            # 7. Return response with security metadata
            return ChatResponse(
                text=text,
                generation_id=response.generation_id if hasattr(response, 'generation_id') else None,
                citations=response.citations if hasattr(response, 'citations') and response.citations else None,
                documents=response.documents if hasattr(response, 'documents') and response.documents else None,
                search_queries=response.search_queries if hasattr(response, 'search_queries') and response.search_queries else None,
                search_results=response.search_results if hasattr(response, 'search_results') and response.search_results else None,
                usage=usage,
                model=self.config.model,
                security=security
            )
        
        except Exception as e:
            if isinstance(e, ValueError):
                raise
            raise ValueError(f"TealCohere error: {str(e)}")
    
    async def embed(
        self,
        texts: List[str],
        input_type: str = "search_document",
        **kwargs
    ) -> EmbedResponse:
        """
        Generate embeddings with security and cost tracking.
        
        Args:
            texts: List of texts to embed
            input_type: Type of input ("search_document", "search_query", "classification", "clustering")
            **kwargs: Additional parameters
                - truncate: Truncation strategy ("NONE", "START", "END")
            
        Returns:
            EmbedResponse with security metadata
            
        Raises:
            ValueError: If guardrails fail or budget is exceeded
        """
        request_id = generate_id()
        agent_id = self.config.agent_id
        security = SecurityMetadata()
        
        try:
            # 1. Run input guardrails on all texts
            if self.config.enable_guardrails and self.guardrail_engine:
                for text in texts:
                    guardrail_result = await self.guardrail_engine.execute(text)
                    security.guardrail_result = guardrail_result
                    
                    if not guardrail_result.passed:
                        failed = ', '.join(guardrail_result.get_failed_guardrails())
                        raise ValueError(
                            f"Guardrail check failed: {failed} "
                            f"(Risk: {guardrail_result.max_risk_score})"
                        )
            
            # 2. Estimate cost and check budget
            if self.config.enable_cost_tracking and self.cost_tracker:
                total_chars = sum(len(text) for text in texts)
                estimated_tokens = total_chars // 4
                
                estimate = self.cost_tracker.estimate_cost(
                    'embed',  # Cohere embed model
                    TokenUsage(
                        input_tokens=estimated_tokens,
                        output_tokens=0,
                        total_tokens=estimated_tokens
                    ),
                    'cohere'
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
            request_params = {
                'texts': texts,
                'input_type': input_type,
                'model': 'embed-english-v3.0'  # Default embed model
            }
            
            if 'truncate' in kwargs:
                request_params['truncate'] = kwargs['truncate']
            
            response = self.client.embed(**request_params)
            
            # 4. Track actual cost
            usage = {
                'input_tokens': getattr(response.meta, 'billed_units', {}).get('input_tokens', 0) if hasattr(response, 'meta') else 0,
                'output_tokens': 0,
                'total_tokens': 0
            }
            usage['total_tokens'] = usage['input_tokens']
            
            if self.config.enable_cost_tracking and self.cost_tracker:
                cost_record = self.cost_tracker.calculate_actual_cost(
                    request_id,
                    agent_id,
                    'embed',
                    TokenUsage(
                        input_tokens=usage['input_tokens'],
                        output_tokens=0,
                        total_tokens=usage['total_tokens']
                    ),
                    'cohere'
                )
                security.cost_record = cost_record
                
                if self.cost_storage:
                    await self.cost_storage.store(cost_record)
                
                if self.budget_manager:
                    await self.budget_manager.record_cost(cost_record)
            
            # 5. Return response with security metadata
            return EmbedResponse(
                embeddings=response.embeddings,
                usage=usage,
                model='embed-english-v3.0',
                security=security
            )
        
        except Exception as e:
            if isinstance(e, ValueError):
                raise
            raise ValueError(f"TealCohere embed error: {str(e)}")
