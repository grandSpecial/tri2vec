# Contributing

Thanks for contributing to TRI2VEC.

## Principles

- Keep patient trust first
- Keep code simple and auditable
- Avoid hidden behavior and opaque dependencies
- Favor explicit privacy and safety language

## Local Workflow

1. Create a branch.
2. Make focused changes.
3. Run checks:

```bash
python3 -m compileall main.py models.py import.py settings.py privacy.py landing_page.py
```

4. Update docs when behavior changes.

## Pull Request Expectations

- Small, reviewable diff
- Clear rationale in description
- Privacy/security impact noted
- No secrets committed

## Code Style

- Prefer explicit names over clever abstractions
- Keep functions short and single-purpose
- Add comments only when logic is non-obvious
