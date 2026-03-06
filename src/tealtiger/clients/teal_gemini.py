"""
TealGemini Client

Drop-in replacement for Google Gemini client with integrated security and cost tracking.
"""

from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field
import google.generativeai as genai

from ..guardrails.engine import GuardrailEngine, GuardrailEngineResult
from ..cost.tracker import CostTracker
from ..cost.budget import BudgetManager
from ..cost.storage import CostStorage
from ..cost.types import TokenUsage, CostRecord
from ..cost.utils import generate_id


# Type alias for content
ContentType = Union[str, List[Dict[str, Any]]]


class TealGeminiConfig(BaseModel):
    """Configuration for TealGemini client."""
    
    api_key: str = Field(..., description="Google API key")
    model: str = Field(default='gemini-pro', description="Model name")
    agent_id: Optional[str] = Field(default='default-agent', description="Agent ID for tracking")
    enable_guardrails: bool = Field(default=True, description="Enable guardrails")
    enable_cost_tracking: bool = Field(default=True, description="Enable cost tracking")
    guardrail_engine: Optional[GuardrailEngine] = Field(default=None, description="Guardrail engine instance")
    cost_tracker: Optional[CostTracker] = Field(default=None, description="Cost tracker instance")
    budget_manager: Optional[BudgetManager] = Field(default=None, description="Budget manager instance")
    cost_storage: Optional[CostStorage] = Field(default=None, description="Cost storage instance")
    safety_settings: Optional[List[Dict[str, Any]]] = Field(default=None, description="Safety settings")
    generation_config: Optional[Dict[str, Any]] = Field(default=None, description="Generation config")
    
    class Config:
        arbitrary_types_allowed = True


class GenerateContentRequest(BaseModel):
    """Generate content request parameters."""
    
    contents: List[Dict[str, Any]]
    generation_config: Optional[Dict[str, Any]] = None
    safety_settings: Optional[List[Dict[str, Any]]] = None
    stream: Optional[bool] = None


class SecurityMetadata(BaseModel):
    """Security metadata for generate content response."""
    
    guardrail_result: Optional[GuardrailEngineResult] = None
    cost_record: Optional[CostRecord] = None
    budget_check: Optional[Dict[str, Any]] = None
    
    class Config:
        arbitrary_types_allowed = True


class GenerateContentResponse(BaseModel):
    """Generate content response."""
    
    text: str
    candidates: List[Dict[str, Any]]
    prompt_feedback: Optional[Dict[str, Any]] = None
    usage: Dict[str, int]
    model: str
    security: Optional[SecurityMetadata] = None


