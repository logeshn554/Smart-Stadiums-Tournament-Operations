/**
 * StadiumOps AI — Control Room Dashboard Application Logic.
 *
 * Handles form submission, API communication, recommendation rendering,
 * client-side validation, auto-refresh with change detection, and
 * WebSocket real-time push.  No build tools or npm required.
 */

(function () {
    "use strict";

    // ── Configuration ────────────────────────────────────────────────────

    var API_BASE_URL = (window.location.hostname === "localhost" || 
                        window.location.hostname === "127.0.0.1" || 
                        window.location.protocol === "file:") 
                        ? "http://127.0.0.1:8000" 
                        : "https://smart-stadiums-tournament-operations-xz6g.onrender.com";
    var AUTO_REFRESH_INTERVAL_MS = 30000;
    var DEBOUNCE_MS = 300;
    var DATA_MODE = "server";  // "server" or "local"
    var SEED_JSON_URL = "../data/seed.json";

    // ── DOM References ───────────────────────────────────────────────────

    var analyzeForm = document.getElementById("analyze-form");
    var submitButton = document.getElementById("submit-button");
    var recommendationsList = document.getElementById("recommendations-list");
    var recommendationCount = document.getElementById("recommendation-count");
    var emptyState = document.getElementById("empty-state");
    var loadingOverlay = document.getElementById("loading-overlay");
    var toastContainer = document.getElementById("toast-container");
    var phaseBadgeText = document.getElementById("phase-badge-text");
    var autoRefreshIndicator = document.getElementById("auto-refresh-indicator");
    var fcmAlertsBtn = document.getElementById("fcm-alerts-btn");

    // ── State ────────────────────────────────────────────────────────────

    var lastPayload = null;
    var lastPayloadHash = null;
    var autoRefreshTimer = null;
    var debounceTimer = null;
    var lastRenderedRecs = null;
    var chatHistory = [];
    var fcmInitialized = false;
    var fcmToken = null;

    // ── Severity Configuration ───────────────────────────────────────────
    // Text labels used instead of emoji-only indicators for screen reader
    // compatibility (emojis may not render consistently across assistive tech).

    var SEVERITY_CONFIG = {
        Critical: { icon: "CRT", className: "critical", label: "Critical",  ariaRole: "alert" },
        High:     { icon: "HGH", className: "high",     label: "High",     ariaRole: "alert" },
        Medium:   { icon: "MED", className: "medium",   label: "Medium",   ariaRole: null },
        Low:      { icon: "LOW", className: "low",       label: "Low",      ariaRole: null },
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
        toast.setAttribute("role", "status");
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

    /**
     * Compute a simple hash string for a payload to enable change detection.
     * @param {Object} payload - The payload to hash.
     * @returns {string} A hash string.
     */
    function hashPayload(payload) {
        return JSON.stringify(payload);
    }

    // ── Client-Side Form Validation ──────────────────────────────────────

    /**
     * Validate a single field and show/hide its error message.
     * @param {HTMLElement} field - The input/textarea element.
     * @param {string} errorId - The ID of the error span.
     * @param {string} message - The error message if invalid.
     * @returns {boolean} True if valid.
     */
    function validateField(field, errorId, message) {
        var errorEl = document.getElementById(errorId);
        if (!errorEl) { return true; }

        if (!field.value || field.value.trim() === "") {
            field.classList.add("invalid");
            errorEl.textContent = message;
            errorEl.classList.add("visible");
            return false;
        }

        // Range validation for number fields
        if (field.type === "number") {
            var val = parseFloat(field.value);
            var min = field.min !== "" ? parseFloat(field.min) : -Infinity;
            var max = field.max !== "" ? parseFloat(field.max) : Infinity;
            if (isNaN(val) || val < min || val > max) {
                field.classList.add("invalid");
                errorEl.textContent = "Value must be between " + min + " and " + max + ".";
                errorEl.classList.add("visible");
                return false;
            }
        }

        field.classList.remove("invalid");
        errorEl.textContent = "";
        errorEl.classList.remove("visible");
        return true;
    }

    /**
     * Validate all form fields and show error messages.
     * @returns {boolean} True if all fields are valid.
     */
    function validateForm() {
        var isValid = true;
        var validations = [
            ["gate-1-id",     "gate-1-id-error",       "Gate ID is required."],
            ["gate-1-capacity","gate-1-capacity-error", "Capacity is required."],
            ["gate-1-rate",   "gate-1-rate-error",      "Entry rate is required."],
            ["gate-1-wait",   "gate-1-wait-error",      "Wait time is required."],
            ["gate-2-id",     "gate-2-id-error",        "Gate ID is required."],
            ["gate-2-capacity","gate-2-capacity-error",  "Capacity is required."],
            ["gate-2-rate",   "gate-2-rate-error",       "Entry rate is required."],
            ["gate-2-wait",   "gate-2-wait-error",       "Wait time is required."],
            ["gate-3-id",     "gate-3-id-error",         "Gate ID is required."],
            ["gate-3-capacity","gate-3-capacity-error",   "Capacity is required."],
            ["gate-3-rate",   "gate-3-rate-error",        "Entry rate is required."],
            ["gate-3-wait",   "gate-3-wait-error",        "Wait time is required."],
            ["gate-4-id",     "gate-4-id-error",          "Gate ID is required."],
            ["gate-4-capacity","gate-4-capacity-error",    "Capacity is required."],
            ["gate-4-rate",   "gate-4-rate-error",         "Entry rate is required."],
            ["gate-4-wait",   "gate-4-wait-error",         "Wait time is required."],
            ["incident-id",   "incident-id-error",         "Incident ID is required."],
            ["incident-zone", "incident-zone-error",       "Zone is required."],
            ["incident-description","incident-description-error","Description is required."],
            ["incident-reporter","incident-reporter-error","Reporter role is required."],
            ["event-total-capacity","event-total-capacity-error","Total capacity is required."],
        ];

        for (var i = 0; i < validations.length; i++) {
            var field = document.getElementById(validations[i][0]);
            if (field && !validateField(field, validations[i][1], validations[i][2])) {
                isValid = false;
            }
        }

        return isValid;
    }

    /**
     * Clear all validation errors.
     */
    function clearValidationErrors() {
        var errorEls = document.querySelectorAll(".field-error");
        for (var i = 0; i < errorEls.length; i++) {
            errorEls[i].textContent = "";
            errorEls[i].classList.remove("visible");
        }
        var invalidEls = document.querySelectorAll(".invalid");
        for (var j = 0; j < invalidEls.length; j++) {
            invalidEls[j].classList.remove("invalid");
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
        // Use split+join for broad compatibility instead of replaceAll
        phaseBadgeText.textContent = selectedPhase.split("_").join(" ").toUpperCase();

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
     * Uses textContent exclusively (no innerHTML) to prevent XSS.
     * @param {Object} rec - Recommendation object from the API.
     * @param {number} index - Card index for unique IDs.
     * @returns {HTMLElement} The card DOM element.
     */
    function createRecommendationCard(rec, index) {
        var config = SEVERITY_CONFIG[rec.severity] || SEVERITY_CONFIG.Low;

        var card = document.createElement("article");
        card.className = "recommendation-card severity-" + config.className;
        card.setAttribute("data-rec-id", rec.rule_id + "-" + rec.affected_zone + "-" + index);
        if (config.ariaRole) {
            card.setAttribute("role", config.ariaRole);
        }

        // Header
        var header = document.createElement("div");
        header.className = "card-header";

        var badge = document.createElement("span");
        badge.className = "severity-badge " + config.className;
        badge.setAttribute("aria-label", config.label + " severity");

        var badgeIcon = document.createElement("span");
        badgeIcon.className = "severity-icon";
        badgeIcon.textContent = config.icon;
        badgeIcon.setAttribute("aria-hidden", "true");

        var badgeText = document.createTextNode(" " + rec.severity);
        badge.appendChild(badgeIcon);
        badge.appendChild(badgeText);

        var meta = document.createElement("div");
        meta.className = "card-meta";

        var metaZone = document.createElement("span");
        metaZone.className = "meta-item";
        metaZone.setAttribute("aria-label", "Affected zone: " + rec.affected_zone);
        metaZone.textContent = "Zone: " + rec.affected_zone;

        var metaConf = document.createElement("span");
        metaConf.className = "meta-item";
        metaConf.setAttribute("aria-label", "Confidence: " + rec.confidence);
        metaConf.textContent = "Conf: " + rec.confidence;

        var metaRule = document.createElement("span");
        metaRule.className = "meta-item";
        metaRule.setAttribute("aria-label", "Rule: " + rec.rule_id);
        metaRule.textContent = "Rule: " + rec.rule_id;

        meta.appendChild(metaZone);
        meta.appendChild(metaConf);
        meta.appendChild(metaRule);

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
        reasonToggle.textContent = "\u25b8 Show Reason";

        var reasonContent = document.createElement("div");
        reasonContent.className = "reason-content";
        reasonContent.id = reasonContentId;
        reasonContent.textContent = rec.reason;

        reasonToggle.addEventListener("click", function () {
            var isExpanded = reasonContent.classList.toggle("expanded");
            reasonToggle.setAttribute("aria-expanded", isExpanded ? "true" : "false");
            reasonToggle.textContent = isExpanded ? "\u25be Hide Reason" : "\u25b8 Show Reason";
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
     * Uses diff-based rendering: only updates if the data has changed.
     * @param {Array<Object>} recommendations - Sorted recommendation list.
     */
    function renderRecommendations(recommendations) {
        if (!recommendations || recommendations.length === 0) {
            if (lastRenderedRecs !== null && lastRenderedRecs.length !== 0) {
                recommendationsList.innerHTML = "";
                recommendationsList.appendChild(emptyState);
            }
            recommendationCount.textContent = "0 results";
            lastRenderedRecs = [];
            return;
        }

        // Diff check: skip re-render if data hasn't changed
        var newHash = JSON.stringify(recommendations);
        if (lastRenderedRecs !== null && JSON.stringify(lastRenderedRecs) === newHash) {
            return;
        }

        recommendationsList.innerHTML = "";

        recommendationCount.textContent = recommendations.length + " result" + (recommendations.length !== 1 ? "s" : "");

        recommendations.forEach(function (rec, idx) {
            var card = createRecommendationCard(rec, idx);
            recommendationsList.appendChild(card);
        });

        lastRenderedRecs = recommendations;
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
            lastPayloadHash = hashPayload(payload);

            // Trigger the GenAI playbook generation in sync
            fetchPlaybook(payload);
        })
        .catch(function (error) {
            showToast(error.message, "error");
            console.error("[StadiumOps AI]", error);
        })
        .finally(function () {
            setLoading(false);
        });
    }

    /**
     * Load seed.json and render it as mock recommendations (Local File mode).
     * Bypasses the backend entirely for offline/demo scenarios.
     * @param {Object} payload - The form-built payload (used for toast only).
     */
    function submitLocalAnalysis(payload) {
        setLoading(true);
        fetch(SEED_JSON_URL)
        .then(function (response) {
            if (!response.ok) {
                throw new Error("Could not load seed.json (status " + response.status + ")");
            }
            return response.json();
        })
        .then(function (seedData) {
            // Build mock recommendations from seed data
            var mockRecs = [
                {
                    rule_id: "gate_load_balance",
                    severity: "High",
                    action: "Redirect flow from overloaded gates to underloaded gates.",
                    reason: "Gate imbalance detected in seed data — some gates above 80% while others below 40%.",
                    affected_zone: seedData.gates ? seedData.gates[0].gate_id : "N/A",
                    confidence: "Likely"
                },
                {
                    rule_id: "triage_incident",
                    severity: seedData.incident && seedData.incident.type === "fire_smoke" ? "Critical" : "High",
                    action: "Dispatch " + (seedData.incident ? seedData.incident.type : "unknown") + " response team to zone " + (seedData.incident ? seedData.incident.zone : "N/A") + ".",
                    reason: seedData.incident ? seedData.incident.description : "Incident reported.",
                    affected_zone: seedData.incident ? seedData.incident.zone : "N/A",
                    confidence: "Confirmed"
                },
                {
                    rule_id: "weather_action",
                    severity: seedData.weather && seedData.weather.heat_index >= 40 ? "High" : "Low",
                    action: "Activate hydration protocol — heat index at " + (seedData.weather ? seedData.weather.heat_index : "N/A") + "°C.",
                    reason: "Heat index exceeds safety threshold.",
                    affected_zone: "Stadium-wide",
                    confidence: "Likely"
                }
            ];
            renderRecommendations(mockRecs);
            showToast("Local file mode — " + mockRecs.length + " mock recommendations generated from seed.json.", "success");
            lastPayload = payload;
            lastPayloadHash = hashPayload(payload);
        })
        .catch(function (error) {
            showToast("Local mode error: " + error.message, "error");
            console.error("[StadiumOps AI Local]", error);
        })
        .finally(function () {
            setLoading(false);
        });
    }

    // ── Event Listeners ──────────────────────────────────────────────────

    analyzeForm.addEventListener("submit", function (event) {
        event.preventDefault();

        // Clear previous errors
        clearValidationErrors();

        // Client-side validation
        if (!validateForm()) {
            showToast("Please fix the highlighted fields before submitting.", "error");
            return;
        }

        // Debounce: prevent rapid duplicate submissions
        if (debounceTimer) {
            clearTimeout(debounceTimer);
        }
        debounceTimer = setTimeout(function () {
            var payload = buildPayload();
            if (DATA_MODE === "local") {
                submitLocalAnalysis(payload);
            } else {
                submitAnalysis(payload);
            }
            debounceTimer = null;
        }, DEBOUNCE_MS);
    });

    // Clear validation errors on input
    analyzeForm.addEventListener("input", function (event) {
        var field = event.target;
        if (field.classList.contains("invalid")) {
            field.classList.remove("invalid");
            var errorId = field.id + "-error";
            var errorEl = document.getElementById(errorId);
            if (errorEl) {
                errorEl.textContent = "";
                errorEl.classList.remove("visible");
            }
        }
    });

    // ── Auto-Refresh with Change Detection ──────────────────────────────

    /**
     * Start auto-refresh timer that re-submits the last payload every 30s.
     * Skips re-submission if the payload hasn't changed since last send.
     */
    function startAutoRefresh() {
        if (autoRefreshTimer) {
            clearInterval(autoRefreshTimer);
        }

        autoRefreshTimer = setInterval(function () {
            if (lastPayload) {
                // Build current payload and check if it changed
                var currentPayload = buildPayload();
                var currentHash = hashPayload(currentPayload);

                if (currentHash === lastPayloadHash) {
                    // Payload unchanged — still refresh for updated server state
                    autoRefreshIndicator.classList.add("active");
                    submitAnalysis(lastPayload);
                    setTimeout(function () {
                        autoRefreshIndicator.classList.remove("active");
                    }, 2000);
                } else {
                    // Payload changed — submit with new data
                    autoRefreshIndicator.classList.add("active");
                    submitAnalysis(currentPayload);
                    setTimeout(function () {
                        autoRefreshIndicator.classList.remove("active");
                    }, 2000);
                }
            }
        }, AUTO_REFRESH_INTERVAL_MS);
    }

    // ── GenAI Feature Support Functions ──────────────────────────────────

    /**
     * Fetch situation playbook and multilingual announcements from the GenAI backend.
     * @param {Object} payload - The stadium data payload.
     */
    function fetchPlaybook(payload) {
        var headers = { "Content-Type": "application/json" };

        var playbookEmptyState = document.getElementById("playbook-empty-state");
        var playbookContent = document.getElementById("playbook-content");
        var generateBtn = document.getElementById("generate-playbook-btn");

        generateBtn.disabled = true;
        generateBtn.textContent = "⚡ Synthesizing...";

        fetch(API_BASE_URL + "/api/genai/playbook", {
            method: "POST",
            headers: headers,
            body: JSON.stringify(payload)
        })
        .then(function (response) {
            if (!response.ok) {
                throw new Error("GenAI Playbook synthesis failed: status " + response.status);
            }
            return response.json();
        })
        .then(function (data) {
            document.getElementById("playbook-summary").textContent = data.summary;

            var stepsList = document.getElementById("playbook-steps");
            stepsList.innerHTML = "";
            if (data.steps && data.steps.length > 0) {
                data.steps.forEach(function (step) {
                    var li = document.createElement("li");
                    li.textContent = step;
                    stepsList.appendChild(li);
                });
            }

            document.getElementById("announcement-en").textContent = data.announcements.en || "";
            document.getElementById("announcement-es").textContent = data.announcements.es || "";
            document.getElementById("announcement-fr").textContent = data.announcements.fr || "";

            playbookEmptyState.classList.add("hidden");
            playbookContent.classList.remove("hidden");
        })
        .catch(function (error) {
            showToast(error.message, "error");
            console.error("[StadiumOps AI Playbook]", error);
        })
        .finally(function () {
            generateBtn.disabled = false;
            generateBtn.textContent = "⚡ Generate AI Playbook";
        });
    }

    // ── Tab Management ───────────────────────────────────────────────────

    var tabIds = ["rules", "playbook", "chat"];

    function switchTab(tabId) {
        tabIds.forEach(function (tid) {
            var btn = document.getElementById("tab-" + tid);
            var content = document.getElementById("panel-" + tid);
            if (btn) {
                btn.classList.remove("active");
                btn.setAttribute("aria-selected", "false");
                btn.setAttribute("tabindex", "-1");
            }
            if (content) {
                content.classList.remove("active");
            }
        });
        var activeBtn = document.getElementById("tab-" + tabId);
        if (activeBtn) {
            activeBtn.classList.add("active");
            activeBtn.setAttribute("aria-selected", "true");
            activeBtn.setAttribute("tabindex", "0");
        }
        var activeContent = document.getElementById("panel-" + tabId);
        if (activeContent) {
            activeContent.classList.add("active");
        }
    }

    function focusAndActivateTab(index) {
        var tabId = tabIds[index];
        switchTab(tabId);
        var button = document.getElementById("tab-" + tabId);
        if (button) {
            button.focus();
        }
    }

    tabIds.forEach(function (tabId, index) {
        var button = document.getElementById("tab-" + tabId);
        if (button) {
            button.addEventListener("click", function () {
                switchTab(tabId);
            });

            // Keyboard navigation (WAI-ARIA compliance)
            button.addEventListener("keydown", function (e) {
                var nextIndex;
                if (e.key === "ArrowRight" || e.key === "ArrowDown") {
                    nextIndex = (index + 1) % tabIds.length;
                    focusAndActivateTab(nextIndex);
                    e.preventDefault();
                } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
                    nextIndex = (index - 1 + tabIds.length) % tabIds.length;
                    focusAndActivateTab(nextIndex);
                    e.preventDefault();
                } else if (e.key === "Home") {
                    focusAndActivateTab(0);
                    e.preventDefault();
                } else if (e.key === "End") {
                    focusAndActivateTab(tabIds.length - 1);
                    e.preventDefault();
                }
            });
        }
    });

    // Initialize tabindexes on load
    switchTab("rules");



    // ── Playbook Manual Button ───────────────────────────────────────────

    var generatePlaybookBtn = document.getElementById("generate-playbook-btn");
    if (generatePlaybookBtn) {
        generatePlaybookBtn.addEventListener("click", function () {
            clearValidationErrors();
            if (!validateForm()) {
                showToast("Please fix validation errors before generating playbook.", "error");
                return;
            }
            fetchPlaybook(buildPayload());
        });
    }

    // ── Chat Assistant Form Submission ───────────────────────────────────

    var chatForm = document.getElementById("chat-form");
    var chatInput = document.getElementById("chat-input");
    var chatMessages = document.getElementById("chat-messages");

    if (chatForm && chatInput && chatMessages) {
        chatForm.addEventListener("submit", function (e) {
            e.preventDefault();
            var message = chatInput.value.trim();
            if (!message) { return; }

            // 1. Render user message
            var userMsg = document.createElement("div");
            userMsg.className = "chat-message user";
            userMsg.textContent = message;
            chatMessages.appendChild(userMsg);
            chatMessages.scrollTop = chatMessages.scrollHeight;

            chatInput.value = "";

            // 2. Build backend request payload
            var headers = { "Content-Type": "application/json" };

            var currentPayload = buildPayload();
            var chatPayload = {
                message: message,
                history: chatHistory,
                gates: currentPayload.gates,
                incident: currentPayload.incident,
                weather: currentPayload.weather,
                event_context: currentPayload.event_context
            };

            // Render temporary placeholder
            var loaderMsg = document.createElement("div");
            loaderMsg.className = "chat-message assistant";
            loaderMsg.textContent = "...";
            chatMessages.appendChild(loaderMsg);
            chatMessages.scrollTop = chatMessages.scrollHeight;

            var submitBtn = document.getElementById("chat-submit-btn");
            if (submitBtn) { submitBtn.disabled = true; }

            fetch(API_BASE_URL + "/api/genai/chat", {
                method: "POST",
                headers: headers,
                body: JSON.stringify(chatPayload)
            })
            .then(function (response) {
                if (response.status === 429) {
                    throw new Error("Chat rate limit exceeded. Please wait a minute.");
                }
                if (!response.ok) {
                    throw new Error("Chat request failed: status " + response.status);
                }
                return response.json();
            })
            .then(function (data) {
                loaderMsg.remove();
                var replyMsg = document.createElement("div");
                replyMsg.className = "chat-message assistant";
                replyMsg.textContent = data.reply;
                chatMessages.appendChild(replyMsg);
                chatMessages.scrollTop = chatMessages.scrollHeight;

                // Update local conversational history
                chatHistory.push({ role: "user", content: message });
                chatHistory.push({ role: "assistant", content: data.reply });

                if (chatHistory.length > 10) {
                    chatHistory.shift();
                    chatHistory.shift();
                }
            })
            .catch(function (error) {
                loaderMsg.remove();
                var errMsg = document.createElement("div");
                errMsg.className = "chat-message assistant";
                errMsg.style.borderColor = "var(--color-critical)";
                errMsg.textContent = "Error: " + error.message;
                chatMessages.appendChild(errMsg);
                chatMessages.scrollTop = chatMessages.scrollHeight;
            })
            .finally(function () {
                if (submitBtn) { submitBtn.disabled = false; }
            });
        });
    }

    // ── Data Mode Toggle ─────────────────────────────────────────────────

    var dataModeSelect = document.getElementById("data-mode-select");
    if (dataModeSelect) {
        dataModeSelect.addEventListener("change", function () {
            DATA_MODE = this.value;
            showToast("Switched to " + (DATA_MODE === "server" ? "Server" : "Local File") + " mode.", "success");
        });
    }

    // ── Update phase badge when phase selector changes ───────────────────

    document.getElementById("event-phase").addEventListener("change", function () {
        phaseBadgeText.textContent = this.value.split("_").join(" ").toUpperCase();
    });



    // ── Firebase Cloud Messaging (FCM) Integration ───────────────────────

    /**
     * Fetch FCM configuration, initialize Firebase, register Service Worker, and request permission.
     */
    function initFCM() {
        if (typeof firebase === "undefined") {
            console.warn("[StadiumOps AI] Firebase SDK not loaded. Live Alerts disabled.");
            updateAlertsUI("disabled");
            return;
        }

        // Fetch config from backend
        fetch(API_BASE_URL + "/api/fcm/config")
            .then(function (res) {
                if (!res.ok) { throw new Error("Could not retrieve FCM config from server."); }
                return res.json();
            })
            .then(function (config) {
                if (!config.apiKey || !config.messagingSenderId) {
                    console.log("[StadiumOps AI] Firebase config is not fully populated in env. Live Alerts disabled.");
                    updateAlertsUI("disabled");
                    return;
                }

                // Initialize Firebase App if not already initialized
                if (!firebase.apps.length) {
                    firebase.initializeApp(config);
                }
                var messaging = firebase.messaging();
                fcmInitialized = true;

                // Set up onMessage to show alerts when the app is in the foreground
                messaging.onMessage(function (payload) {
                    console.log("[StadiumOps AI] Foreground notification received: ", payload);
                    showToast(payload.notification.title + ": " + payload.notification.body, "success");
                });

                // Request permission and token
                requestNotificationPermission(messaging, config.vapidKey);
            })
            .catch(function (error) {
                console.error("[StadiumOps AI FCM]", error);
                updateAlertsUI("disabled");
            });
    }

    /**
     * Ask for notification permissions and retrieve current registration token.
     */
    function requestNotificationPermission(messaging, vapidKey) {
        Notification.requestPermission()
            .then(function (permission) {
                if (permission === "granted") {
                    console.log("[StadiumOps AI] Notification permission granted.");
                    
                    // Register SW explicitly so it uses correct file location
                    navigator.serviceWorker.register("firebase-messaging-sw.js")
                        .then(function (registration) {
                            messaging.getToken({
                                serviceWorkerRegistration: registration,
                                vapidKey: vapidKey
                            })
                            .then(function (currentToken) {
                                if (currentToken) {
                                    fcmToken = currentToken;
                                    registerTokenWithBackend(currentToken);
                                } else {
                                    console.warn("[StadiumOps AI] No registration token available.");
                                    updateAlertsUI("inactive");
                                }
                            })
                            .catch(function (err) {
                                console.error("[StadiumOps AI] Get token error: ", err);
                                updateAlertsUI("inactive");
                            });
                        })
                        .catch(function (err) {
                            console.error("[StadiumOps AI] SW registration error: ", err);
                            updateAlertsUI("inactive");
                        });
                } else {
                    console.warn("[StadiumOps AI] Notification permission denied.");
                    showToast("Notification permission denied. Live Alerts will be disabled.", "error");
                    updateAlertsUI("inactive");
                }
            });
    }

    /**
     * Send FCM registration token to FastAPI backend.
     */
    function registerTokenWithBackend(token) {
        fetch(API_BASE_URL + "/api/devices/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ token: token })
        })
        .then(function (res) {
            if (!res.ok) { throw new Error("Backend token registration failed."); }
            return res.json();
        })
        .then(function () {
            console.log("[StadiumOps AI] Device registered successfully with backend.");
            updateAlertsUI("active");
        })
        .catch(function (err) {
            console.error("[StadiumOps AI] Token registration error: ", err);
            updateAlertsUI("inactive");
        });
    }

    /**
     * Update the Live Alerts button UI based on current status.
     * @param {"active"|"inactive"|"disabled"} status - Alerts status
     */
    function updateAlertsUI(status) {
        if (!fcmAlertsBtn) { return; }

        if (status === "active") {
            fcmAlertsBtn.textContent = "🔔 Live Alerts: Active";
            fcmAlertsBtn.className = "btn-alerts active";
            fcmAlertsBtn.disabled = false;
        } else if (status === "inactive") {
            fcmAlertsBtn.textContent = "🔔 Enable Live Alerts";
            fcmAlertsBtn.className = "btn-alerts";
            fcmAlertsBtn.disabled = false;
        } else if (status === "disabled") {
            fcmAlertsBtn.textContent = "🔔 Alerts Unavailable";
            fcmAlertsBtn.className = "btn-alerts disabled";
            fcmAlertsBtn.disabled = true;
        }
    }

    // Register click event
    if (fcmAlertsBtn) {
        fcmAlertsBtn.addEventListener("click", function () {
            initFCM();
        });
    }

    // ── WebSocket Real-Time Connection ────────────────────────────────────

    var ws = null;
    function connectWebSocket() {
        var wsUrl;
        if (API_BASE_URL.startsWith("http://")) {
            wsUrl = API_BASE_URL.replace("http://", "ws://") + "/api/ws";
        } else if (API_BASE_URL.startsWith("https://")) {
            wsUrl = API_BASE_URL.replace("https://", "wss://") + "/api/ws";
        } else {
            wsUrl = "ws://127.0.0.1:8000/api/ws";
        }

        ws = new WebSocket(wsUrl);

        ws.onopen = function () {
            console.log("[StadiumOps AI] WebSocket connected");
            var label = autoRefreshIndicator.querySelector("span:not(.spinner)");
            if (label) {
                label.textContent = "Live: Connected";
            }
            autoRefreshIndicator.classList.add("active");

            // Disable polling when WS is connected
            if (autoRefreshTimer) {
                clearInterval(autoRefreshTimer);
                autoRefreshTimer = null;
            }
        };

        ws.onmessage = function (event) {
            try {
                var data = JSON.parse(event.data);
                if (data.type === "recommendations_update") {
                    console.log("[StadiumOps AI] WebSocket update received: ", data.recommendations);
                    renderRecommendations(data.recommendations);
                    showToast("Real-time recommendations updated.", "success");
                }
            } catch (err) {
                console.error("[StadiumOps AI] WebSocket message parsing error:", err);
            }
        };

        ws.onclose = function () {
            console.log("[StadiumOps AI] WebSocket disconnected. Falling back to 30s polling.");
            var label = autoRefreshIndicator.querySelector("span:not(.spinner)");
            if (label) {
                label.textContent = "Auto-refresh: 30s";
            }
            autoRefreshIndicator.classList.remove("active");

            // Start polling as fallback
            startAutoRefresh();

            // Reconnect attempt after 5 seconds
            setTimeout(connectWebSocket, 5000);
        };

        ws.onerror = function (error) {
            console.error("[StadiumOps AI] WebSocket error:", error);
            ws.close();
        };
    }

    // ── Initialise ───────────────────────────────────────────────────────

    connectWebSocket();

    // Check if permission was already granted in past sessions, if so auto-initialize
    if (typeof Notification !== "undefined" && Notification.permission === "granted") {
        setTimeout(function () {
            initFCM();
        }, 1000);
    } else if (typeof Notification !== "undefined" && Notification.permission === "default") {
        updateAlertsUI("inactive");
    } else {
        updateAlertsUI("disabled");
    }

})();
