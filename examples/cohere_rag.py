"""
TealCohere Example - RAG (Retrieval-Augmented Generation)

This example demonstrates using TealCohere with RAG capabilities,
including document-based responses and citation tracking.
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
        agent_id="cohere-rag-agent",
        limit=10.0,  # $10 budget
        window="daily"
    )
    
    # Create guarded Cohere client
    client = TealCohere(TealCohereConfig(
        api_key="your-cohere-api-key",
        model="command",
        agent_id="cohere-rag-agent",
        guardrail_engine=engine,
        cost_tracker=tracker,
        budget_manager=budget_manager,
        cost_storage=storage
    ))
    
    print("TealCohere Example - RAG (Retrieval-Augmented Generation)")
    print("=" * 60)
    
    # Example 1: RAG with documents
    print("\n1. RAG with Documents:")
    
    documents = [
        {
            "title": "TealTiger Overview",
            "snippet": "TealTiger is an AI security platform that provides guardrails, "
                      "cost tracking, and policy management for LLM applications. "
                      "It supports multiple providers including OpenAI, Anthropic, and Cohere."
        },
        {
            "title": "TealTiger Features",
            "snippet": "Key features include PII detection, prompt injection prevention, "
                      "content moderation, budget management, and comprehensive audit logging."
        },
        {
            "title": "TealTiger Pricing",
            "snippet": "TealTiger offers flexible pricing with a free tier for development "
                      "and enterprise plans for production use. Cost tracking helps optimize spending."
        }
    ]
    
    response = await client.chat(
        message="What is TealTiger and what are its main features?",
        documents=documents,
        temperature=0.5,
        max_tokens=300
    )
    
    print(f"Response: {response.text}")
    print(f"\nCitations: {len(response.citations) if response.citations else 0}")
    
    if response.citations:
        print("\nCitation Details:")
        for i, citation in enumerate(response.citations[:3], 1):  # Show first 3
            print(f"  {i}. {citation}")
    
    if response.security and response.security.cost_record:
        print(f"\nCost: ${response.security.cost_record.cost:.6f}")
    
    # Example 2: RAG with web search connector
    print("\n2. RAG with Web Search Connector:")
    
    response = await client.chat(
        message="What are the latest developments in AI security?",
        connectors=[{"id": "web-search"}],
        temperature=0.5,
        max_tokens=300
    )
    
    print(f"Response: {response.text[:200]}...")
    
    if response.search_queries:
        print(f"\nSearch Queries Used: {response.search_queries}")
    
    if response.citations:
        print(f"Citations: {len(response.citations)}")
    
    if response.security and response.security.cost_record:
        print(f"Cost: ${response.security.cost_record.cost:.6f}")
    
    # Example 3: Multi-turn RAG conversation
    print("\n3. Multi-turn RAG Conversation:")
    
    chat_history = []
    
    # First turn
    response1 = await client.chat(
        message="What security features does TealTiger provide?",
        documents=documents,
        temperature=0.5,
        max_tokens=200
    )
    
    print(f"Turn 1: {response1.text[:150]}...")
    
    # Add to history
    chat_history.append({"role": "USER", "message": "What security features does TealTiger provide?"})
    chat_history.append({"role": "CHATBOT", "message": response1.text})
    
    # Second turn with context
    response2 = await client.chat(
        message="How does the cost tracking work?",
        chat_history=chat_history,
        documents=documents,
        temperature=0.5,
        max_tokens=200
    )
    
    print(f"Turn 2: {response2.text[:150]}...")
    
    if response2.security and response2.security.cost_record:
        print(f"Cost: ${response2.security.cost_record.cost:.6f}")
    
    # Example 4: Check total costs
    print("\n4. Total Costs:")
    total_cost = await storage.get_total_cost("cohere-rag-agent")
    print(f"Total spent: ${total_cost:.6f}")
    
    # Example 5: Check budget status
    print("\n5. Budget Status:")
    budget_status = await budget_manager.get_budget_status("cohere-rag-agent")
    if budget_status:
        print(f"Budget limit: ${budget_status.limit}")
        print(f"Current usage: ${budget_status.current_usage:.6f}")
        print(f"Remaining: ${budget_status.remaining:.6f}")
        print(f"Usage: {budget_status.usage_percentage:.1f}%")


if __name__ == "__main__":
    asyncio.run(main())
