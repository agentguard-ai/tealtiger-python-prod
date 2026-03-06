"""
TealCohere Example - Embeddings

This example demonstrates using TealCohere for generating embeddings
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
        agent_id="cohere-embed-agent",
        limit=5.0,  # $5 budget
        window="daily"
    )
    
    # Create guarded Cohere client
    client = TealCohere(TealCohereConfig(
        api_key="your-cohere-api-key",
        model="command",
        agent_id="cohere-embed-agent",
        guardrail_engine=engine,
        cost_tracker=tracker,
        budget_manager=budget_manager,
        cost_storage=storage
    ))
    
    print("TealCohere Example - Embeddings")
    print("=" * 50)
    
    # Example 1: Embed documents for search
    print("\n1. Embed Documents for Search:")
    
    documents = [
        "TealTiger provides AI security and cost tracking.",
        "Machine learning models can be expensive to run.",
        "Guardrails help prevent security vulnerabilities.",
        "Budget management is crucial for AI applications."
    ]
    
    response = await client.embed(
        texts=documents,
        input_type="search_document"
    )
    
    print(f"Generated {len(response.embeddings)} embeddings")
    print(f"Embedding dimension: {len(response.embeddings[0])}")
    print(f"Model: {response.model}")
    print(f"Usage: {response.usage}")
    
    if response.security and response.security.cost_record:
        print(f"Cost: ${response.security.cost_record.cost:.6f}")
    
    # Example 2: Embed search query
    print("\n2. Embed Search Query:")
    
    query = ["What are the security features?"]
    
    response = await client.embed(
        texts=query,
        input_type="search_query"
    )
    
    print(f"Query embedding dimension: {len(response.embeddings[0])}")
    
    if response.security and response.security.cost_record:
        print(f"Cost: ${response.security.cost_record.cost:.6f}")
    
    # Example 3: Embed for classification
    print("\n3. Embed for Classification:")
    
    texts = [
        "This is a positive review of the product.",
        "I'm not satisfied with the service.",
        "The quality is excellent and worth the price."
    ]
    
    response = await client.embed(
        texts=texts,
        input_type="classification"
    )
    
    print(f"Generated {len(response.embeddings)} classification embeddings")
    
    if response.security and response.security.cost_record:
        print(f"Cost: ${response.security.cost_record.cost:.6f}")
    
    # Example 4: Embed for clustering
    print("\n4. Embed for Clustering:")
    
    texts = [
        "AI security is important.",
        "Cost tracking helps manage budgets.",
        "Machine learning requires careful monitoring.",
        "Budget management prevents overspending."
    ]
    
    response = await client.embed(
        texts=texts,
        input_type="clustering"
    )
    
    print(f"Generated {len(response.embeddings)} clustering embeddings")
    
    if response.security and response.security.cost_record:
        print(f"Cost: ${response.security.cost_record.cost:.6f}")
    
    # Example 5: Check total costs
    print("\n5. Total Costs:")
    total_cost = await storage.get_total_cost("cohere-embed-agent")
    print(f"Total spent: ${total_cost:.6f}")
    
    # Example 6: Check budget status
    print("\n6. Budget Status:")
    budget_status = await budget_manager.get_budget_status("cohere-embed-agent")
    if budget_status:
        print(f"Budget limit: ${budget_status.limit}")
        print(f"Current usage: ${budget_status.current_usage:.6f}")
        print(f"Remaining: ${budget_status.remaining:.6f}")
        print(f"Usage: {budget_status.usage_percentage:.1f}%")
    
    print("\n" + "=" * 50)
    print("Note: Embeddings can be used for:")
    print("  - Semantic search")
    print("  - Document similarity")
    print("  - Classification")
    print("  - Clustering")
    print("  - Recommendation systems")


if __name__ == "__main__":
    asyncio.run(main())
