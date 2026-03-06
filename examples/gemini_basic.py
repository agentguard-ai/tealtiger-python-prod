"""
TealGemini Basic Example

This example demonstrates basic usage of TealGemini client with
integrated security guardrails and cost tracking.
"""

import asyncio
import os
from tealtiger import TealGemini, TealGeminiConfig
from tealtiger.guardrails import GuardrailEngine
from tealtiger.cost import CostTracker, BudgetManager, InMemoryCostStorage


async def main():
    """Run basic TealGemini example."""
    
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
        agent_id='example-agent',
        enable_guardrails=True,
        enable_cost_tracking=True,
        guardrail_engine=engine,
        cost_tracker=tracker,
        budget_manager=budget_manager,
        cost_storage=storage
    ))
    
    print("TealGemini Basic Example")
    print("=" * 50)
    
    # Example 1: Simple text generation
    print("\n1. Simple Text Generation:")
    print("-" * 50)
    
    response = await client.generate_content(
        "Explain quantum computing in simple terms"
    )
    
    print(f"Response: {response.text[:200]}...")
    print(f"\nUsage:")
    print(f"  - Prompt tokens: {response.usage['prompt_tokens']}")
    print(f"  - Completion tokens: {response.usage['completion_tokens']}")
    print(f"  - Total tokens: {response.usage['total_tokens']}")
    
    if response.security and response.security.cost_record:
        print(f"  - Cost: ${response.security.cost_record.cost:.6f}")
    
    # Example 2: Structured content
    print("\n2. Structured Content:")
    print("-" * 50)
    
    response = await client.generate_content(
        contents=[
            {
                "role": "user",
                "parts": [
                    {"text": "What are the three laws of robotics?"}
                ]
            }
        ]
    )
    
    print(f"Response: {response.text}")
    
    # Example 3: With generation config
    print("\n3. With Generation Config:")
    print("-" * 50)
    
    response = await client.generate_content(
        "Write a haiku about AI",
        generation_config={
            "temperature": 0.9,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 100
        }
    )
    
    print(f"Response: {response.text}")
    
    print("\n" + "=" * 50)
    print("Example completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
