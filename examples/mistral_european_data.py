"""
TealMistral Example - European Data Residency

This example demonstrates using TealMistral with European data residency
compliance. Mistral AI processes all data in Paris, France, making it
ideal for GDPR-compliant applications.
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
        agent_id="mistral-eu-agent",
        limit=10.0,  # $10 budget
        window="daily"
    )
    
    print("TealMistral Example - European Data Residency")
    print("=" * 60)
    print()
    print("🇪🇺 GDPR Compliance Features:")
    print("  ✓ Data processed in Paris, France")
    print("  ✓ European data residency")
    print("  ✓ GDPR-compliant infrastructure")
    print("  ✓ No data transfer outside EU")
    print()
    print("=" * 60)
    
    # Example 1: Using Mistral Small (cost-effective)
    print("\n1. Mistral Small (Cost-Effective):")
    
    client_small = TealMistral(TealMistralConfig(
        api_key="your-mistral-api-key",
        model="mistral-small",
        agent_id="mistral-eu-agent",
        guardrail_engine=engine,
        cost_tracker=tracker,
        budget_manager=budget_manager,
        cost_storage=storage
    ))
    
    response = await client_small.chat(
        messages=[
            {"role": "user", "content": "What are GDPR requirements for AI systems?"}
        ],
        temperature=0.7,
        max_tokens=250
    )
    
    print(f"Response: {response.text[:200]}...")
    print(f"Model: {response.model}")
    
    if response.security and response.security.cost_record:
        print(f"Cost: ${response.security.cost_record.cost:.6f}")
    
    # Example 2: Using Mistral Medium (balanced)
    print("\n2. Mistral Medium (Balanced Performance):")
    
    client_medium = TealMistral(TealMistralConfig(
        api_key="your-mistral-api-key",
        model="mistral-medium",
        agent_id="mistral-eu-agent",
        guardrail_engine=engine,
        cost_tracker=tracker,
        budget_manager=budget_manager,
        cost_storage=storage
    ))
    
    response = await client_medium.chat(
        messages=[
            {"role": "user", "content": "Explain data sovereignty in the context of AI."}
        ],
        temperature=0.7,
        max_tokens=250
    )
    
    print(f"Response: {response.text[:200]}...")
    print(f"Model: {response.model}")
    
    if response.security and response.security.cost_record:
        print(f"Cost: ${response.security.cost_record.cost:.6f}")
    
    # Example 3: Using Mistral Large (highest quality)
    print("\n3. Mistral Large (Highest Quality):")
    
    client_large = TealMistral(TealMistralConfig(
        api_key="your-mistral-api-key",
        model="mistral-large",
        agent_id="mistral-eu-agent",
        guardrail_engine=engine,
        cost_tracker=tracker,
        budget_manager=budget_manager,
        cost_storage=storage
    ))
    
    response = await client_large.chat(
        messages=[
            {"role": "user", "content": "What are the key differences between EU and US data protection laws?"}
        ],
        temperature=0.7,
        max_tokens=300
    )
    
    print(f"Response: {response.text[:200]}...")
    print(f"Model: {response.model}")
    
    if response.security and response.security.cost_record:
        print(f"Cost: ${response.security.cost_record.cost:.6f}")
    
    # Example 4: Using Mixtral (open-source model)
    print("\n4. Mixtral 8x7B (Open-Source Model):")
    
    client_mixtral = TealMistral(TealMistralConfig(
        api_key="your-mistral-api-key",
        model="mixtral-8x7b",
        agent_id="mistral-eu-agent",
        guardrail_engine=engine,
        cost_tracker=tracker,
        budget_manager=budget_manager,
        cost_storage=storage
    ))
    
    response = await client_mixtral.chat(
        messages=[
            {"role": "user", "content": "What is the Mixture of Experts architecture?"}
        ],
        temperature=0.7,
        max_tokens=200
    )
    
    print(f"Response: {response.text[:200]}...")
    print(f"Model: {response.model}")
    
    if response.security and response.security.cost_record:
        print(f"Cost: ${response.security.cost_record.cost:.6f}")
    
    # Example 5: Cost comparison across models
    print("\n5. Cost Comparison:")
    total_cost = await storage.get_total_cost("mistral-eu-agent")
    print(f"Total spent across all models: ${total_cost:.6f}")
    
    # Example 6: Check budget status
    print("\n6. Budget Status:")
    budget_status = await budget_manager.get_budget_status("mistral-eu-agent")
    if budget_status:
        print(f"Budget limit: ${budget_status.limit}")
        print(f"Current usage: ${budget_status.current_usage:.6f}")
        print(f"Remaining: ${budget_status.remaining:.6f}")
        print(f"Usage: {budget_status.usage_percentage:.1f}%")
    
    print("\n" + "=" * 60)
    print("Model Selection Guide:")
    print("  • mistral-small: Best for simple tasks, lowest cost")
    print("  • mistral-medium: Balanced performance and cost")
    print("  • mistral-large: Highest quality, complex reasoning")
    print("  • mixtral-8x7b: Open-source, cost-effective")
    print("  • mixtral-8x22b: Larger open-source model")
    print()
    print("All models provide European data residency! 🇪🇺")


if __name__ == "__main__":
    asyncio.run(main())
