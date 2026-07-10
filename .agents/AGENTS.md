# StadiumOps AI — Developer & Agent Workspace Guidelines

These project-scoped guidelines define coding standards, architectural requirements, and verification protocols for both human developers and agent assistants working in this repository.

---

## 1. Architectural Philosophy
* **Explainable Decisions**: The core safety rules in `backend/core/decision_engine.py` must remain pure, deterministic, and stateless functions. Avoid machine learning or non-deterministic mechanisms for safety-critical triage.
* **Separation of Concerns**: The decision engine has zero knowledge of HTTP or FastAPI. Keep web endpoints (`backend/api/routes.py`), data validation schemas (`backend/models/schemas.py`), and decision engine rules decoupled.

---

## 2. Coding Standards
* **Python Target**: Python 3.11+.
* **Linting & Formatting**: Clean compliance with Ruff is non-negotiable. 
  * Strict rules selected include `E` (pycodestyle), `W` (pycodestyle warnings), `F` (pyflakes), `I` (isort), `N` (naming), `UP` (pyupgrade), `B` (bugbear), `S` (bandit), `ANN` (annotations), `D` (pydocstyle), `PT` (pytest-style), `RET` (return-style), `RSE` (raise-style), `RUF` (Ruff-specific), and `ERA` (eradicate commented code).
  * Line-length is strictly capped at **100 characters**.
* **Type Annotations**: Enforce strict type hints (`typing`) on all public function interfaces, classes, and APIs.
* **Docstrings**: Public functions, classes, and models must include descriptive, Google-style docstrings.

---

## 3. Frontend & Accessibility (WCAG 2.1 AA)
* **Semantic HTML**: Maintain clean HTML landmarks (`<header>`, `<main>`, `<aside>`, `<section>`, `<article>`).
* **Screen Reader Hygiene**: 
  * All inputs must have corresponding `<label for="...">` tags.
  * Every input that requires validation must have `aria-describedby` linked to its error container.
  * Decorative or non-standard characters (e.g. raw emojis) inside actionable elements (buttons, tabs) must be wrapped in `<span aria-hidden="true">` to prevent screen reader noise.
* **Responsive Styling**: Pure, fluid vanilla CSS with high contrast compatibility (`prefers-contrast: more`) and reduced motion styling (`prefers-reduced-motion: reduce`).

---

## 4. Verification & Testing Protocol
* **Pre-commit Automation**: Every commit must pass the `.pre-commit-config.yaml` check local suite (runs Ruff check, Ruff format, and file sanitisation).
* **Test Coverage**: Keep test coverage of `backend` above **95%**. Add corresponding tests for every new feature or bug fix in `backend/tests/`.
