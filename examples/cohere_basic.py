"""
TealCohere Example - Basic Chat

This example demonstrates using TealCohere for basic chat interactions
with integrated security and cost tracking.
"""

import asyncio
from tealtiger import TealCohere, TealCohereConfig
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
        agent_id="cohere-agent",
        limit=5.0,  # $5 budget
        window="daily"
    )
    
    # Create guarded Cohere client
    client = TealCohere(TealCohereConfig(
        api_key="your-cohere-api-key",
        model="command",
        agent_id="cohere-agent",
        guardrail_engine=engine,
        cost_tracker=tracker,
        budget_manager=budget_manager,
        cost_storage=storage
    ))
    
    print("TealCohere Example - Basic Chat")
    print("=" * 50)
    
    # Example 1: Simple question
    print("\n1. Simple Question:")
    response = await client.chat(
        message="What is artificial intelligence?",
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
    chat_history = [
        {"role": "USER", "message": "What is machine learning?"},
        {"role": "CHATBOT", "message": "Machine learning is a subset of AI that enables systems to learn from data."}
    ]
    
    response = await client.chat(
        message="Can you give me an example?",
        chat_history=chat_history,
        temperature=0.7,
        max_tokens=200
    )
    
    print(f"Response: {response.text}")
    
    if response.security and response.security.cost_record:
        print(f"Cost: ${response.security.cost_record.cost:.6f}")
    
    # Example 3: Creative writing with higher temperature
    print("\n3. Creative Writing:")
    response = await client.chat(
        message="Write a short tagline for an AI security product.",
        temperature=0.9,
        max_tokens=50
    )
    
    print(f"Response: {response.text}")
    
    if response.security and response.security.cost_record:
        print(f"Cost: ${response.security.cost_record.cost:.6f}")
    
    # Example 4: Check total costs
    print("\n4. Total Costs:")
    total_cost = await storage.get_total_cost("cohere-agent")
    print(f"Total spent: ${total_cost:.6f}")
    
    # Example 5: Check budget status
    print("\n5. Budget Status:")
    budget_status = await budget_manager.get_budget_status("cohere-agent")
    if budget_status:
        print(f"Budget limit: ${budget_status.limit}")
        print(f"Current usage: ${budget_status.current_usage:.6f}")
        print(f"Remaining: ${budget_status.remaining:.6f}")
        print(f"Usage: {budget_status.usage_percentage:.1f}%")


if __name__ == "__main__":
    asyncio.run(main())
