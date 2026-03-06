"""
TealBedrock Example - Amazon Titan on AWS Bedrock

This example demonstrates using TealBedrock with Amazon Titan models
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
        agent_id="bedrock-titan-agent",
        limit=5.0,  # $5 budget
        window="daily"
    )
    
    # Create guarded Bedrock client for Titan
    client = TealBedrock(TealBedrockConfig(
        model_id="amazon.titan-text-express-v1",
        region="us-east-1",
        agent_id="bedrock-titan-agent",
        guardrail_engine=engine,
        cost_tracker=tracker,
        budget_manager=budget_manager,
        cost_storage=storage
    ))
    
    print("TealBedrock Example - Amazon Titan")
    print("=" * 50)
    
    # Example 1: Basic text generation
    print("\n1. Basic Text Generation:")
    response = await client.invoke_model(
        prompt="What are the benefits of cloud computing?",
        max_tokens=250,
        temperature=0.7
    )
    
    print(f"Response: {response.text[:200]}...")
    print(f"Provider: {response.provider}")
    print(f"Model: {response.model_id}")
    print(f"Usage: {response.usage}")
    
    if response.security and response.security.cost_record:
        print(f"Cost: ${response.security.cost_record.cost:.6f}")
    
    # Example 2: Summarization task
    print("\n2. Summarization:")
    long_text = """
    Artificial intelligence (AI) is intelligence demonstrated by machines, 
    in contrast to the natural intelligence displayed by humans and animals. 
    Leading AI textbooks define the field as the study of "intelligent agents": 
    any device that perceives its environment and takes actions that maximize 
    its chance of successfully achieving its goals. Colloquially, the term 
    "artificial intelligence" is often used to describe machines (or computers) 
    that mimic "cognitive" functions that humans associate with the human mind, 
    such as "learning" and "problem solving".
    """
    
    response = await client.invoke_model(
        prompt=f"Summarize this text in one sentence:\n\n{long_text}",
        max_tokens=100,
        temperature=0.5
    )
    
    print(f"Summary: {response.text}")
    
    if response.security and response.security.cost_record:
        print(f"Cost: ${response.security.cost_record.cost:.6f}")
    
    # Example 3: Check total costs
    print("\n3. Total Costs:")
    total_cost = await storage.get_total_cost("bedrock-titan-agent")
    print(f"Total spent: ${total_cost:.6f}")
    
    # Example 4: Check budget status
    print("\n4. Budget Status:")
    budget_status = await budget_manager.get_budget_status("bedrock-titan-agent")
    if budget_status:
        print(f"Budget limit: ${budget_status.limit}")
        print(f"Current usage: ${budget_status.current_usage:.6f}")
        print(f"Remaining: ${budget_status.remaining:.6f}")
        print(f"Usage: {budget_status.usage_percentage:.1f}%")


if __name__ == "__main__":
    asyncio.run(main())
