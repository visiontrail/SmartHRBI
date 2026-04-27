# Contributing to Cognitrix

Thank you for your interest in contributing to Cognitrix — an open-source AI-native BI platform for natural language analytics on structured data.

## Ways to Contribute

- **Bug reports** — Open an issue describing the problem, reproduction steps, and expected vs actual behavior.
- **Feature requests** — Open an issue with the use case and proposed behavior. For large changes, discuss before coding.
- **Pull requests** — Fix bugs, improve docs, or implement agreed-upon features.
- **Sample data & semantic models** — Add YAML metric definitions to `models/` for new domains (Finance, Sales, Operations).
- **LLM provider integrations** — Test and document compatibility with other OpenAI-compatible endpoints.

## Development Setup

```bash
# Clone and bootstrap
git clone <repo-url>
cd cognitrix
make bootstrap
make env-check
make dev
```

Add your API key to `apps/api/.env`:

```env
AI_API_KEY=your-deepseek-or-openai-compatible-key
```

## Running Tests

```bash
# Backend unit, integration, and security tests
make test

# Frontend unit tests (Vitest)
cd apps/web && npx vitest run

# Full gate: lint + test + build + smoke
make test-all
```

All pull requests must pass `make test` and `make lint` before review.

## Pull Request Guidelines

1. **Branch from `master`** — use a descriptive name: `fix/agent-timeout`, `feat/recharts-boxplot`, `docs/quickstart-guide`.
2. **Keep PRs focused** — one logical change per PR. Split large features into smaller reviewable units.
3. **Write tests** — new backend behavior needs pytest coverage; new frontend components need Vitest unit tests.
4. **No new dependencies without discussion** — especially for frontend bundles or Python packages that affect Docker image size.
5. **Update docs** — if your change affects configuration, API surface, or user-visible behavior, update `README.md` and `README_CN.md` accordingly.

## Code Style

- **Python** — PEP 8; use `ruff` or `flake8` (run via `make lint`).
- **TypeScript / React** — follow existing ESLint config; run `next lint` via `make lint`.
- **No commented-out code** — remove dead code rather than commenting it out.
- **No inline `print()` or `console.log()` in committed code** — use the structured logger (`audit.py` / structured SSE events).

## Semantic Model Contributions (`models/`)

The YAML metric layer prevents AI hallucinations on domain KPIs. When adding metrics:

- Follow the existing YAML schema in `models/hr/` or `models/pm/`.
- Include a `description`, `sql_template`, and `group_by` field.
- Add a unit test in `tests/unit/` that compiles the metric and checks the generated SQL.

## Reporting Security Issues

Do **not** open a public issue for security vulnerabilities. Email the maintainer directly or use GitHub's private security advisory feature. Include reproduction steps and impact assessment.

## License

By contributing, you agree that your contributions will be licensed under the same [MIT License](LICENSE) as the project.
