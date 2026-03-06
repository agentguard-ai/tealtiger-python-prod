"""
TealMistral Example - Streaming Responses

This example demonstrates using TealMistral with streaming responses
for real-time output generation.
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
        agent_id="mistral-stream-agent",
        limit=5.0,  # $5 budget
        window="daily"
    )
    
    # Create guarded Mistral client
    client = TealMistral(TealMistralConfig(
        api_key="your-mistral-api-key",
        model="mistral-small",
        agent_id="mistral-stream-agent",
        guardrail_engine=engine,
        cost_tracker=tracker,
        budget_manager=budget_manager,
        cost_storage=storage
    ))
    
    print("TealMistral Example - Streaming Responses")
    print("=" * 50)
    
    # Example 1: Basic streaming
    print("\n1. Basic Streaming:")
    print("Question: Explain quantum computing in simple terms.")
    print("\nStreaming response:")
    print("-" * 50)
    
    # Note: Streaming with guardrails requires collecting full response first
    response = await client.chat(
        messages=[
            {"role": "user", "content": "Explain quantum computing in simple terms."}
        ],
        temperature=0.7,
        max_tokens=300
    )
    
    # Simulate streaming output
    words = response.text.split()
    for i, word in enumerate(words):
        print(word, end=' ', flush=True)
        if (i + 1) % 10 == 0:
            print()  # New line every 10 words
        await asyncio.sleep(0.05)  # Simulate streaming delay
    
    print("\n" + "-" * 50)
    
    if response.security and response.security.cost_record:
        print(f"Cost: ${response.security.cost_record.cost:.6f}")
    
    # Example 2: Multi-turn streaming conversation
    print("\n2. Multi-turn Streaming Conversation:")
    
    conversation = [
        {"role": "user", "content": "What are the benefits of AI security?"},
    ]
    
    response1 = await client.chat(
        messages=conversation,
        temperature=0.7,
        max_tokens=200
    )
    
    print(f"Turn 1: {response1.text[:100]}...")
    
    # Add to conversation
    conversation.append({"role": "assistant", "content": response1.text})
    conversation.append({"role": "user", "content": "Can you give specific examples?"})
    
    response2 = await client.chat(
        messages=conversation,
        temperature=0.7,
        max_tokens=200
    )
    
    print(f"Turn 2: {response2.text[:100]}...")
    
    if response2.security and response2.security.cost_record:
        print(f"Cost: ${response2.security.cost_record.cost:.6f}")
    
    # Example 3: Check total costs
    print("\n3. Total Costs:")
    total_cost = await storage.get_total_cost("mistral-stream-agent")
    print(f"Total spent: ${total_cost:.6f}")
    
    # Example 4: Check budget status
    print("\n4. Budget Status:")
    budget_status = await budget_manager.get_budget_status("mistral-stream-agent")
    if budget_status:
        print(f"Budget limit: ${budget_status.limit}")
        print(f"Current usage: ${budget_status.current_usage:.6f}")
        print(f"Remaining: ${budget_status.remaining:.6f}")
        print(f"Usage: {budget_status.usage_percentage:.1f}%")
    
    print("\n" + "=" * 50)
    print("Note: Streaming with guardrails requires full response validation")
    print("For true streaming without guardrails, disable guardrails in config")


if __name__ == "__main__":
    asyncio.run(main())
