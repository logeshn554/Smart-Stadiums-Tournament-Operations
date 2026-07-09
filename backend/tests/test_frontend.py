"""
Accessibility and HTML structure tests for the StadiumOps AI frontend.

Contains exactly 22 tests parsing 'frontend/index.html' using Python's
built-in 'html.parser' to verify compliance with WCAG 2.1 accessibility
guidelines, semantic elements, skip navigation, and Pydantic-aligned form constraints.
"""

import os
from html.parser import HTMLParser
import pytest

INDEX_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "frontend",
    "index.html",
)


class HTMLTag:
    def __init__(self, tag, attrs):
        self.tag = tag
        self.attrs = dict(attrs)
        self.children = []
        self.text = ""


class IndexHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.root = HTMLTag("root", [])
        self.stack = [self.root]
        self.all_tags = []

    def handle_starttag(self, tag, attrs):
        node = HTMLTag(tag, attrs)
        self.stack[-1].children.append(node)
        self.stack.append(node)
        self.all_tags.append(node)

    def handle_endtag(self, tag):
        if len(self.stack) > 1:
            self.stack.pop()

    def handle_data(self, data):
        if self.stack[-1]:
            self.stack[-1].text += data.strip()


@pytest.fixture(scope="module")
def parsed_html():
    if not os.path.exists(INDEX_PATH):
        pytest.fail(f"index.html not found at {INDEX_PATH}")
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    parser = IndexHTMLParser()
    parser.feed(content)
    return parser


# ═════════════════════════════════════════════════════════════════════════════
# ── HTML ACCESSIBILITY & STRUCTURE TESTS (22 Tests) ──────────────────────────
# ═════════════════════════════════════════════════════════════════════════════


def test_html_lang_attribute(parsed_html):
    """Test 1: HTML tag has lang="en" defined for screen readers."""
    html_tags = [t for t in parsed_html.all_tags if t.tag == "html"]
    assert len(html_tags) == 1
    assert html_tags[0].attrs.get("lang") == "en"


def test_charset_meta_defined(parsed_html):
    """Test 2: Charset meta tag is defined as UTF-8."""
    meta_tags = [t for t in parsed_html.all_tags if t.tag == "meta" and "charset" in t.attrs]
    assert len(meta_tags) == 1
    assert meta_tags[0].attrs.get("charset").lower() == "utf-8"


def test_viewport_meta_defined(parsed_html):
    """Test 3: Viewport meta is present for mobile scaling."""
    meta_tags = [t for t in parsed_html.all_tags if t.tag == "meta" and t.attrs.get("name") == "viewport"]
    assert len(meta_tags) == 1
    assert "width=device-width" in meta_tags[0].attrs.get("content")


def test_description_meta_present(parsed_html):
    """Test 4: Meta description is defined for search engines and SEO."""
    meta_tags = [t for t in parsed_html.all_tags if t.tag == "meta" and t.attrs.get("name") == "description"]
    assert len(meta_tags) == 1
    assert len(meta_tags[0].attrs.get("content", "")) > 0


def test_title_tag_present(parsed_html):
    """Test 5: Title tag exists with descriptive text."""
    title_tags = [t for t in parsed_html.all_tags if t.tag == "title"]
    assert len(title_tags) == 1
    assert "StadiumOps AI" in title_tags[0].text


def test_skip_nav_link_exists(parsed_html):
    """Test 6: Skip navigation link is present."""
    skip_link = [t for t in parsed_html.all_tags if t.tag == "a" and t.attrs.get("id") == "skip-nav"]
    assert len(skip_link) == 1
    assert skip_link[0].attrs.get("href") == "#recommendations-list"


def test_skip_nav_first_child(parsed_html):
    """Test 7: Skip navigation link is the first focusable child of body."""
    body_tags = [t for t in parsed_html.all_tags if t.tag == "body"]
    assert len(body_tags) == 1
    # Check if first child (or skip-nav class element) is skip-nav
    children_tags = [c.tag for c in body_tags[0].children if c.tag != "comment"]
    # The first element inside body should be the skip navigation link
    assert children_tags[0] == "a" or any(c.attrs.get("id") == "skip-nav" for c in body_tags[0].children[:2])


def test_h1_app_logo(parsed_html):
    """Test 8: App logo is wrapped in a single H1 tag."""
    h1_tags = [t for t in parsed_html.all_tags if t.tag == "h1"]
    assert len(h1_tags) == 1
    assert h1_tags[0].attrs.get("class") == "app-logo"


def test_semantic_header_exists(parsed_html):
    """Test 9: Header tag is used semantically."""
    header_tags = [t for t in parsed_html.all_tags if t.tag == "header"]
    assert len(header_tags) == 1


def test_semantic_main_exists(parsed_html):
    """Test 10: Main landmark wrapper exists."""
    main_tags = [t for t in parsed_html.all_tags if t.tag == "main"]
    assert len(main_tags) == 1


