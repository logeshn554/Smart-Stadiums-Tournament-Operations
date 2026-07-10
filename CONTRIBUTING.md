# Contributing to StadiumOps AI

Thank you for contributing to StadiumOps AI! To keep our codebase clean, predictable, and easy to maintain, we enforce strict standards and use automated checks. Please follow these guidelines.

---

## Local Development Setup

1. **Clone the Repository and Install Python 3.11+**.
2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Install Pre-Commit Hooks**:
   We use `pre-commit` to automate local code quality checks before any commit is finalized.
   ```bash
   pip install pre-commit
   pre-commit install
   ```
   *The hooks will now automatically format and lint your code on every `git commit`.*

---

## Coding Habits and Standards

* **Keep Code Predictable and Maintenance-Friendly**: Write clean, explicit logic. Avoid complex, "clever" patterns that other developers cannot easily follow.
* **Strict Linting & Formatting**:
  * We use **Ruff** for formatting and linting.
  * Run checks manually before pushing:
    ```bash
    ruff check backend/
    ruff format backend/
    ```
* **Type Hints**: All function interfaces and data structures must have explicit type annotations.
* **Docstrings**: Public methods and modules must have Google-style docstrings.

---

## Everyday Verification Cycle

Before pushing your changes or opening a Pull Request, run the local check suite:

1. **Run All Hooks Manually**:
   Verify everything passes:
   ```bash
   pre-commit run --all-files
   ```
2. **Run Pytest & Check Test Coverage**:
   We enforce a strict minimum code coverage target of **95%**:
   ```bash
   python -m pytest backend/tests/ -v --cov=backend --cov-report=term-missing
   ```

---

## Pull Request Checklist

When submitting a PR, make sure:
- [ ] Pre-commit hooks run cleanly with zero warnings/errors.
- [ ] Ruff formatter and linter report 100% clean.
- [ ] No commented-out code remains (enforced by the `ERA` check).
- [ ] Unit, integration, and accessibility tests pass.
- [ ] Test coverage meets or exceeds the **95%** threshold.
- [ ] Key design choices or changes are updated in the docs/README if applicable.
