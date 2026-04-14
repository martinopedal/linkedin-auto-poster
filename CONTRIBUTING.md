# Contributing

Thanks for your interest in contributing to LinkedIn Auto-Poster!

## Getting Started

1. **Fork** this repository
2. **Clone** your fork:
   ```bash
   git clone https://github.com/your-username/linkedin-auto-poster.git
   cd linkedin-auto-poster
   ```
3. **Set up** your development environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # or .venv\Scripts\activate on Windows
   pip install -r requirements.txt
   pip install pytest pytest-cov ruff responses
   ```

## Development Workflow

1. Create a **feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes

3. **Run tests**:
   ```bash
   python -m pytest --tb=short -q
   ```

4. **Run linter**:
   ```bash
   python -m ruff check src/ tests/ main.py
   ```

5. **Commit** with a clear message:
   ```bash
   git commit -m "Add: description of your change"
   ```

6. **Push** and open a Pull Request

## Code Style

- Python 3.12+
- Ruff for linting (config in `pyproject.toml`)
- Line length: 120 characters
- Type hints encouraged

## Pull Request Checklist

- [ ] Tests pass (`pytest`)
- [ ] Lint passes (`ruff check src/ tests/`)
- [ ] README.md updated if features/config/architecture changed
- [ ] No secrets, PII, or customer names in code or drafts

## Reporting Issues

- Use GitHub Issues for bugs and feature requests
- For security vulnerabilities, see [SECURITY.md](SECURITY.md)
