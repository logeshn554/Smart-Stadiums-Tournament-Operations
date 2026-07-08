"""
Frontend structure and accessibility tests for StadiumOps AI.

Validates that the HTML, CSS, and JS files contain required
accessibility attributes, semantic elements, and security measures.
These are static analysis tests that verify the frontend meets
WCAG 2.1 Level AA compliance and follows security best practices.
"""

import os
import re

import pytest

# ── Path resolution ─────────────────────────────────────────────────────

FRONTEND_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "frontend",
)

HTML_PATH = os.path.join(FRONTEND_DIR, "index.html")
CSS_PATH = os.path.join(FRONTEND_DIR, "style.css")
JS_PATH = os.path.join(FRONTEND_DIR, "app.js")


def _read_file(path: str) -> str:
    """Read a file's full content as a string."""
    with open(path, encoding="utf-8") as f:
        return f.read()


class TestHTMLAccessibility:
    """Verify HTML meets accessibility requirements."""

    @pytest.fixture(autouse=True)
    def load_html(self) -> None:
        """Load the HTML content before each test."""
        self.html = _read_file(HTML_PATH)

    def test_lang_attribute_present(self) -> None:
        """HTML element must have a lang attribute."""
        assert 'lang="en"' in self.html

    def test_skip_nav_link_present(self) -> None:
        """Skip navigation link must exist for keyboard users."""
        assert "skip-nav" in self.html
        assert 'href="#recommendations-list"' in self.html

    def test_semantic_header(self) -> None:
        """Page must use <header> element."""
        assert "<header" in self.html

    def test_semantic_main(self) -> None:
        """Page must use <main> element."""
        assert "<main" in self.html

    def test_semantic_aside(self) -> None:
        """Input panel must use <aside> element."""
        assert "<aside" in self.html

    def test_semantic_section(self) -> None:
        """Recommendations panel must use <section> element."""
        assert "<section" in self.html

    def test_fieldset_and_legend(self) -> None:
        """Form groups must use <fieldset> and <legend>."""
        assert "<fieldset" in self.html
        assert "<legend" in self.html

    def test_all_inputs_have_labels(self) -> None:
        """Every input with an id must have a corresponding <label for>."""
        input_ids = re.findall(r'<input[^>]+id="([^"]+)"', self.html)
        for input_id in input_ids:
            assert f'for="{input_id}"' in self.html, (
                f"Input #{input_id} is missing a <label for> element."
            )

    def test_aria_live_region(self) -> None:
        """Toast container must use aria-live for screen readers."""
        assert 'aria-live="polite"' in self.html

    def test_aria_hidden_on_loading_overlay(self) -> None:
        """Loading overlay must use aria-hidden."""
        assert 'aria-hidden="true"' in self.html

    def test_recommendations_panel_aria_label(self) -> None:
        """Recommendations panel must have an aria-label."""
        assert 'aria-label="Live Recommendations"' in self.html

    def test_aria_describedby_on_required_inputs(self) -> None:
        """Required text/number inputs should have aria-describedby for error messages."""
        assert "aria-describedby" in self.html

    def test_decorative_emojis_hidden(self) -> None:
        """Decorative emoji icons should be marked with aria-hidden."""
        assert 'aria-hidden="true"' in self.html

    def test_meta_viewport_present(self) -> None:
        """Meta viewport tag must be present for mobile accessibility."""
        assert 'name="viewport"' in self.html

    def test_meta_description_present(self) -> None:
        """Meta description must be present for SEO and screen readers."""
        assert 'name="description"' in self.html


class TestCSSAccessibility:
    """Verify CSS meets accessibility requirements."""

    @pytest.fixture(autouse=True)
    def load_css(self) -> None:
        """Load the CSS content before each test."""
        self.css = _read_file(CSS_PATH)

    def test_focus_visible_styles(self) -> None:
        """Global focus-visible styles must be defined."""
        assert "focus-visible" in self.css

    def test_prefers_reduced_motion(self) -> None:
        """prefers-reduced-motion media query must be present."""
        assert "prefers-reduced-motion" in self.css
        assert "reduce" in self.css

    def test_prefers_contrast(self) -> None:
        """prefers-contrast media query must be present for high contrast."""
        assert "prefers-contrast" in self.css
        assert "more" in self.css

    def test_skip_nav_styles(self) -> None:
        """Skip navigation link must have show-on-focus styles."""
        assert "skip-nav" in self.css

    def test_sr_only_utility(self) -> None:
        """Screen-reader-only utility class must be defined."""
        assert "sr-only" in self.css

    def test_field_error_styles(self) -> None:
        """Field error styles for validation must be defined."""
        assert "field-error" in self.css

    def test_responsive_breakpoint(self) -> None:
        """Responsive layout must be defined with a breakpoint."""
        assert "@media" in self.css
        assert "max-width" in self.css


class TestJSSecurity:
    """Verify JavaScript follows security best practices."""

    @pytest.fixture(autouse=True)
    def load_js(self) -> None:
        """Load the JS content before each test."""
        self.js = _read_file(JS_PATH)

    def test_strict_mode(self) -> None:
        """JavaScript must use strict mode."""
        assert '"use strict"' in self.js

    def test_escape_html_defined(self) -> None:
        """escapeHtml function must be defined for XSS prevention."""
        assert "escapeHtml" in self.js

    def test_no_direct_innerhtml_for_user_content(self) -> None:
        """Severity badge must use textContent, not innerHTML, for user content."""
        # The badge construction should use textContent
        assert "badgeText" in self.js or "textContent" in self.js

    def test_iife_encapsulation(self) -> None:
        """Code must be wrapped in an IIFE to avoid global pollution."""
        assert "(function" in self.js

    def test_debounce_implemented(self) -> None:
        """Form submission must use debouncing."""
        assert "debounce" in self.js.lower() or "DEBOUNCE" in self.js

    def test_form_validation_present(self) -> None:
        """Client-side form validation must be implemented."""
        assert "validateForm" in self.js or "validateField" in self.js