class TealGemini:
    """
    TealGemini client - drop-in replacement for Google Gemini with security.
    
    Provides integrated guardrails, cost tracking, and budget management
    for Google Gemini API calls.
    
    Example:
        ```python
        from tealtiger import TealGemini, TealGeminiConfig
        from tealtiger.guardrails import GuardrailEngine
        from tealtiger.cost import CostTracker, BudgetManager, InMemoryCostStorage
        
        # Create components
        engine = GuardrailEngine()
        tracker = CostTracker()
        storage = InMemoryCostStorage()
        budget_manager = BudgetManager(storage)
        
        # Create guarded client
        client = TealGemini(TealGeminiConfig(
            api_key="your-api-key",
            model="gemini-pro",
            agent_id="my-agent",
            guardrail_engine=engine,
            cost_tracker=tracker,
            budget_manager=budget_manager,
            cost_storage=storage
        ))
        
        # Use like normal Gemini client
        response = await client.generate_content(
            contents=[{"role": "user", "parts": [{"text": "Hello!"}]}]
        )
        ```
    """
    
    def __init__(self, config: TealGeminiConfig):
        """
        Initialize TealGemini client.
        
        Args:
            config: Configuration for the guarded client
        """
        self.config = config
        
        # Configure Gemini API
        genai.configure(api_key=config.api_key)
        
        # Create model instance
        self.model = genai.GenerativeModel(
            model_name=config.model,
            safety_settings=config.safety_settings,
            generation_config=config.generation_config
        )
        
        self.guardrail_engine = config.guardrail_engine
        self.cost_tracker = config.cost_tracker
        self.budget_manager = config.budget_manager
        self.cost_storage = config.cost_storage
    
    async def generate_content(
        self,
        contents: Union[str, List[Dict[str, Any]]],
        **kwargs
    ) -> GenerateContentResponse:
        """
        Generate content with security and cost tracking.
        
        Supports multimodal inputs (text + images), streaming, safety settings,
        and generation configuration.
        
        Args:
            contents: Content to generate from (string or structured content)
                     For multimodal: [{"role": "user", "parts": [{"text": "..."}, {"inline_data": {...}}]}]
            **kwargs: Additional generation parameters
                - generation_config: Dict with temperature, top_p, top_k, max_output_tokens
                - safety_settings: List of safety setting dicts
                - stream: Boolean for streaming responses
            
        Returns:
            GenerateContentResponse with security metadata
            
        Raises:
            ValueError: If guardrails fail or budget is exceeded
        """
        request_id = generate_id()
        agent_id = self.config.agent_id
        security = SecurityMetadata()
        
        try:
            # Normalize contents to list format
            if isinstance(contents, str):
                contents = [{"role": "user", "parts": [{"text": contents}]}]
            
            # Check if this is a multimodal request
            is_multimodal = self._is_multimodal_content(contents)
            
            # 1. Run input guardrails (text only)
            if self.config.enable_guardrails and self.guardrail_engine:
                user_text = self._extract_text_content(contents)
                if user_text:  # Only run if there's text content
                    guardrail_result = await self.guardrail_engine.execute(user_text)
                    security.guardrail_result = guardrail_result
                    
                    if not guardrail_result.passed:
                        failed = ', '.join(guardrail_result.get_failed_guardrails())
                        raise ValueError(
                            f"Guardrail check failed: {failed} "
                            f"(Risk: {guardrail_result.max_risk_score})"
                        )
            
            # 2. Estimate cost and check budget
            if self.config.enable_cost_tracking and self.cost_tracker:
                input_text = self._extract_text_content(contents)
                estimated_input_tokens = len(input_text) // 4 if input_text else 100
                
                # Get max_output_tokens from generation_config or kwargs
                gen_config = kwargs.get('generation_config', {})
                estimated_output_tokens = gen_config.get('max_output_tokens', 
                                                        kwargs.get('max_output_tokens', 500))
                
                estimate = self.cost_tracker.estimate_cost(
                    self.config.model,
                    TokenUsage(
                        input_tokens=estimated_input_tokens,
                        output_tokens=estimated_output_tokens,
                        total_tokens=estimated_input_tokens + estimated_output_tokens
                    ),
                    'gemini'
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
            
            # 3. Prepare generation config with safety settings
            generation_config = kwargs.get('generation_config', self.config.generation_config)
            safety_settings = kwargs.get('safety_settings', self.config.safety_settings)
            stream = kwargs.get('stream', False)
            
            # 4. Make actual API call
            if stream:
                # Streaming not fully supported with guardrails yet
                response = await self.model.generate_content_async(
                    contents,
                    generation_config=generation_config,
                    safety_settings=safety_settings,
                    stream=True
                )
                # For streaming, we need to consume the stream
                full_text = ""
                async for chunk in response:
                    full_text += chunk.text
                # Create a mock response object for consistency
                response.text = full_text
            else:
                response = await self.model.generate_content_async(
                    contents,
                    generation_config=generation_config,
                    safety_settings=safety_settings,
                    stream=False
                )
            
            # 5. Run output guardrails
            if self.config.enable_guardrails and self.guardrail_engine and not stream:
                assistant_text = response.text
                output_result = await self.guardrail_engine.execute(assistant_text)
                
                if not output_result.passed:
                    failed = ', '.join(output_result.get_failed_guardrails())
                    raise ValueError(
                        f"Output guardrail check failed: {failed} "
                        f"(Risk: {output_result.max_risk_score})"
                    )
            
            # 6. Track actual cost
            if self.config.enable_cost_tracking and self.cost_tracker:
                usage_metadata = response.usage_metadata
                cost_record = self.cost_tracker.calculate_actual_cost(
                    request_id,
                    agent_id,
                    self.config.model,
                    TokenUsage(
                        input_tokens=usage_metadata.prompt_token_count,
                        output_tokens=usage_metadata.candidates_token_count,
                        total_tokens=usage_metadata.total_token_count
                    ),
                    'gemini'
                )
                security.cost_record = cost_record
                
                if self.cost_storage:
                    await self.cost_storage.store(cost_record)
                
                if self.budget_manager:
                    await self.budget_manager.record_cost(cost_record)
            
            # 7. Return response with security metadata
            return GenerateContentResponse(
                text=response.text,
                candidates=[
                    {
                        'content': {
                            'parts': [
                                {'text': part.text} if hasattr(part, 'text') else {}
                                for part in candidate.content.parts
                            ],
                            'role': candidate.content.role
                        },
                        'finish_reason': candidate.finish_reason,
                        'safety_ratings': [
                            {
                                'category': rating.category,
                                'probability': rating.probability
                            }
                            for rating in candidate.safety_ratings
                        ] if hasattr(candidate, 'safety_ratings') else []
                    }
                    for candidate in response.candidates
                ],
                prompt_feedback={
                    'safety_ratings': [
                        {
                            'category': rating.category,
                            'probability': rating.probability
                        }
                        for rating in response.prompt_feedback.safety_ratings
                    ]
                } if hasattr(response, 'prompt_feedback') and response.prompt_feedback else None,
                usage={
                    'prompt_tokens': response.usage_metadata.prompt_token_count,
                    'completion_tokens': response.usage_metadata.candidates_token_count,
                    'total_tokens': response.usage_metadata.total_token_count
                },
                model=self.config.model,
                security=security
            )
        
        except Exception as e:
            if isinstance(e, ValueError):
                raise
            raise ValueError(f"TealGemini error: {str(e)}")
    
    def _extract_text_content(self, contents: List[Dict[str, Any]]) -> str:
        """
        Extract text content from structured content.
        
        Args:
            contents: Structured content list
            
        Returns:
            Extracted text content
        """
        text_parts = []
        
        for content in contents:
            if isinstance(content, dict):
                parts = content.get('parts', [])
                for part in parts:
                    if isinstance(part, dict) and 'text' in part:
                        text_parts.append(part['text'])
                    elif isinstance(part, str):
                        text_parts.append(part)
        
        return '\n'.join(text_parts)
    
    def _is_multimodal_content(self, contents: List[Dict[str, Any]]) -> bool:
        """
        Check if content includes multimodal data (images, etc.).
        
        Args:
            contents: Structured content list
            
        Returns:
            True if multimodal content is present
        """
        for content in contents:
            if isinstance(content, dict):
                parts = content.get('parts', [])
                for part in parts:
                    if isinstance(part, dict):
                        # Check for inline_data (images) or other non-text content
                        if 'inline_data' in part or 'file_data' in part:
                            return True
        return False
