"""
Audit Redaction Examples

Demonstrates security-by-default redaction of sensitive content in audit logs.

Examples:
1. Production configuration (HASH redaction - default)
2. Development configuration (debug mode)
3. Custom redaction rules
4. PII detection integration
5. Redaction level comparison
6. Size-only redaction
7. Category-only redaction
8. Full redaction
"""

import asyncio
from tealtiger.core.audit.teal_audit import TealAudit, AuditConfig
from tealtiger.core.audit.types import RedactionLevel, AuditEventType
from tealtiger.core.audit.output import ConsoleOutput
from tealtiger.core.context.context_manager import ContextManager


# Example 1: Production configuration (HASH redaction - default)
async def example_production_config():
    """Production-safe configuration with HASH redaction."""
    print("\n=== Example 1: Production Configuration (HASH Redaction) ===\n")
    
    # Default configuration - secure by default
    audit = TealAudit(
        outputs=[ConsoleOutput()],
        config=AuditConfig(
            input_redaction=RedactionLevel.HASH,
            output_redaction=RedactionLevel.HASH,
            detect_pii=True,
            debug_mode=False
        )
    )
    
    context = ContextManager.create_context(tenant_id='acme-corp')
    
    # Log event with sensitive content
    audit.log_event(
        event_type=AuditEventType.LLM_REQUEST,
        context=context,
        metadata={
            'model': 'gpt-4',
            'input': 'My SSN is 123-45-6789',
            'output': 'I can help you with that.'
        }
    )
    
    print("✓ Sensitive content is hashed (SHA-256)")
    print("✓ PII is detected and redacted")
    print("✓ Safe for production audit logs")


# Example 2: Development configuration (debug mode)
async def example_development_config():
    """Development configuration with debug mode (use with caution)."""
    print("\n=== Example 2: Development Configuration (Debug Mode) ===\n")
    
    # Debug mode - includes raw content (DANGEROUS in production)
    audit = TealAudit(
        outputs=[ConsoleOutput()],
        config=AuditConfig(
            input_redaction=RedactionLevel.NONE,
            output_redaction=RedactionLevel.SIZE_ONLY,
            detect_pii=True,
            debug_mode=True  # Explicit opt-in required
        )
    )
    
    context = ContextManager.create_context(tenant_id='acme-corp')
    
    # Log event
    audit.log_event(
        event_type=AuditEventType.LLM_REQUEST,
        context=context,
        metadata={
            'model': 'gpt-4',
            'input': 'Hello, world!',
            'output': 'Hi there!'
        }
    )
    
    print("⚠️  Debug mode enabled - raw content included")
    print("⚠️  Only use in development environments")
    print("⚠️  Never enable debug mode in production")


# Example 3: Custom redaction rules
async def example_custom_redaction():
    """Custom redaction rules for domain-specific patterns."""
    print("\n=== Example 3: Custom Redaction Rules ===\n")
    
    import re
    
    # Custom redaction for API keys and tokens
    audit = TealAudit(
        outputs=[ConsoleOutput()],
        config=AuditConfig(
            input_redaction=RedactionLevel.HASH,
            output_redaction=RedactionLevel.HASH,
            detect_pii=True,
            custom_redaction=[
                {
                    'pattern': re.compile(r'sk-[a-zA-Z0-9]{48}'),
                    'replacement': '[REDACTED_API_KEY]'
                },
                {
                    'pattern': re.compile(r'Bearer [a-zA-Z0-9\-._~+/]+=*'),
                    'replacement': '[REDACTED_TOKEN]'
                }
            ]
        )
    )
    
    context = ContextManager.create_context(tenant_id='acme-corp')
    
    # Log event with API key
    audit.log_event(
        event_type=AuditEventType.LLM_REQUEST,
        context=context,
        metadata={
            'model': 'gpt-4',
            'api_key': 'sk-1234567890abcdefghijklmnopqrstuvwxyz1234567890',
            'auth': 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9'
        }
    )
    
    print("✓ Custom patterns redacted (API keys, tokens)")
    print("✓ Domain-specific sensitive data protected")


# Example 4: PII detection integration
async def example_pii_detection():
    """PII detection before logging."""
    print("\n=== Example 4: PII Detection Integration ===\n")
    
    # Enable PII detection (enabled by default)
    audit = TealAudit(
        outputs=[ConsoleOutput()],
        config=AuditConfig(
            input_redaction=RedactionLevel.HASH,
            output_redaction=RedactionLevel.HASH,
            detect_pii=True
        )
    )
    
    context = ContextManager.create_context(tenant_id='acme-corp')
    
    # Log event with various PII types
    audit.log_event(
        event_type=AuditEventType.GUARDRAIL_CHECK,
        context=context,
        metadata={
            'content': '''
                Customer information:
                - SSN: 123-45-6789
                - Email: john.doe@example.com
                - Phone: (555) 123-4567
                - Credit Card: 4532-1234-5678-9010
            '''
        }
    )
    
    print("✓ SSN detected and redacted")
    print("✓ Email detected and redacted")
    print("✓ Phone number detected and redacted")
    print("✓ Credit card detected and redacted")


