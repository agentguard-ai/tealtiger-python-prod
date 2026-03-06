"""
TealGemini Multimodal Example

This example demonstrates multimodal usage of TealGemini client
with text and image inputs.
"""

import asyncio
import os
import base64
from pathlib import Path
from tealtiger import TealGemini, TealGeminiConfig
from tealtiger.guardrails import GuardrailEngine
from tealtiger.cost import CostTracker, BudgetManager, InMemoryCostStorage


def load_image_as_base64(image_path: str) -> str:
    """Load an image file and convert to base64."""
    with open(image_path, 'rb') as f:
        image_data = f.read()
    return base64.b64encode(image_data).decode('utf-8')


async def main():
    """Run multimodal TealGemini example."""
    
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
    
    # Configure TealGemini client with vision model
    client = TealGemini(TealGeminiConfig(
        api_key=api_key,
        model='gemini-pro-vision',  # Use vision model for multimodal
        agent_id='multimodal-agent',
        enable_guardrails=True,
        enable_cost_tracking=True,
        guardrail_engine=engine,
        cost_tracker=tracker,
        budget_manager=budget_manager,
        cost_storage=storage
    ))
    
    print("TealGemini Multimodal Example")
    print("=" * 50)
    
    # Example 1: Text + Image (using inline_data)
    print("\n1. Image Analysis:")
    print("-" * 50)
    
    # Note: In a real scenario, you would load an actual image
    # For this example, we'll show the structure
    
    try:
        # Example structure for multimodal content
        # You would replace this with actual image data
        response = await client.generate_content(
            contents=[
                {
                    "role": "user",
                    "parts": [
                        {"text": "What do you see in this image?"},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": "base64_encoded_image_data_here"
                            }
                        }
                    ]
                }
            ]
        )
        
        print(f"Response: {response.text}")
        print(f"\nUsage:")
        print(f"  - Prompt tokens: {response.usage['prompt_tokens']}")
        print(f"  - Completion tokens: {response.usage['completion_tokens']}")
        print(f"  - Total tokens: {response.usage['total_tokens']}")
        
        if response.security and response.security.cost_record:
            print(f"  - Cost: ${response.security.cost_record.cost:.6f}")
    
    except Exception as e:
        print(f"Note: This example requires actual image data. Error: {e}")
    
    # Example 2: Multiple images with text
    print("\n2. Multiple Images Analysis:")
    print("-" * 50)
    
    print("""
    Structure for multiple images:
    
    contents=[
        {
            "role": "user",
            "parts": [
                {"text": "Compare these two images"},
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": "base64_image1_data"
                    }
                },
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": "base64_image2_data"
                    }
                }
            ]
        }
    ]
    """)
    
    # Example 3: Image with specific questions
    print("\n3. Structured Image Analysis:")
    print("-" * 50)
    
    print("""
    You can ask specific questions about images:
    
    - "What objects are in this image?"
    - "Describe the colors and composition"
    - "Is there any text visible in the image?"
    - "What is the mood or atmosphere?"
    - "Count the number of people/objects"
    """)
    
    # Example 4: Safety considerations
    print("\n4. Safety Considerations:")
    print("-" * 50)
    
    print("""
    TealGemini automatically:
    - Runs guardrails on text content (images are not scanned)
    - Tracks costs including image processing
    - Enforces budget limits
    - Applies safety settings to prevent harmful content
    
    Safety settings can be configured:
    
    client = TealGemini(TealGeminiConfig(
        api_key=api_key,
        model='gemini-pro-vision',
        safety_settings=[
            {
                "category": "HARM_CATEGORY_HARASSMENT",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            },
            {
                "category": "HARM_CATEGORY_HATE_SPEECH",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            }
        ]
    ))
    """)
    
    print("\n" + "=" * 50)
    print("Multimodal example structure demonstrated!")
    print("\nTo use with real images:")
    print("1. Load image file as base64")
    print("2. Include in inline_data with correct mime_type")
    print("3. Use gemini-pro-vision model")


if __name__ == "__main__":
    asyncio.run(main())