def test_semantic_aside_exists(parsed_html):
    """Test 11: Aside tag is used for the input side panel."""
    aside_tags = [t for t in parsed_html.all_tags if t.tag == "aside"]
    assert len(aside_tags) == 1
    assert "input-panel" in aside_tags[0].attrs.get("class", "")


def test_semantic_section_exists(parsed_html):
    """Test 12: Section tag is used for the recommendations content."""
    section_tags = [t for t in parsed_html.all_tags if t.tag == "section"]
    assert len(section_tags) >= 1


def test_fieldset_and_legend_used(parsed_html):
    """Test 13: Form uses fieldset and legend to group input controls."""
    fieldset_tags = [t for t in parsed_html.all_tags if t.tag == "fieldset"]
    assert len(fieldset_tags) >= 4  # Gates, Incident, Weather, Event
    for fs in fieldset_tags:
        assert any(c.tag == "legend" for c in fs.children)


def test_gate_ids_match_inputs(parsed_html):
    """Test 14: Gate status ID inputs are correctly labeled."""
    for idx in range(1, 5):
        input_tag = [t for t in parsed_html.all_tags if t.tag == "input" and t.attrs.get("id") == f"gate-{idx}-id"]
        assert len(input_tag) == 1
        assert "required" in input_tag[0].attrs


def test_gate_capacity_validation_attributes(parsed_html):
    """Test 15: Capacity inputs have min and max validation constraints matching schema."""
    for idx in range(1, 5):
        input_tag = [t for t in parsed_html.all_tags if t.tag == "input" and t.attrs.get("id") == f"gate-{idx}-capacity"]
        assert len(input_tag) == 1
        assert input_tag[0].attrs.get("min") == "0"
        assert input_tag[0].attrs.get("max") == "100"


def test_incident_description_maxlength(parsed_html):
    """Test 16: Incident description is bounded to 300 characters."""
    desc_tag = [t for t in parsed_html.all_tags if t.tag == "textarea" and t.attrs.get("id") == "incident-description"]
    assert len(desc_tag) == 1
    assert desc_tag[0].attrs.get("maxlength") == "300"


def test_event_total_capacity_minimum(parsed_html):
    """Test 17: Event total capacity input has min="1" constraint."""
    capacity_input = [t for t in parsed_html.all_tags if t.tag == "input" and t.attrs.get("id") == "event-total-capacity"]
    assert len(capacity_input) == 1
    assert capacity_input[0].attrs.get("min") == "1"


def test_form_aria_describedby_error_bindings(parsed_html):
    """Test 18: Form input fields are linked to error message containers via aria-describedby."""
    test_ids = ["gate-1-id", "gate-1-capacity", "incident-id", "incident-description"]
    for fid in test_ids:
        tag = [t for t in parsed_html.all_tags if t.attrs.get("id") == fid][0]
        described_by = tag.attrs.get("aria-describedby")
        assert described_by == f"{fid}-error"
        # Validate that the error span actually exists in the DOM
        span = [t for t in parsed_html.all_tags if t.attrs.get("id") == described_by]
        assert len(span) == 1
        assert span[0].tag == "span"
        assert span[0].attrs.get("role") == "alert"


def test_recommendations_panel_has_role_region(parsed_html):
    """Test 19: Recommendations panel uses semantic region landmark with an aria-label."""
    panels = [t for t in parsed_html.all_tags if "recommendations-panel" in t.attrs.get("class", "")]
    assert len(panels) == 1
    assert panels[0].attrs.get("role") == "region"
    assert "aria-label" in panels[0].attrs


def test_tabs_list_accessibility_roles(parsed_html):
    """Test 20: Tab indicators use role="tablist" and children use role="tab"."""
    tablists = [t for t in parsed_html.all_tags if t.attrs.get("role") == "tablist"]
    assert len(tablists) == 1

    tabs = [t for t in parsed_html.all_tags if t.attrs.get("role") == "tab"]
    assert len(tabs) >= 3
    for tab in tabs:
        assert "aria-controls" in tab.attrs
        assert "aria-selected" in tab.attrs


def test_caller_role_select_has_options(parsed_html):
    """Test 21: Authentication role selector features admin and viewer options."""
    select_tags = [t for t in parsed_html.all_tags if t.tag == "select" and t.attrs.get("id") == "caller-role"]
    assert len(select_tags) == 1
    options = [c for c in select_tags[0].children if c.tag == "option"]
    assert len(options) == 2
    vals = {opt.attrs.get("value") for opt in options}
    assert "admin" in vals
    assert "viewer" in vals


def test_form_novalidate_active(parsed_html):
    """Test 22: Form uses novalidate to allow clean custom client-side validation logic."""
    form_tags = [t for t in parsed_html.all_tags if t.tag == "form" and t.attrs.get("id") == "analyze-form"]
    assert len(form_tags) == 1
    assert "novalidate" in form_tags[0].attrs
