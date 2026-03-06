"""
TealGemini Streaming Example

This example demonstrates streaming responses with TealGemini client.
"""

import asyncio
import os
from tealtiger import TealGemini, TealGeminiConfig
from tealtiger.guardrails import GuardrailEngine
from tealtiger.cost import CostTracker, BudgetManager, InMemoryCostStorage


async def main():
    """Run streaming TealGemini example."""
    
    # Get API key from environment
    api_key = os.getenv('GOOGLE_API_KEY')
    if not api_key:
        print("Error: GOOGLE_API_KEY environment variable not set")
        return
    
    # Create security components
    engine = GuardrailEngine()
    tracker = CostTracker()
    storage = InMemoryCostStorage()
    budget_manager = BudgetManager(storage)
    
    # Configure TealGemini client
    client = TealGemini(TealGeminiConfig(
        api_key=api_key,
        model='gemini-pro',
        agent_id='streaming-agent',
        enable_guardrails=True,
        enable_cost_tracking=True,
        guardrail_engine=engine,
        cost_tracker=tracker,
        budget_manager=budget_manager,
        cost_storage=storage
    ))
    
    print("TealGemini Streaming Example")
    print("=" * 50)
    
    # Example 1: Basic streaming
    print("\n1. Basic Streaming Response:")
    print("-" * 50)
    print("Prompt: Write a short story about AI")
    print("\nStreaming response:")
    print("-" * 50)
    
    response = await client.generate_content(
        "Write a short story about AI in 3 paragraphs",
        stream=True
    )
    
    print(f"\n{response.text}")
    
    print(f"\nUsage:")
    print(f"  - Prompt tokens: {response.usage['prompt_tokens']}")
    print(f"  - Completion tokens: {response.usage['completion_tokens']}")
    print(f"  - Total tokens: {response.usage['total_tokens']}")
    
    if response.security and response.security.cost_record:
        print(f"  - Cost: ${response.security.cost_record.cost:.6f}")
    
    # Example 2: Streaming with generation config
    print("\n2. Streaming with Custom Config:")
    print("-" * 50)
    print("Prompt: Explain quantum computing")
    print("\nStreaming response with temperature=0.9:")
    print("-" * 50)
    
    response = await client.generate_content(
        "Explain quantum computing in simple terms",
        stream=True,
        generation_config={
            "temperature": 0.9,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 200
        }
    )
    
    print(f"\n{response.text}")
    
    # Example 3: Streaming considerations
    print("\n3. Streaming Considerations:")
    print("-" * 50)
    
    print("""
    When using streaming with TealGemini:
    
    ✅ Supported:
    - Real-time token generation
    - Cost tracking (calculated after stream completes)
    - Budget enforcement (checked before streaming starts)
    - Input guardrails (run before streaming)
    - Generation config (temperature, top_p, etc.)
    
    ⚠️  Limitations:
    - Output guardrails run after full response (not per-chunk)
    - Cannot interrupt mid-stream based on content
    - Full response buffered for guardrail checking
    
    💡 Best Practices:
    - Use streaming for long-form content generation
    - Set max_output_tokens to control response length
    - Monitor costs with budget limits
    - Consider non-streaming for strict content filtering
    """)
    
    # Example 4: Comparing streaming vs non-streaming
    print("\n4. When to Use Streaming:")
    print("-" * 50)
    
    print("""
    Use Streaming When:
    - Generating long-form content (articles, stories, code)
    - User experience benefits from progressive display
    - Response time perception is important
    - Content length is variable
    
    Use Non-Streaming When:
    - Need strict real-time content filtering
    - Response is typically short
    - Need to process complete response before display
    - Implementing approval workflows
    """)
    
    print("\n" + "=" * 50)
    print("Streaming example completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
