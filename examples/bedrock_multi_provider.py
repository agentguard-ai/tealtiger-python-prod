"""
TealBedrock Example - Multi-Provider Support

This example demonstrates using TealBedrock with multiple model providers
on AWS Bedrock (Claude, Titan, Llama) with integrated security and cost tracking.
"""

import asyncio
from tealtiger import TealBedrock, TealBedrockConfig
from tealtiger.guardrails import GuardrailEngine
from tealtiger.cost import CostTracker, BudgetManager, InMemoryCostStorage


async def test_provider(model_id: str, prompt: str, engine, tracker, budget_manager, storage):
    """Test a specific Bedrock model provider."""
    client = TealBedrock(TealBedrockConfig(
        model_id=model_id,
        region="us-east-1",
        agent_id="bedrock-multi-agent",
        guardrail_engine=engine,
        cost_tracker=tracker,
        budget_manager=budget_manager,
        cost_storage=storage
    ))
    
    response = await client.invoke_model(
        prompt=prompt,
        max_tokens=150,
        temperature=0.7
    )
    
    return response


async def main():
    # Create shared security components
    engine = GuardrailEngine()
    tracker = CostTracker()
    storage = InMemoryCostStorage()
    budget_manager = BudgetManager(storage)
    
    # Set a shared budget
    await budget_manager.set_budget(
        agent_id="bedrock-multi-agent",
        limit=20.0,  # $20 budget
        window="daily"
    )
    
    print("TealBedrock Example - Multi-Provider Support")
    print("=" * 60)
    
    prompt = "What is the capital of France?"
    
    # Test different providers
    providers = [
        ("anthropic.claude-v2", "Anthropic Claude"),
        ("amazon.titan-text-express-v1", "Amazon Titan"),
        ("meta.llama2-13b-chat-v1", "Meta Llama 2"),
        ("cohere.command-text-v14", "Cohere Command"),
    ]
    
    for model_id, provider_name in providers:
        print(f"\n{'=' * 60}")
        print(f"Testing: {provider_name}")
        print(f"Model: {model_id}")
        print(f"{'=' * 60}")
        
        try:
            response = await test_provider(
                model_id, prompt, engine, tracker, budget_manager, storage
            )
            
            print(f"\nResponse: {response.text[:150]}...")
            print(f"Provider: {response.provider}")
            print(f"Usage: {response.usage}")
            
            if response.security and response.security.cost_record:
                print(f"Cost: ${response.security.cost_record.cost:.6f}")
        
        except Exception as e:
            print(f"Error: {str(e)}")
    
    # Summary
    print(f"\n{'=' * 60}")
    print("Summary")
    print(f"{'=' * 60}")
    
    total_cost = await storage.get_total_cost("bedrock-multi-agent")
    print(f"Total spent across all providers: ${total_cost:.6f}")
    
    budget_status = await budget_manager.get_budget_status("bedrock-multi-agent")
    if budget_status:
        print(f"Budget limit: ${budget_status.limit}")
        print(f"Current usage: ${budget_status.current_usage:.6f}")
        print(f"Remaining: ${budget_status.remaining:.6f}")
        print(f"Usage: {budget_status.usage_percentage:.1f}%")
    
    # Cost comparison
    print(f"\n{'=' * 60}")
    print("Cost Comparison")
    print(f"{'=' * 60}")
    print("Note: Costs vary by model. Claude is typically more expensive")
    print("but offers better quality. Titan is cost-effective for simpler tasks.")
    print("Llama 2 offers good balance. Cohere excels at RAG use cases.")


if __name__ == "__main__":
    asyncio.run(main())