# Example 5: Redaction level comparison
async def example_redaction_levels():
    """Compare different redaction levels."""
    print("\n=== Example 5: Redaction Level Comparison ===\n")
    
    content = "My SSN is 123-45-6789 and email is john@example.com"
    context = ContextManager.create_context(tenant_id='acme-corp')
    
    levels = [
        RedactionLevel.NONE,
        RedactionLevel.HASH,
        RedactionLevel.SIZE_ONLY,
        RedactionLevel.CATEGORY_ONLY,
        RedactionLevel.FULL
    ]
    
    for level in levels:
        print(f"\n{level.value}:")
        
        audit = TealAudit(
            outputs=[ConsoleOutput()],
            config=AuditConfig(
                input_redaction=level,
                output_redaction=level,
                detect_pii=True,
                debug_mode=(level == RedactionLevel.NONE)
            )
        )
        
        audit.log_event(
            event_type=AuditEventType.POLICY_EVALUATION,
            context=context,
            metadata={'content': content}
        )
        
        if level == RedactionLevel.NONE:
            print("  - Raw content included (DANGEROUS)")
        elif level == RedactionLevel.HASH:
            print("  - SHA-256 hash + size")
        elif level == RedactionLevel.SIZE_ONLY:
            print("  - Content size only")
        elif level == RedactionLevel.CATEGORY_ONLY:
            print("  - Content category only")
        elif level == RedactionLevel.FULL:
            print("  - Fully redacted (no metadata)")


# Example 6: Size-only redaction
async def example_size_only_redaction():
    """Size-only redaction for content analysis."""
    print("\n=== Example 6: Size-Only Redaction ===\n")
    
    audit = TealAudit(
        outputs=[ConsoleOutput()],
        config=AuditConfig(
            input_redaction=RedactionLevel.SIZE_ONLY,
            output_redaction=RedactionLevel.SIZE_ONLY
        )
    )
    
    context = ContextManager.create_context(tenant_id='acme-corp')
    
    # Log events with different content sizes
    for size in [100, 1000, 10000]:
        content = "x" * size
        audit.log_event(
            event_type=AuditEventType.LLM_REQUEST,
            context=context,
            metadata={
                'content': content,
                'size': size
            }
        )
    
    print("✓ Only content size is logged")
    print("✓ Useful for analyzing content size patterns")
    print("✓ No raw content or hashes exposed")


# Example 7: Category-only redaction
async def example_category_only_redaction():
    """Category-only redaction for content classification."""
    print("\n=== Example 7: Category-Only Redaction ===\n")
    
    audit = TealAudit(
        outputs=[ConsoleOutput()],
        config=AuditConfig(
            input_redaction=RedactionLevel.CATEGORY_ONLY,
            output_redaction=RedactionLevel.CATEGORY_ONLY
        )
    )
    
    context = ContextManager.create_context(tenant_id='acme-corp')
    
    # Log events with different content categories
    categories = [
        ('user_query', 'What is the weather today?'),
        ('system_prompt', 'You are a helpful assistant.'),
        ('tool_call', '{"tool": "get_weather", "args": {}}'),
        ('llm_response', 'The weather is sunny today.')
    ]
    
    for category, content in categories:
        audit.log_event(
            event_type=AuditEventType.LLM_REQUEST,
            context=context,
            metadata={
                'category': category,
                'content': content
            }
        )
    
    print("✓ Only content category is logged")
    print("✓ Useful for analyzing content type distribution")
    print("✓ No raw content, hashes, or sizes exposed")


# Example 8: Full redaction
async def example_full_redaction():
    """Full redaction for maximum security."""
    print("\n=== Example 8: Full Redaction ===\n")
    
    audit = TealAudit(
        outputs=[ConsoleOutput()],
        config=AuditConfig(
            input_redaction=RedactionLevel.FULL,
            output_redaction=RedactionLevel.FULL
        )
    )
    
    context = ContextManager.create_context(tenant_id='acme-corp')
    
    # Log event with sensitive content
    audit.log_event(
        event_type=AuditEventType.LLM_REQUEST,
        context=context,
        metadata={
            'content': 'Highly sensitive information that must be fully redacted'
        }
    )
    
    print("✓ Content fully redacted")
    print("✓ Only metadata indicating redaction is present")
    print("✓ Maximum security for highly sensitive data")


async def main():
    """Run all examples."""
    print("=" * 70)
    print("Audit Redaction Examples")
    print("=" * 70)
    
    await example_production_config()
    await example_development_config()
    await example_custom_redaction()
    await example_pii_detection()
    await example_redaction_levels()
    await example_size_only_redaction()
    await example_category_only_redaction()
    await example_full_redaction()
    
    print("\n" + "=" * 70)
    print("All examples completed!")
    print("=" * 70)
    print("\nKey Takeaways:")
    print("- Use HASH redaction in production (default)")
    print("- Enable PII detection (enabled by default)")
    print("- Only use debug mode in development")
    print("- Choose redaction level based on security requirements")
    print("=" * 70)


if __name__ == '__main__':
    asyncio.run(main())
