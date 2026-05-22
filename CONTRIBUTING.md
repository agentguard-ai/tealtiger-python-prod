# Contributing to AgentGuard Python SDK

Thank you for considering contributing to AgentGuard Python SDK!

## 🚀 Getting Started

### Prerequisites

- Python 3.8 or higher
- pip or poetry
- Git

### Development Setup

1. **Fork and clone the repository**
   ```bash
   git clone https://github.com/YOUR_USERNAME/tealtiger-python-prod.git
   cd tealtiger-python-prod
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -e ".[dev]"
   ```

4. **Run tests**
   ```bash
   pytest
   ```

## 📝 Development Workflow

### 1. Create a Branch

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/your-bug-fix
```

Branch naming conventions:
- `feature/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation changes
- `refactor/` - Code refactoring
- `test/` - Test improvements

### 2. Make Your Changes

- Write clear, concise code
- Follow PEP 8 style guidelines
- Add type hints to all functions
- Add tests for new functionality
- Update documentation as needed

### 3. Run Quality Checks

```bash
# Format code
black src tests
isort src tests

# Run linter
ruff check src tests

# Run type checker
mypy src

# Run tests
pytest

# Run tests with coverage
pytest --cov=agentguard --cov-report=html
```

### 4. Commit Your Changes

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```bash
git commit -m "feat: add new policy validation feature"
git commit -m "fix: resolve timeout issue in execute_tool"
git commit -m "docs: update API reference for PolicyBuilder"
```

Commit message format:
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `style:` - Code style changes (formatting, etc.)
- `refactor:` - Code refactoring
- `test:` - Test additions or changes
- `chore:` - Build process or auxiliary tool changes

### 5. Push and Create PR

```bash
git push origin feature/your-feature-name
```

Then create a Pull Request on GitHub.

## 🧪 Testing Guidelines

### Writing Tests

- Place tests in `tests/` directory
- Use descriptive test names
- Test both success and failure cases
- Aim for high code coverage (>80%)

Example test structure:

```python
import pytest
from agentguard import AgentGuard


def test_client_initialization():
    """Test that client initializes correctly."""
    guard = AgentGuard(
        api_key="test-key",
        ssa_url="http://localhost:3000"
    )
    
    assert guard.api_key == "test-key"
    assert guard.ssa_url == "http://localhost:3000"


@pytest.mark.asyncio
async def test_async_execution():
    """Test async tool execution."""
    guard = AgentGuard(
        api_key="test-key",
        ssa_url="http://localhost:3000"
    )
    
    # Test implementation
    pass
```

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_client.py

# Run with coverage
pytest --cov=agentguard --cov-report=html

# Run with verbose output
pytest -v
```

## 📚 Documentation Guidelines

### Code Documentation

- Add docstrings to all public functions and classes
- Use Google-style docstrings
- Include parameter descriptions and return types
- Provide usage examples

```python
def execute_tool(
    self,
    tool_name: str,
    parameters: Dict[str, Any],
    context: ExecutionContext,
) -> ExecutionResult:
    """Execute a tool with security evaluation.
    
    Args:
        tool_name: Name of the tool to execute
        parameters: Tool parameters as a dictionary
        context: Execution context with session info
    
    Returns:
        ExecutionResult containing data and security decision
    
    Raises:
        AgentGuardError: If validation or execution fails
    
    Example:
        >>> guard = AgentGuard(api_key="key", ssa_url="http://localhost:3000")
        >>> result = guard.execute_tool_sync(
        ...     "web-search",
        ...     {"query": "AI security"},
        ...     {"session_id": "123"}
        ... )
    """
    pass
```

### README Updates

- Keep examples up-to-date
- Add new features to the feature list
- Update API reference for new methods

## 🎨 Code Style Guidelines

### Python Style

- Follow PEP 8
- Use type hints for all functions
- Maximum line length: 100 characters
- Use meaningful variable names

### Formatting

We use Black for code formatting:

```bash
black src tests
```

### Import Sorting

We use isort for import sorting:

```bash
isort src tests
```

### Linting

We use Ruff for linting:

```bash
ruff check src tests
```

## 🐛 Bug Reports

### Before Submitting

1. Check if the bug has already been reported
2. Try to reproduce with the latest version
3. Gather relevant information

### Bug Report Template

Use the bug report template when creating an issue.

## 💡 Feature Requests

### Before Submitting

1. Check if the feature has already been requested
2. Consider if it fits the project's scope
3. Think about how it would work

### Feature Request Template

Use the feature request template when creating an issue.

## 🔍 Code Review Process

### What We Look For

- **Correctness** - Does the code work as intended?
- **Tests** - Are there adequate tests?
- **Documentation** - Is the code well-documented?
- **Style** - Does it follow our style guidelines?
- **Performance** - Are there any performance concerns?
- **Security** - Are there any security implications?

### Review Timeline

- Initial review: Within 2-3 business days
- Follow-up reviews: Within 1-2 business days
- Merge: After approval from at least one maintainer

## 📜 Code of Conduct

### Our Pledge

We are committed to providing a welcoming and inspiring community for all.

### Our Standards

**Positive behavior includes:**
- Using welcoming and inclusive language
- Being respectful of differing viewpoints
- Gracefully accepting constructive criticism
- Focusing on what is best for the community
- Showing empathy towards other community members

**Unacceptable behavior includes:**
- Harassment, trolling, or discriminatory comments
- Publishing others' private information
- Other conduct which could reasonably be considered inappropriate

### Enforcement

Violations may result in:
1. Warning
2. Temporary ban
3. Permanent ban

Report violations to: agentguard@proton.me

## 🏆 Recognition

Contributors will be:
- Listed in our [Contributors](https://github.com/agentguard-ai/tealtiger-python-prod/graphs/contributors) page
- Mentioned in release notes for significant contributions
- Invited to our contributors community

## 📞 Getting Help

- **Questions?** Open a [Discussion](https://github.com/agentguard-ai/tealtiger-python-prod/discussions)
- **Bug?** Open an [Issue](https://github.com/agentguard-ai/tealtiger-python-prod/issues)
- **Security?** Email agentguard@proton.me

## 📄 License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing to AgentGuard Python SDK! 🎉
