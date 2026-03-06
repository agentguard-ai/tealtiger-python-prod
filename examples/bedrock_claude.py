"""
TealBedrock Example - Anthropic Claude on AWS Bedrock

This example demonstrates using TealBedrock with Anthropic Claude models
on AWS Bedrock with integrated security and cost tracking.
"""

import asyncio
from tealtiger import TealBedrock, TealBedrockConfig
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
        agent_id="bedrock-claude-agent",
        limit=10.0,  # $10 budget
        window="daily"
    )
    
    # Create guarded Bedrock client for Claude
    client = TealBedrock(TealBedrockConfig(
        model_id="anthropic.claude-v2",
        region="us-east-1",
        agent_id="bedrock-claude-agent",
        guardrail_engine=engine,
        cost_tracker=tracker,
        budget_manager=budget_manager,
        cost_storage=storage
    ))
    
    print("TealBedrock Example - Anthropic Claude")
    print("=" * 50)
    
    # Example 1: Basic text generation
    print("\n1. Basic Text Generation:")
    response = await client.invoke_model(
        prompt="Explain quantum computing in simple terms.",
        max_tokens=300,
        temperature=0.7
    )
    
    print(f"Response: {response.text[:200]}...")
    print(f"Provider: {response.provider}")
    print(f"Model: {response.model_id}")
    print(f"Usage: {response.usage}")
    
    if response.security and response.security.cost_record:
        print(f"Cost: ${response.security.cost_record.cost:.6f}")
    
    # Example 2: Creative writing with higher temperature
    print("\n2. Creative Writing:")
    response = await client.invoke_model(
        prompt="Write a short poem about artificial intelligence.",
        max_tokens=200,
        temperature=0.9
    )
    
    print(f"Response:\n{response.text}")
    
    if response.security and response.security.cost_record:
        print(f"Cost: ${response.security.cost_record.cost:.6f}")
    
    # Example 3: Check total costs
    print("\n3. Total Costs:")
    total_cost = await storage.get_total_cost("bedrock-claude-agent")
    print(f"Total spent: ${total_cost:.6f}")
    
    # Example 4: Check budget status
    print("\n4. Budget Status:")
    budget_status = await budget_manager.get_budget_status("bedrock-claude-agent")
    if budget_status:
        print(f"Budget limit: ${budget_status.limit}")
        print(f"Current usage: ${budget_status.current_usage:.6f}")
        print(f"Remaining: ${budget_status.remaining:.6f}")
        print(f"Usage: {budget_status.usage_percentage:.1f}%")


if __name__ == "__main__":
    asyncio.run(main())
