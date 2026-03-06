"""
TealMistral Example - Basic Chat

This example demonstrates using TealMistral for basic chat interactions
with integrated security and cost tracking. Mistral AI provides European
data residency (Paris, France).
"""

import asyncio
from tealtiger import TealMistral, TealMistralConfig
from tealtiger.guardrails import GuardrailEngine
from tealtiger.cost import CostTracker, BudgetManager, InMemoryCostStorage


async def main():
    # Create security components
    engine = GuardrailEngine()
    tracker = CostTracker()
    storage = InMemoryCostStorage()
    budget_manager = BudgetManager(storage)
    
    # Set a budget (optional)
    await budget_manager.set_budget(
        agent_id="mistral-agent",
        limit=5.0,  # $5 budget
        window="daily"
    )
    
    # Create guarded Mistral client
    client = TealMistral(TealMistralConfig(
        api_key="your-mistral-api-key",
        model="mistral-small",
        agent_id="mistral-agent",
        guardrail_engine=engine,
        cost_tracker=tracker,
        budget_manager=budget_manager,
        cost_storage=storage
    ))
    
    print("TealMistral Example - Basic Chat")
    print("=" * 50)
    print("Note: Mistral AI provides European data residency (Paris, France)")
    print()
    
    # Example 1: Simple question
    print("1. Simple Question:")
    response = await client.chat(
        messages=[
            {"role": "user", "content": "What is artificial intelligence?"}
        ],
        temperature=0.7,
        max_tokens=200
    )
    
    print(f"Response: {response.text}")
    print(f"Model: {response.model}")
    print(f"Usage: {response.usage}")
    
    if response.security and response.security.cost_record:
        print(f"Cost: ${response.security.cost_record.cost:.6f}")
    
    # Example 2: Conversation with history
    print("\n2. Conversation with History:")
    response = await client.chat(
        messages=[
            {"role": "user", "content": "What is machine learning?"},
            {"role": "assistant", "content": "Machine learning is a subset of AI that enables systems to learn from data."},
            {"role": "user", "content": "Can you give me an example?"}
        ],
        temperature=0.7,
        max_tokens=200
    )
    
    print(f"Response: {response.text}")
    
    if response.security and response.security.cost_record:
        print(f"Cost: ${response.security.cost_record.cost:.6f}")
    
    # Example 3: Creative writing with higher temperature
    print("\n3. Creative Writing:")
    response = await client.chat(
        messages=[
            {"role": "user", "content": "Write a short tagline for an AI security product."}
        ],
        temperature=0.9,
        max_tokens=50
    )
    
    print(f"Response: {response.text}")
    
    if response.security and response.security.cost_record:
        print(f"Cost: ${response.security.cost_record.cost:.6f}")
    
    # Example 4: Safe mode (content filtering)
    print("\n4. Safe Mode (Content Filtering):")
    response = await client.chat(
        messages=[
            {"role": "user", "content": "Tell me about cybersecurity best practices."}
        ],
        temperature=0.7,
        max_tokens=200,
        safe_mode=True
    )
    
    print(f"Response: {response.text[:150]}...")
    
    if response.security and response.security.cost_record:
        print(f"Cost: ${response.security.cost_record.cost:.6f}")
    
    # Example 5: Check total costs
    print("\n5. Total Costs:")
    total_cost = await storage.get_total_cost("mistral-agent")
    print(f"Total spent: ${total_cost:.6f}")
    
    # Example 6: Check budget status
    print("\n6. Budget Status:")
    budget_status = await budget_manager.get_budget_status("mistral-agent")
    if budget_status:
        print(f"Budget limit: ${budget_status.limit}")
        print(f"Current usage: ${budget_status.current_usage:.6f}")
        print(f"Remaining: ${budget_status.remaining:.6f}")
        print(f"Usage: {budget_status.usage_percentage:.1f}%")


if __name__ == "__main__":
    asyncio.run(main())
