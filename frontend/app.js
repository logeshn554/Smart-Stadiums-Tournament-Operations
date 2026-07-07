/**
 * StadiumOps AI — Control Room Dashboard Application Logic.
 *
 * Handles form submission, API communication, recommendation rendering,
 * and auto-refresh functionality.  No build tools or npm required.
 */

(function () {
    "use strict";

    // ── Configuration ────────────────────────────────────────────────────

    const API_BASE_URL = "http://127.0.0.1:8000";
    const AUTO_REFRESH_INTERVAL_MS = 30000;

    // ── DOM References ───────────────────────────────────────────────────

    const analyzeForm = document.getElementById("analyze-form");
    const submitButton = document.getElementById("submit-button");
    const recommendationsList = document.getElementById("recommendations-list");
    const recommendationCount = document.getElementById("recommendation-count");
    const emptyState = document.getElementById("empty-state");
    const loadingOverlay = document.getElementById("loading-overlay");
    const toastContainer = document.getElementById("toast-container");
    const phaseBadgeText = document.getElementById("phase-badge-text");
    const autoRefreshIndicator = document.getElementById("auto-refresh-indicator");

    // ── State ────────────────────────────────────────────────────────────

    let lastPayload = null;
    let autoRefreshTimer = null;

    // ── Severity Configuration ───────────────────────────────────────────

    const SEVERITY_CONFIG = {
        Critical: { icon: "🔴", className: "critical", ariaRole: "alert" },
        High:     { icon: "🟠", className: "high",     ariaRole: "alert" },
        Medium:   { icon: "🟡", className: "medium",   ariaRole: null },
        Low:      { icon: "🟢", className: "low",      ariaRole: null },
    };

    // ── Utility Functions ────────────────────────────────────────────────

    /**
     * Show a toast notification.
     * @param {string} message - The message to display.
     * @param {"success"|"error"} type - Toast type.
     */
    function showToast(message, type) {
        var toast = document.createElement("div");
        toast.className = "toast " + type;
        toast.textContent = message;
        toastContainer.appendChild(toast);
        setTimeout(function () {
            toast.style.opacity = "0";
            toast.style.transform = "translateY(16px)";
            toast.style.transition = "opacity 0.3s, transform 0.3s";
            setTimeout(function () { toast.remove(); }, 300);
        }, 4000);
    }

    /**
     * Toggle the loading overlay.
     * @param {boolean} active - Whether to show the overlay.
     */
    function setLoading(active) {
        if (active) {
            loadingOverlay.classList.add("active");
            loadingOverlay.setAttribute("aria-hidden", "false");
            submitButton.disabled = true;
        } else {
            loadingOverlay.classList.remove("active");
            loadingOverlay.setAttribute("aria-hidden", "true");
            submitButton.disabled = false;
        }
    }

    // ── Form Data Extraction ─────────────────────────────────────────────

    /**
     * Read a single gate's data from the form.
     * @param {number} index - Gate number (1-based).
     * @returns {Object} Gate status object.
     */
    function readGate(index) {
        return {
            gate_id:          document.getElementById("gate-" + index + "-id").value.trim(),
            capacity_percent: parseFloat(document.getElementById("gate-" + index + "-capacity").value) || 0,
            entry_rate:       parseInt(document.getElementById("gate-" + index + "-rate").value, 10) || 0,
            wait_time_seconds: parseInt(document.getElementById("gate-" + index + "-wait").value, 10) || 0,
        };
    }

    /**
     * Build the full analyze request payload from the form.
     * @returns {Object} Payload matching the AnalyzeRequest schema.
     */
    function buildPayload() {
        var selectedPhase = document.getElementById("event-phase").value;
        phaseBadgeText.textContent = selectedPhase.replace("_", " ").toUpperCase();

        return {
            gates: [readGate(1), readGate(2), readGate(3), readGate(4)],
            incident: {
                incident_id:  document.getElementById("incident-id").value.trim(),
                zone:         document.getElementById("incident-zone").value.trim(),
                type:         document.getElementById("incident-type").value,
                description:  document.getElementById("incident-description").value.trim(),
                reporter_role: document.getElementById("incident-reporter").value.trim(),
            },
            weather: {
                temperature_celsius: parseFloat(document.getElementById("weather-temp").value) || 0,
                heat_index:          parseFloat(document.getElementById("weather-heat-index").value) || 0,
                lightning_detected:  document.getElementById("weather-lightning").value === "true",
                lightning_radius_km: parseFloat(document.getElementById("weather-lightning-radius").value) || 0,
            },
            event_context: {
                phase:                      selectedPhase,
                total_capacity:             parseInt(document.getElementById("event-total-capacity").value, 10) || 1,
                occupied_seats:             parseInt(document.getElementById("event-occupied").value, 10) || 0,
                accessible_seats_available: parseInt(document.getElementById("event-accessible").value, 10) || 0,
                concession_queue_avg_minutes: parseFloat(document.getElementById("event-concession").value) || 0,
            },
            role: document.getElementById("caller-role").value,
        };
    }

    // ── Recommendation Rendering ─────────────────────────────────────────

    /**
     * Create a single recommendation card element.
     * @param {Object} rec - Recommendation object from the API.
     * @param {number} index - Card index for unique IDs.
     * @returns {HTMLElement} The card DOM element.
     */
    function createRecommendationCard(rec, index) {
        var config = SEVERITY_CONFIG[rec.severity] || SEVERITY_CONFIG.Low;

        var card = document.createElement("article");
        card.className = "recommendation-card severity-" + config.className;
        if (config.ariaRole) {
            card.setAttribute("role", config.ariaRole);
        }

        // Header
        var header = document.createElement("div");
        header.className = "card-header";

        var badge = document.createElement("span");
        badge.className = "severity-badge " + config.className;
        badge.innerHTML = '<span class="severity-icon">' + config.icon + '</span> ' + rec.severity;

        var meta = document.createElement("div");
        meta.className = "card-meta";
        meta.innerHTML =
            '<span class="meta-item">📍 ' + escapeHtml(rec.affected_zone) + '</span>' +
            '<span class="meta-item">🎯 ' + escapeHtml(rec.confidence) + '</span>' +
            '<span class="meta-item">⚙️ ' + escapeHtml(rec.rule_id) + '</span>';

        header.appendChild(badge);
        header.appendChild(meta);

        // Action text
        var actionDiv = document.createElement("div");
        actionDiv.className = "card-action";
        actionDiv.textContent = rec.action;

        // Reason toggle
        var reasonToggleId = "reason-toggle-" + index;
        var reasonContentId = "reason-content-" + index;

        var reasonToggle = document.createElement("button");
        reasonToggle.type = "button";
        reasonToggle.className = "reason-toggle";
        reasonToggle.id = reasonToggleId;
        reasonToggle.setAttribute("aria-expanded", "false");
        reasonToggle.setAttribute("aria-controls", reasonContentId);
        reasonToggle.innerHTML = "▸ Show Reason";

        var reasonContent = document.createElement("div");
        reasonContent.className = "reason-content";
        reasonContent.id = reasonContentId;
        reasonContent.textContent = rec.reason;

        reasonToggle.addEventListener("click", function () {
            var isExpanded = reasonContent.classList.toggle("expanded");
            reasonToggle.setAttribute("aria-expanded", isExpanded ? "true" : "false");
            reasonToggle.innerHTML = isExpanded ? "▾ Hide Reason" : "▸ Show Reason";
        });

        card.appendChild(header);
        card.appendChild(actionDiv);
        card.appendChild(reasonToggle);
        card.appendChild(reasonContent);

        return card;
    }

    /**
     * Escape HTML entities to prevent XSS in rendered content.
     * @param {string} text - Raw text.
     * @returns {string} Escaped text.
     */
    function escapeHtml(text) {
        var div = document.createElement("div");
        div.appendChild(document.createTextNode(text));
        return div.innerHTML;
    }

    /**
     * Render the full list of recommendations into the panel.
     * @param {Array<Object>} recommendations - Sorted recommendation list.
     */
    function renderRecommendations(recommendations) {
        recommendationsList.innerHTML = "";

        if (!recommendations || recommendations.length === 0) {
            recommendationsList.appendChild(emptyState);
            recommendationCount.textContent = "0 results";
            return;
        }

        recommendationCount.textContent = recommendations.length + " result" + (recommendations.length !== 1 ? "s" : "");

        recommendations.forEach(function (rec, idx) {
            var card = createRecommendationCard(rec, idx);
            recommendationsList.appendChild(card);
        });
    }

    // ── API Communication ────────────────────────────────────────────────

    /**
     * Send the payload to the API and render the response.
     * @param {Object} payload - The analyze request payload.
     */
    function submitAnalysis(payload) {
        setLoading(true);

        fetch(API_BASE_URL + "/api/analyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        })
        .then(function (response) {
            if (response.status === 403) {
                throw new Error("Access denied: viewers cannot submit Critical-level incidents.");
            }
            if (response.status === 422) {
                return response.json().then(function (data) {
                    throw new Error("Validation error: " + JSON.stringify(data.detail));
                });
            }
            if (!response.ok) {
                throw new Error("Server error: " + response.status);
            }
            return response.json();
        })
        .then(function (data) {
            renderRecommendations(data.recommendations);
            showToast("Analysis complete — " + data.recommendations.length + " recommendations generated.", "success");
            lastPayload = payload;
        })
        .catch(function (error) {
            showToast(error.message, "error");
            console.error("[StadiumOps AI]", error);
        })
        .finally(function () {
            setLoading(false);
        });
    }

    // ── Event Listeners ──────────────────────────────────────────────────

    analyzeForm.addEventListener("submit", function (event) {
        event.preventDefault();
        var payload = buildPayload();
        submitAnalysis(payload);
    });

    // ── Auto-Refresh ─────────────────────────────────────────────────────

    /**
     * Start auto-refresh timer that re-submits the last payload every 30s.
     */
    function startAutoRefresh() {
        if (autoRefreshTimer) {
            clearInterval(autoRefreshTimer);
        }

        autoRefreshTimer = setInterval(function () {
            if (lastPayload) {
                autoRefreshIndicator.classList.add("active");
                submitAnalysis(lastPayload);
                setTimeout(function () {
                    autoRefreshIndicator.classList.remove("active");
                }, 2000);
            }
        }, AUTO_REFRESH_INTERVAL_MS);
    }

    // ── Update phase badge when phase selector changes ───────────────────

    document.getElementById("event-phase").addEventListener("change", function () {
        phaseBadgeText.textContent = this.value.replace("_", " ").toUpperCase();
    });

    // ── Initialise ───────────────────────────────────────────────────────

    startAutoRefresh();

})();
