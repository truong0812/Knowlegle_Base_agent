/* ========================================================================
   KB Agent Dashboard — app.js
   SPA with hash routing, Overview/Features/Graph views, Chat panel.
   ======================================================================== */

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const KIND_COLORS = {
    class: "#58a6ff",
    function: "#3fb950",
    method: "#56d364",
    interface: "#a371f7",
    enum: "#ffa657",
    module: "#f0883e",
    package: "#d2a8ff",
    struct: "#79c0ff",
    variable: "#8b949e",
};

// ---------------------------------------------------------------------------
// Application State
// ---------------------------------------------------------------------------

const state = {
    activeView: "overview",
    currentNodeId: null,
    currentFeatureId: null,
    currentFilePath: null,
    chatHistory: [],
    overviewData: null,
    featuresData: null,
    graphLoaded: false,
};

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function escapeHtml(value) {
    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function escapeAttribute(value) {
    return escapeHtml(value).replace(/`/g, "&#096;");
}

async function apiFetch(url, timeoutMs = 10000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
        const response = await fetch(url, { signal: controller.signal });
        if (!response.ok) {
            const detail = await responseDetail(response);
            const error = new Error(`API error: ${response.status} ${formatErrorDetail(detail)}`);
            error.status = response.status;
            error.detail = detail;
            error.code = typeof detail === "object" && detail !== null ? detail.code : null;
            throw error;
        }
        return response.json();
    } finally {
        clearTimeout(timer);
    }
}

async function apiPost(url, payload = {}, timeoutMs = 10000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
        const response = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
            signal: controller.signal,
        });
        if (!response.ok) {
            const detail = await responseDetail(response);
            const error = new Error(`API error: ${response.status} ${formatErrorDetail(detail)}`);
            error.status = response.status;
            error.detail = detail;
            throw error;
        }
        return response.json();
    } finally {
        clearTimeout(timer);
    }
}

async function responseDetail(response) {
    if (!response.headers.get("content-type")?.includes("json")) {
        return response.statusText;
    }
    try {
        const payload = await response.json();
        return payload.detail || payload;
    } catch (error) {
        return response.statusText;
    }
}

function formatErrorDetail(detail) {
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object") {
        return detail.message || detail.code || JSON.stringify(detail);
    }
    return "Request failed";
}

const apiClient = {
    fetch(url, options = {}) {
        return apiFetch(url, options.timeoutMs || 10000);
    },
};

async function fetchData(url, client = apiClient) {
    if (typeof url !== "string" || !url.startsWith("/api/")) {
        throw new Error("fetchData expects an internal /api/ URL.");
    }
    return client.fetch(url);
}

function formatNumber(n) {
    if (n == null) return "—";
    return n.toLocaleString();
}

// ---------------------------------------------------------------------------
// Hash Router
// ---------------------------------------------------------------------------

function parseHash() {
    const hash = window.location.hash.slice(1) || "overview";
    const parts = hash.split("/");
    if (parts[0] === "features" && parts.length > 1) {
        return { view: "feature-detail", featureId: parts.slice(1).join("/") };
    }
    if (parts[0] === "paths" && parts.length > 1) {
        return { view: "path-detail", pathId: decodeURIComponent(parts.slice(1).join("/")) };
    }
    if (parts[0] === "paths") return { view: "paths" };
    if (parts[0] === "topics" && parts.length > 1) {
        return { view: "topic-detail", topicId: decodeURIComponent(parts.slice(1).join("/")) };
    }
    if (parts[0] === "topics") return { view: "topics" };
    if (parts[0] === "features") return { view: "features" };
    if (parts[0] === "graph") return { view: "graph" };
    if (parts[0] === "node" && parts.length > 1) {
        return { view: "node", nodeId: decodeURIComponent(parts.slice(1).join("/")) };
    }
    return { view: "overview" };
}

function navigate(hash) {
    window.location.hash = hash;
}

function onRouteChange() {
    const route = parseHash();
    state.activeView = route.view;

    // Update nav tabs
    document.querySelectorAll(".nav-tab").forEach((tab) => {
        tab.classList.toggle(
            "active",
            tab.dataset.view === route.view ||
                (tab.dataset.view === "features" && route.view === "feature-detail") ||
                (tab.dataset.view === "paths" && route.view === "path-detail") ||
                (tab.dataset.view === "topics" && route.view === "topic-detail")
        );
    });

    renderRouteShell(route);

    // Update suggestions when view changes
    ChatPanel.updateDefaultSuggestions();
}

function renderRouteShell(route) {
    document.getElementById("graph-controls").style.display = route.view === "graph" ? "flex" : "none";

    const mainContent = document.getElementById("main-content");
    const graphContainer = document.getElementById("graph-container");

    if (route.view === "graph") {
        renderGraphRoute(mainContent, graphContainer);
    } else {
        renderContentRoute(mainContent, graphContainer, route);
    }
}

function renderGraphRoute(mainContent, graphContainer) {
    mainContent.style.display = "none";
    graphContainer.style.display = "block";
    if (!state.graphLoaded) {
        GraphView.loadData();
    } else {
        GraphView.render();
    }
}

function renderContentRoute(mainContent, graphContainer, route) {
    mainContent.style.display = "block";
    graphContainer.style.display = "none";
    renderCurrentView(route, mainContent);
}

function renderCurrentView(route, container) {
    switch (route.view) {
        case "overview":
            renderOverview(container);
            break;
        case "features":
            renderFeatures(container);
            break;
        case "paths":
            renderPaths(container);
            break;
        case "path-detail":
            renderPathDetail(container, route.pathId);
            break;
        case "topics":
            renderTopics(container);
            break;
        case "topic-detail":
            renderTopicDetail(container, route.topicId);
            break;
        case "feature-detail":
            state.currentFeatureId = route.featureId;
            renderFeatureDetail(container, route.featureId);
            break;
        case "node":
            state.currentNodeId = route.nodeId;
            openSymbolPanel(route.nodeId);
            break;
        default:
            renderOverview(container);
    }
}

// ---------------------------------------------------------------------------
// Overview View
// ---------------------------------------------------------------------------

async function renderOverview(container) {
    container.innerHTML = '<div class="loading-text">Loading overview...</div>';
    try {
        const [data, learningData] = await Promise.all([
            apiFetch("/api/overview"),
            apiFetch("/api/learning/recommendations").catch(() => ({ recommendations: [] })),
        ]);
        if (data.error) {
            container.innerHTML = `<div class="error-card"><h2>Knowledge Base Not Found</h2><p>${escapeHtml(data.error.message)}</p><p>Run <code>kb-agent analyze</code> first to create a knowledge base.</p></div>`;
            return;
        }
        state.overviewData = data;

        let html = "";

        // Summary card
        if (data.summary) {
            html += `<div class="overview-card"><h2>Project Overview</h2><p>${escapeHtml(data.summary)}</p></div>`;
        }

        // Stats row
        if (data.stats) {
            html += `<div class="stats-row">`;
            html += `<div class="stat-card"><div class="stat-value">${formatNumber(data.stats.total_entries)}</div><div class="stat-label">Entries</div></div>`;
            html += `<div class="stat-card"><div class="stat-value">${formatNumber(data.stats.node_count)}</div><div class="stat-label">Nodes</div></div>`;
            html += `<div class="stat-card"><div class="stat-value">${formatNumber(data.stats.edge_count)}</div><div class="stat-label">Edges</div></div>`;
            html += `<div class="stat-card"><div class="stat-value">${(data.languages || []).join(", ") || "—"}</div><div class="stat-label">Languages</div></div>`;
            html += `</div>`;
        }

        const recommendations = (learningData.recommendations || []).slice(0, 4);
        if (recommendations.length > 0) {
            html += `<div class="overview-card"><h3>Recommended Next</h3>`;
            html += `<div class="recommendation-list">`;
            recommendations.forEach((recommendation) => {
                html += renderRecommendationItem(recommendation);
            });
            html += `</div></div>`;
        }

        // Top features
        if (data.top_features && data.top_features.length > 0) {
            html += `<div class="overview-card"><h3>Top Features</h3>`;
            data.top_features.forEach((f) => {
                html += `<div class="clickable-list-item" onclick="navigate('#features/${escapeAttribute(f.id)}')">${escapeHtml(f.name)} <span class="meta-info">(${f.member_count} members, density: ${f.edge_density.toFixed(2)})</span></div>`;
            });
            html += `</div>`;
        }

        // Top hot symbols
        if (data.top_hot_symbols && data.top_hot_symbols.length > 0) {
            html += `<div class="overview-card"><h3>Hot Symbols</h3>`;
            data.top_hot_symbols.forEach((s) => {
                const hotnessPct = Math.round((s.hotness || 0) * 100);
                html += `<div class="clickable-list-item" onclick="openSymbolPanel('${escapeAttribute(s.node_id)}')">${escapeHtml(s.name)} <span class="meta-info">🔥 ${hotnessPct}% (${s.incoming_calls} calls)</span></div>`;
            });
            html += `</div>`;
        }

        // Modules
        if (data.top_modules && data.top_modules.length > 0) {
            html += `<div class="overview-card"><h3>Top Modules</h3><div class="tags">`;
            data.top_modules.forEach((m) => {
                html += `<span class="tag">${escapeHtml(m)}</span>`;
            });
            html += `</div></div>`;
        }

        // Action buttons
        html += `<div class="action-buttons overview-actions">`;
        html += `<button class="action-btn primary" onclick="navigate('#paths')">Start a Learning Path</button>`;
        html += `<button class="action-btn primary" onclick="navigate('#topics')">Explore Topics</button>`;
        html += `<button class="action-btn primary" onclick="navigate('#features')">Explore Features</button>`;
        html += `<button class="action-btn primary" onclick="ChatPanel.focus()">Ask about this project</button>`;
        html += `</div>`;

        container.innerHTML = html;
    } catch (error) {
        container.innerHTML = `<div class="error-card"><p>Error loading overview: ${escapeHtml(error.message)}</p></div>`;
    }
}

function renderRecommendationItem(recommendation) {
    const target = recommendation.target || {};
    const action = recommendationAction(recommendation);
    const signals = (recommendation.signals || []).slice(0, 3);
    return `<div class="recommendation-item">
        <div>
            <div class="recommendation-title">${escapeHtml(recommendation.label)}</div>
            <p>${escapeHtml(recommendation.reason)}</p>
            <div class="tags recommendation-tags">${signals.map((signal) => `<span class="tag">${escapeHtml(signal.replace("_", " "))}</span>`).join("")}</div>
        </div>
        <button class="action-btn primary" onclick="${action}">${escapeHtml(recommendationButtonLabel(recommendation, target))}</button>
    </div>`;
}

function recommendationAction(recommendation) {
    const target = recommendation.target || {};
    if (target.topic_id) {
        return `navigate('#topics/${encodeURIComponent(target.topic_id)}')`;
    }
    if (target.path_id) {
        return `navigate('#paths/${encodeURIComponent(target.path_id)}')`;
    }
    if (recommendation.type === "ask_tutor") {
        return "navigate('#tutor')";
    }
    return "navigate('#graph')";
}

function recommendationButtonLabel(recommendation, target) {
    if (target.topic_id) return "Open topic";
    if (target.path_id) return recommendation.type === "continue_path" ? "Continue" : "Start";
    if (recommendation.type === "ask_tutor") return "Ask";
    return "Open";
}

// ---------------------------------------------------------------------------
// Learning Path Views
// ---------------------------------------------------------------------------

async function renderPaths(container) {
    container.innerHTML = '<div class="loading-text">Loading learning paths...</div>';
    try {
        const data = await fetchData("/api/learning/paths");
        const paths = data.paths || [];
        let html = '<div class="path-header">';
        html += '<h2 class="view-title">Learning Paths</h2>';
        html += '</div>';

        if (!paths.length) {
            html += '<div class="overview-card"><h3>No Paths Yet</h3><p>No graph-backed learning paths are available. Generate or refresh the knowledge base first.</p></div>';
            container.innerHTML = html;
            return;
        }

        html += `<div class="path-grid">${paths.map(renderPathCard).join("")}</div>`;
        container.innerHTML = html;
    } catch (error) {
        container.innerHTML = `<div class="error-card"><p>Error loading paths: ${escapeHtml(error.message)}</p></div>`;
    }
}

function renderPathCard(path) {
    const complete = path.lesson_count ? Math.round((path.completed_lesson_count / path.lesson_count) * 100) : 0;
    return `<div class="path-card" onclick="navigate('#paths/${encodeURIComponent(path.id)}')">
        <div class="path-card-top">
            <div>
                <div class="path-card-title">${escapeHtml(path.title)}</div>
                <div class="topic-card-meta">${escapeHtml(path.audience_level)} &middot; ${path.estimated_minutes} min</div>
            </div>
            <span class="status-pill ${escapeAttribute(path.status)}">${escapeHtml(path.status.replace("_", " "))}</span>
        </div>
        <p>${escapeHtml(path.description)}</p>
        <div class="path-progress-bar"><div style="width:${complete}%"></div></div>
        <div class="path-card-foot">${path.completed_lesson_count}/${path.lesson_count} lessons complete</div>
    </div>`;
}

/**
 * Render a learning path detail page with objectives, lesson progress,
 * completion actions, and source/topic links for each lesson.
 */
async function renderPathDetail(container, pathId) {
    container.innerHTML = '<div class="loading-text">Loading path...</div>';
    try {
        const data = await fetchData(`/api/learning/paths/${encodeURIComponent(pathId)}`);
        let html = '<div class="path-detail">';
        html += `<button class="back-btn" onclick="navigate('#paths')">&larr; Back to Paths</button>`;
        html += '<div class="topic-title-row">';
        html += `<div><h2>${escapeHtml(data.title)}</h2><div class="meta"><span>${data.completed_lesson_count}/${data.lesson_count} lessons</span><span>${escapeHtml(data.status.replace("_", " "))}</span></div></div>`;
        html += `<button class="action-btn primary" onclick="ChatPanel.sendFromButton('Help me learn ${escapeAttribute(data.title)}')">Ask tutor</button>`;
        html += '</div>';

        if (data.warnings && data.warnings.length > 0) {
            html += '<div class="warning-strip">';
            data.warnings.forEach((warning) => {
                html += `<div>${escapeHtml(warning.message)}</div>`;
            });
            html += '</div>';
        }

        html += `<div class="overview-card"><h3>Goal</h3><p>${escapeHtml(data.description)}</p></div>`;
        if (data.objectives && data.objectives.length) {
            html += '<div class="overview-card"><h3>Objectives</h3><ul class="lesson-list">';
            data.objectives.forEach((objective) => {
                html += `<li>${escapeHtml(objective)}</li>`;
            });
            html += '</ul></div>';
        }

        html += '<div class="lesson-stack">';
        (data.lessons || []).forEach((lesson, index) => {
            html += renderLessonCard(data.id, lesson, index + 1);
        });
        html += '</div></div>';
        container.innerHTML = html;
        ChatPanel.updateDefaultSuggestions();
    } catch (error) {
        container.innerHTML = `<div class="error-card"><p>Error loading path: ${escapeHtml(error.message)}</p><button class="back-btn" onclick="navigate('#paths')">&larr; Back to Paths</button></div>`;
    }
}

function renderLessonCard(pathId, lesson, number) {
    const citation = (lesson.citations || [])[0];
    const topicButton = citation?.node_id
        ? `<button class="action-btn" onclick="event.stopPropagation(); navigate('#topics/${encodeURIComponent(citation.node_id)}')">Open topic</button>`
        : "";
    const sourceButton = citation?.path
        ? `<button class="action-btn" onclick="event.stopPropagation(); openSourceSnippet('${escapeAttribute(citation.path)}', ${citation.line_start || 0}, ${citation.line_end || 0})">Open source</button>`
        : "";
    return `<div class="lesson-card ${lesson.completed ? "completed" : ""}">
        <div class="lesson-card-head">
            <div>
                <div class="lesson-kicker">Lesson ${number}</div>
                <h3>${escapeHtml(lesson.title)}</h3>
            </div>
            <span class="status-pill ${lesson.completed ? "completed" : "not_started"}">${lesson.completed ? "completed" : "open"}</span>
        </div>
        <p>${escapeHtml(lesson.summary)}</p>
        <p>${escapeHtml(lesson.explanation)}</p>
        ${renderLessonConcepts(lesson.key_concepts || [])}
        <div class="action-buttons">
            <button class="action-btn primary" onclick="completeLesson('${escapeAttribute(pathId)}', '${escapeAttribute(lesson.id)}')">${lesson.completed ? "Completed" : "Mark Complete"}</button>
            ${topicButton}
            ${sourceButton}
        </div>
    </div>`;
}

function renderLessonConcepts(concepts) {
    if (!concepts.length) return "";
    let html = '<div class="tags lesson-tags">';
    concepts.forEach((concept) => {
        html += `<span class="tag">${escapeHtml(concept)}</span>`;
    });
    html += '</div>';
    return html;
}

async function completeLesson(pathId, lessonId) {
    try {
        await apiPost(`/api/learning/paths/${encodeURIComponent(pathId)}/lessons/${encodeURIComponent(lessonId)}/complete`);
        const route = parseHash();
        if (route.view === "path-detail") {
            renderPathDetail(document.getElementById("main-content"), pathId);
        }
    } catch (error) {
        const container = document.getElementById("main-content");
        container.insertAdjacentHTML("afterbegin", `<div class="error-card"><p>Error completing lesson: ${escapeHtml(error.message)}</p></div>`);
    }
}

// ---------------------------------------------------------------------------
// Topic Views
// ---------------------------------------------------------------------------

async function renderTopics(container) {
    container.innerHTML = '<div class="loading-text">Loading topics...</div>';
    try {
        const data = await fetchData("/api/learning/dashboard");
        const recommended = data.recommended_topics || [];

        let html = '<div class="topic-header">';
        html += '<h2 class="view-title">Topics</h2>';
        html += '<div class="topic-search-row">';
        html += '<input type="text" id="topic-search-input" placeholder="Search topics, symbols, or files...">';
        html += '<button class="action-btn primary" id="topic-search-btn">Search</button>';
        html += '</div></div>';
        html += '<div id="topic-search-results">';

        if (recommended.length > 0) {
            html += '<div class="topic-grid">';
            recommended.forEach((topic) => {
                html += renderTopicCard(topic);
            });
            html += '</div>';
        } else {
            html += '<div class="overview-card"><h3>No Topics Found</h3><p>No graph topics are available yet. Generate or refresh the knowledge base first.</p></div>';
        }
        html += '</div>';
        container.innerHTML = html;

        const input = document.getElementById("topic-search-input");
        if (input) input.focus();
    } catch (error) {
        container.innerHTML = `<div class="error-card"><p>Error loading topics: ${escapeHtml(error.message)}</p></div>`;
    }
}

async function searchTopics(query) {
    const resultsEl = document.getElementById("topic-search-results");
    if (!resultsEl) return;
    resultsEl.innerHTML = '<div class="loading-text">Searching topics...</div>';
    try {
        const data = await fetchData(`/api/learning/topics/search?q=${encodeURIComponent(query)}`);
        if (!data.results || data.results.length === 0) {
            resultsEl.innerHTML = '<div class="overview-card"><h3>No Matches</h3><p>Try a symbol name, file path, or module keyword.</p></div>';
            return;
        }
        let html = '<div class="topic-grid">';
        data.results.forEach((topic) => {
            html += renderTopicCard(topic);
        });
        html += '</div>';
        resultsEl.innerHTML = html;
    } catch (error) {
        resultsEl.innerHTML = `<div class="error-card"><p>Error searching topics: ${escapeHtml(error.message)}</p></div>`;
    }
}

function renderTopicCard(topic) {
    return `<div class="topic-card" onclick="navigate('#topics/${encodeURIComponent(topic.id)}')">
        <div class="topic-card-title">${escapeHtml(topic.title)}</div>
        <div class="topic-card-meta">${escapeHtml(topic.type)} &middot; score ${Math.round((topic.score || 0) * 100)}%</div>
        <p>${escapeHtml(topic.summary)}</p>
    </div>`;
}

async function renderTopicDetail(container, topicId) {
    container.innerHTML = '<div class="loading-text">Loading topic...</div>';
    try {
        const data = await fetchData(`/api/learning/topics/${encodeURIComponent(topicId)}`);
        state.currentNodeId = data.id;

        let html = '<div class="topic-detail">';
        html += `<button class="back-btn" onclick="navigate('#topics')">&larr; Back to Topics</button>`;
        html += '<div class="topic-title-row">';
        html += `<div><h2>${escapeHtml(data.title)}</h2><div class="meta"><span>${escapeHtml(data.type)}</span></div></div>`;
        html += `<button class="action-btn primary" onclick="ChatPanel.sendFromButton('Explain ${escapeAttribute(data.title)}')">Ask tutor</button>`;
        html += '</div>';

        if (data.warnings && data.warnings.length > 0) {
            html += '<div class="warning-strip">';
            data.warnings.forEach((warning) => {
                html += `<div>${escapeHtml(warning.message)}</div>`;
            });
            html += '</div>';
        }

        html += `<div class="overview-card"><h3>Summary</h3><p>${escapeHtml(data.summary)}</p></div>`;
        html += `<div class="overview-card"><h3>Explanation</h3><p>${escapeHtml(data.explanation)}</p></div>`;
        html += `<div class="overview-card"><h3>Why It Matters</h3><p>${escapeHtml(data.why_it_matters)}</p></div>`;

        if (data.examples && data.examples.length > 0) {
            html += '<div class="overview-card"><h3>Examples</h3>';
            data.examples.forEach((example) => {
                html += `<pre>${escapeHtml(example)}</pre>`;
            });
            html += '</div>';
        }

        html += renderCitationSection(data.citations || []);
        html += renderTopicLinkSection("Prerequisites", data.prerequisites || []);
        html += renderTopicLinkSection("Related Topics", data.related_topics || [], data.related_symbols || []);
        html += renderGraphNeighborhood(data.graph_context || { nodes: [], relationships: [] });

        if (data.suggested_questions && data.suggested_questions.length > 0) {
            html += '<div class="overview-card"><h3>Suggested Questions</h3><div class="suggestions inline-suggestions">';
            data.suggested_questions.forEach((question) => {
                html += `<span class="suggestion-chip" onclick="ChatPanel.sendFromButton('${escapeAttribute(question)}')">${escapeHtml(question)}</span>`;
            });
            html += '</div></div>';
        }

        html += '</div>';
        container.innerHTML = html;
        ChatPanel.updateDefaultSuggestions();
    } catch (error) {
        container.innerHTML = `<div class="error-card"><p>${escapeHtml(topicErrorMessage(error))}</p><button class="back-btn" onclick="navigate('#topics')">&larr; Back to Topics</button></div>`;
    }
}

function topicErrorMessage(error) {
    const parts = [`Error loading topic: ${error.message || "Request failed"}`];
    if (error.status) parts.push(`Status: ${error.status}`);
    if (error.code) parts.push(`Code: ${error.code}`);
    const detail = formatErrorDetail(error.detail);
    if (detail && detail !== error.message) parts.push(`Detail: ${detail}`);
    return parts.join(" | ");
}

function renderCitationSection(citations) {
    if (!citations.length) {
        return '<div class="overview-card"><h3>Source References</h3><p>No source citations are available for this topic.</p></div>';
    }
    let html = '<div class="overview-card"><h3>Source References</h3><div class="citation-list">';
    citations.forEach((citation) => {
        html += `<button class="citation-card" onclick="handleCitationClick('${escapeAttribute(citation.node_id || "")}', '${escapeAttribute(citation.path || "")}', ${citation.line_start || 0}, ${citation.line_end || 0})">
            <span>${escapeHtml(citation.label)}</span>
            <small>${escapeHtml(citation.path || "")}${citation.line_start ? `:${citation.line_start}-${citation.line_end}` : ""}</small>
        </button>`;
    });
    html += '</div></div>';
    return html;
}

function renderTopicLinkSection(title, ids, labels) {
    if (!ids.length) return "";
    let html = `<div class="overview-card"><h3>${escapeHtml(title)}</h3><div class="tags">`;
    ids.forEach((id, index) => {
        const label = labels && labels[index] ? labels[index] : id;
        html += `<span class="tag clickable-tag" onclick="navigate('#topics/${encodeURIComponent(id)}')">${escapeHtml(label)}</span>`;
    });
    html += '</div></div>';
    return html;
}

function renderGraphNeighborhood(graphContext) {
    const nodes = graphContext.nodes || [];
    const relationships = graphContext.relationships || [];
    if (!nodes.length && !relationships.length) return "";
    let html = '<div class="overview-card"><h3>Graph Neighborhood</h3>';
    if (nodes.length) {
        html += '<div class="tags topic-node-tags">';
        nodes.forEach((node) => {
            html += `<span class="tag clickable-tag" onclick="navigate('#topics/${encodeURIComponent(node.id)}')">${escapeHtml(node.name)}</span>`;
        });
        html += '</div>';
    }
    if (relationships.length) {
        html += '<div class="relationship-list">';
        relationships.forEach((rel) => {
            html += `<div class="relationship-item">${escapeHtml(rel.source_name)} <span>${escapeHtml(rel.kind)}</span> ${escapeHtml(rel.target_name)}</div>`;
        });
        html += '</div>';
    }
    html += '</div>';
    return html;
}

// ---------------------------------------------------------------------------
// Features View
// ---------------------------------------------------------------------------

async function renderFeatures(container) {
    container.innerHTML = '<div class="loading-text">Loading features...</div>';
    try {
        const data = await apiFetch("/api/features");
        state.featuresData = data;

        if (!data.features || data.features.length === 0) {
            container.innerHTML = '<div class="overview-card"><h3>No Features Found</h3><p>No features have been detected. Try analyzing the repository with deeper depth.</p></div>';
            return;
        }

        let html = '<h2 class="view-title">Features</h2><div class="feature-grid">';
        data.features.forEach((f) => {
            html += `<div class="feature-list-item" onclick="navigate('#features/${escapeAttribute(f.id)}')">`;
            html += `<div class="feature-name">${escapeHtml(f.name)}</div>`;
            html += `<div class="feature-meta">${f.members.length} members · density: ${f.edge_density.toFixed(2)} · basis: ${escapeHtml(f.naming_basis)}</div>`;
            html += `</div>`;
        });
        html += `</div>`;
        container.innerHTML = html;
    } catch (error) {
        container.innerHTML = `<div class="error-card"><p>Error loading features: ${escapeHtml(error.message)}</p></div>`;
    }
}

// ---------------------------------------------------------------------------
// Feature Detail View
// ---------------------------------------------------------------------------

async function renderFeatureDetail(container, featureId) {
    container.innerHTML = '<div class="loading-text">Loading feature detail...</div>';
    try {
        const data = await apiFetch(`/api/features/${encodeURIComponent(featureId)}`);

        let html = `<div class="feature-detail-header">`;
        html += `<button class="back-btn" onclick="navigate('#features')">&larr; Back to Features</button>`;
        html += `<h2>${escapeHtml(data.name)}</h2>`;
        html += `<div class="meta"><span>Naming basis: ${escapeHtml(data.naming_basis)}</span><span>Members: ${data.member_count}</span><span>Edge density: ${data.edge_density.toFixed(2)}</span></div>`;
        html += `</div>`;

        // Members table
        if (data.members && data.members.length > 0) {
            html += `<div class="overview-card"><h3>Member Symbols</h3>`;
            html += `<table class="members-table"><thead><tr><th>Name</th><th>Kind</th><th>Path</th><th>Hotness</th></tr></thead><tbody>`;
            data.members.forEach((m) => {
                const hotnessPct = m.hotness != null ? Math.round(m.hotness * 100) : null;
                html += `<tr onclick="openSymbolPanel('${escapeAttribute(m.node_id)}')">`;
                html += `<td>${escapeHtml(m.name)}</td>`;
                html += `<td><span class="kind-badge" style="color:${KIND_COLORS[m.kind] || "#8b949e"}">${escapeHtml(m.kind)}</span></td>`;
                html += `<td>${escapeHtml(m.path)}:${m.line_start}-${m.line_end}</td>`;
                html += `<td>${hotnessPct != null ? `<div class="mini-bar"><div class="mini-bar-fill" style="width:${hotnessPct}%;background:#ffa657"></div></div> ${hotnessPct}%` : "—"}</td>`;
                html += `</tr>`;
            });
            html += `</tbody></table></div>`;
        }

        // Related files
        if (data.related_files && data.related_files.length > 0) {
            html += `<div class="overview-card"><h3>Related Files</h3><div class="tags">`;
            data.related_files.forEach((f) => {
                html += `<span class="tag">${escapeHtml(f)}</span>`;
            });
            html += `</div></div>`;
        }

        container.innerHTML = html;
    } catch (error) {
        container.innerHTML = `<div class="error-card"><p>Error loading feature: ${escapeHtml(error.message)}</p><button class="back-btn" onclick="navigate('#features')">&larr; Back to Features</button></div>`;
    }
}

// ---------------------------------------------------------------------------
// Symbol Detail Panel (shared across views)
// ---------------------------------------------------------------------------

async function openSymbolPanel(nodeId) {
    const panel = document.getElementById("detail-panel");
    const content = document.getElementById("detail-content");
    panel.classList.add("visible");

    state.currentNodeId = nodeId;
    ChatPanel.updateDefaultSuggestions();

    content.innerHTML = "<p>Loading...</p>";
    try {
        const data = await apiFetch(`/api/node/${encodeURIComponent(nodeId)}`);

        let html = "";

        // Action buttons
        html += `<div class="action-buttons">`;
        html += `<button class="action-btn" onclick="navigate('#topics/${encodeURIComponent(data.id)}')">Open topic</button>`;
        html += `<button class="action-btn" onclick="ChatPanel.sendFromButton('Giải thích ${escapeAttribute(data.name)}')">Explain</button>`;
        html += `<button class="action-btn" onclick="ChatPanel.sendFromButton('${escapeAttribute(data.name)} gọi những gì?')">Trace calls</button>`;
        html += `<button class="action-btn" onclick="ChatPanel.sendFromButton('Ảnh hưởng nếu sửa ${escapeAttribute(data.name)}?')">Impact</button>`;
        html += `<button class="action-btn" onclick="openSourceSnippet('${escapeAttribute(data.path)}', ${data.line_start}, ${data.line_end})">Open source</button>`;
        html += `</div>`;

        html += `<h2>${escapeHtml(data.name)}</h2>`;
        html += `<div class="meta"><span>${escapeHtml(data.kind)}</span><span>${escapeHtml(data.language)}</span><span>${escapeHtml(data.path)}:${data.line_start}-${data.line_end}</span></div>`;

        if (data.signature) {
            html += `<div class="section"><h3>Signature</h3><pre>${escapeHtml(data.signature)}</pre></div>`;
        }
        if (data.docstring) {
            html += `<div class="section"><h3>Docstring</h3><pre>${escapeHtml(data.docstring)}</pre></div>`;
        }
        if (data.entry?.ai?.summary) {
            html += `<div class="section"><h3>Summary</h3><p>${escapeHtml(data.entry.ai.summary)}</p></div>`;
        }
        if (data.entry?.ai?.tags) {
            html += `<div class="section"><h3>Tags</h3><p>${escapeHtml(data.entry.ai.tags.join(", "))}</p></div>`;
        }

        if (data.hotness != null) {
            const pct = Math.round(data.hotness * 100);
            html += `<div class="section"><h3>Hotness: ${pct}% (${data.incoming_calls} calls)</h3><div class="confidence-bar"><div class="confidence-fill" style="width:${pct}%;background:#ffa657"></div></div></div>`;
        }

        if (data.connections && data.connections.length) {
            html += `<div class="section"><h3>Connections (${data.connections.length})</h3>`;
            data.connections.forEach((connection) => {
                const name = connection.direction === "outgoing" ? connection.target_name : connection.source_name;
                const id = connection.direction === "outgoing" ? connection.target_id : connection.source_id;
                const arrow = connection.direction === "outgoing" ? "&rarr;" : "&larr;";
                html += `<div class="conn-item" data-node-id="${escapeAttribute(id)}"><span class="dir">${arrow}</span>${escapeHtml(name)} <span class="kind">${escapeHtml(connection.kind)}</span></div>`;
            });
            html += "</div>";
        }

        content.innerHTML = html;
        content.querySelectorAll(".conn-item").forEach((element) => {
            element.addEventListener("click", () => {
                const nid = element.dataset.nodeId;
                if (nid) openSymbolPanel(nid);
            });
        });
    } catch (error) {
        content.innerHTML = `<p>Error: ${escapeHtml(error.message)}</p>`;
    }
}

// ---------------------------------------------------------------------------
// Source Snippet Panel
// ---------------------------------------------------------------------------

async function openSourceSnippet(filePath, lineStart, lineEnd) {
    const panel = document.getElementById("detail-panel");
    const content = document.getElementById("detail-content");
    panel.classList.add("visible");

    content.innerHTML = "<p>Loading source...</p>";
    try {
        const params = new URLSearchParams();
        if (lineStart > 0) params.set("start", lineStart);
        if (lineEnd > 0) params.set("end", lineEnd);
        const data = await apiFetch(`/api/file/${encodeURIComponent(filePath)}?${params}`);

        let html = `<div class="section"><h3>${escapeHtml(filePath)}${lineStart ? `:${lineStart}-${lineEnd}` : ""}</h3>`;
        html += `<div class="source-snippet">`;
        const startLine = lineStart || 1;
        data.lines.forEach((line, i) => {
            const lineNum = startLine + i;
            const highlighted = lineStart && lineEnd && lineNum >= lineStart && lineNum <= lineEnd;
            html += `<div class="source-line${highlighted ? " highlighted" : ""}"><span class="line-num">${lineNum}</span><span class="line-text">${escapeHtml(line)}</span></div>`;
        });
        html += `</div></div>`;
        html += `<button class="action-btn" onclick="ChatPanel.sendFromButton('Giải thích code tại ${escapeAttribute(filePath)}:${lineStart}-${lineEnd}')">Ask about this code</button>`;

        content.innerHTML = html;
    } catch (error) {
        content.innerHTML = `<p>Error loading source: ${escapeHtml(error.message)}</p>`;
    }
}

// ---------------------------------------------------------------------------
// Graph View (wrapped D3 code)
// ---------------------------------------------------------------------------

const GraphView = {
    nodes: [],
    edges: [],
    simulation: null,
    svg: null,
    showHotpath: false,
    activeEdgeFilter: "",

    async loadData() {
        try {
            const [nodesData, edgesData, statusData] = await Promise.all([
                apiFetch("/api/nodes"),
                apiFetch("/api/edges"),
                apiFetch("/api/status"),
            ]);

            this.nodes = nodesData.nodes;
            this.edges = edgesData.edges;
            document.getElementById("stats").textContent =
                `${this.nodes.length} nodes | ${this.edges.length} edges | ${statusData.languages?.join(", ") || ""}`;
            document.getElementById("graph-loading").style.display = "none";
            state.graphLoaded = true;
            this.render();
        } catch (error) {
            document.getElementById("graph-loading").textContent = `Error loading graph: ${error.message}`;
        }
    },

    render() {
        const container = document.getElementById("graph-container");
        const width = container.clientWidth;
        const height = container.clientHeight;
        d3.select("#graph-container svg").remove();

        this.svg = d3.select("#graph-container").append("svg").attr("width", width).attr("height", height);
        const graph = this.svg.append("g");

        this.svg.call(d3.zoom().scaleExtent([0.1, 8]).on("zoom", (event) => graph.attr("transform", event.transform)));

        let filteredEdges = this.edges;
        if (this.activeEdgeFilter) {
            filteredEdges = this.edges.filter((edge) => edge.kind === this.activeEdgeFilter);
        }

        const nodeIds = new Set(this.nodes.map((node) => node.id));
        const validEdges = filteredEdges.filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target));

        this.nodes.forEach((node) => {
            node.x = width / 2 + (Math.random() - 0.5) * 200;
            node.y = height / 2 + (Math.random() - 0.5) * 200;
        });

        const link = graph
            .selectAll(".link")
            .data(validEdges)
            .join("line")
            .attr("class", (edge) => `link ${edge.kind}`)
            .attr("stroke-width", (edge) => Math.max(0.5, edge.confidence * 2));

        const node = graph
            .selectAll(".node")
            .data(this.nodes)
            .join("g")
            .attr("class", "node")
            .call(d3.drag().on("start", (event, item) => this._dragStart(event, item)).on("drag", (event, item) => this._dragged(event, item)).on("end", (event, item) => this._dragEnd(event, item)));

        node.append("circle")
            .attr("r", 6)
            .attr("fill", (item) => KIND_COLORS[item.kind] || "#8b949e")
            .attr("stroke", (item) => KIND_COLORS[item.kind] || "#8b949e")
            .attr("stroke-opacity", 0.3);

        node.append("text")
            .attr("dx", 10)
            .attr("dy", 4)
            .text((item) => (item.name.length > 20 ? `${item.name.slice(0, 20)}...` : item.name));

        const self = this;
        node.on("click", (event, item) => {
            event.stopPropagation();
            openSymbolPanel(item.id);
        });
        node.on("mouseenter", (event, item) => {
            link.attr("stroke-opacity", (edge) => {
                const sourceId = typeof edge.source === "object" ? edge.source.id : edge.source;
                const targetId = typeof edge.target === "object" ? edge.target.id : edge.target;
                return sourceId === item.id || targetId === item.id ? 0.8 : 0.08;
            });
            node.attr("opacity", (candidate) => {
                const connected = validEdges.some((edge) => {
                    const sourceId = typeof edge.source === "object" ? edge.source.id : edge.source;
                    const targetId = typeof edge.target === "object" ? edge.target.id : edge.target;
                    return (
                        (sourceId === candidate.id || targetId === candidate.id) &&
                        (sourceId === item.id || targetId === item.id)
                    );
                });
                return candidate.id === item.id || connected ? 1 : 0.2;
            });
        });
        node.on("mouseleave", () => {
            link.attr("stroke-opacity", 0.4);
            node.attr("opacity", 1);
        });

        this.simulation = d3
            .forceSimulation(this.nodes)
            .force("link", d3.forceLink(validEdges).id((item) => item.id).distance(60).strength(0.3))
            .force("charge", d3.forceManyBody().strength(-80))
            .force("center", d3.forceCenter(width / 2, height / 2))
            .force("collision", d3.forceCollide(12));

        this.simulation.on("tick", () => {
            link
                .attr("x1", (edge) => edge.source.x)
                .attr("y1", (edge) => edge.source.y)
                .attr("x2", (edge) => edge.target.x)
                .attr("y2", (edge) => edge.target.y);
            node.attr("transform", (item) => `translate(${item.x},${item.y})`);
        });
    },

    async toggleHotpath() {
        this.showHotpath = !this.showHotpath;
        document.getElementById("btn-hotpath").classList.toggle("active", this.showHotpath);
        if (this.showHotpath) {
            try {
                const data = await apiFetch("/api/hotpath");
                const hotMap = {};
                data.scores.forEach((score) => {
                    if (score.hotness > 0.3) {
                        hotMap[score.node_id] = score.hotness;
                    }
                });
                d3.selectAll(".node")
                    .classed("hot", (node) => node.id in hotMap)
                    .select("circle")
                    .attr("r", (node) => (node.id in hotMap ? 6 + hotMap[node.id] * 8 : 6));
            } catch (error) {
                // Keep the graph usable if hotpath data is unavailable.
            }
        } else {
            d3.selectAll(".node").classed("hot", false).select("circle").attr("r", 6);
        }
    },

    resetView() {
        d3.selectAll(".node").classed("highlighted", false).classed("hot", false).select("circle").attr("r", 6);
        document.getElementById("search-input").value = "";
        document.getElementById("btn-hotpath").classList.remove("active");
        this.showHotpath = false;
        if (this.simulation) {
            this.simulation.alpha(0.3).restart();
        }
    },

    _dragStart(event, item) {
        if (!event.active) this.simulation.alphaTarget(0.3).restart();
        item.fx = item.x;
        item.fy = item.y;
    },

    _dragged(event, item) {
        item.fx = event.x;
        item.fy = event.y;
    },

    _dragEnd(event, item) {
        if (!event.active) this.simulation.alphaTarget(0);
        item.fx = null;
        item.fy = null;
    },
};

// ---------------------------------------------------------------------------
// Chat Panel (Phase 4)
// ---------------------------------------------------------------------------

const ChatPanel = {
    _loading: false,

    focus() {
        document.getElementById("chat-input").focus();
    },

    getContext() {
        return {
            active_view: state.activeView,
            node_id: state.currentNodeId,
            feature_id: state.currentFeatureId,
            file_path: state.currentFilePath,
        };
    },

    async sendMessage(question) {
        if (!question.trim() || this._loading) return;

        const messagesEl = document.getElementById("chat-messages");

        // Render user message
        this._renderMessage({ role: "user", text: question });
        messagesEl.scrollTop = messagesEl.scrollHeight;

        // Clear input
        document.getElementById("chat-input").value = "";

        // Loading state
        this._loading = true;
        const loadingEl = document.createElement("div");
        loadingEl.className = "chat-loading";
        loadingEl.textContent = "Thinking...";
        loadingEl.id = "chat-loading-indicator";
        messagesEl.appendChild(loadingEl);
        messagesEl.scrollTop = messagesEl.scrollHeight;

        try {
            const response = await fetch("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    question: question,
                    context: this.getContext(),
                    history: state.chatHistory.slice(-10),
                }),
            });

            const data = await response.json();
            messagesEl.removeChild(loadingEl);

            if (data.error) {
                this._renderMessage({ role: "bot", text: `⚠️ ${data.error.message}`, citations: [] });
            } else {
                this._renderMessage({ role: "bot", text: data.answer, citations: data.citations });
                // Update suggestions
                if (data.suggested_questions && data.suggested_questions.length > 0) {
                    this._renderSuggestions(data.suggested_questions);
                }
                // Save to history
                state.chatHistory.push({ role: "user", text: question });
                state.chatHistory.push({ role: "bot", text: data.answer });
            }
        } catch (error) {
            if (document.getElementById("chat-loading-indicator")) {
                messagesEl.removeChild(loadingEl);
            }
            this._renderMessage({ role: "bot", text: `Error: ${error.message}`, citations: [] });
        } finally {
            this._loading = false;
            messagesEl.scrollTop = messagesEl.scrollHeight;
        }
    },

    sendFromButton(question) {
        // Replace placeholder names with actual node name
        if (state.currentNodeId) {
            const parts = state.currentNodeId.split("::");
            const name = parts[parts.length - 1] || state.currentNodeId;
            question = question.replace("function_name", name).replace("symbol_name", name);
        }
        this.sendMessage(question);
    },

    _renderMessage(msg) {
        const messagesEl = document.getElementById("chat-messages");
        const div = document.createElement("div");
        div.className = `chat-msg ${msg.role}`;

        let html = `<div class="msg-bubble">`;
        html += escapeHtml(msg.text).replace(/\n/g, "<br>");
        if (msg.citations && msg.citations.length > 0) {
            html += `<div class="citations">`;
            msg.citations.forEach((c) => {
                html += `<span class="citation-link" onclick="handleCitationClick('${escapeAttribute(c.node_id || "")}', '${escapeAttribute(c.path || "")}', ${c.line_start || 0}, ${c.line_end || 0})">📄 ${escapeHtml(c.label)}${c.line_start ? ` (${c.line_start}-${c.line_end})` : ""}</span>`;
            });
            html += `</div>`;
        }
        html += `</div>`;

        div.innerHTML = html;
        messagesEl.appendChild(div);
    },

    _renderSuggestions(questions) {
        const container = document.getElementById("chat-suggestions");
        container.innerHTML = "";
        questions.forEach((q) => {
            const chip = document.createElement("span");
            chip.className = "suggestion-chip";
            chip.textContent = q;
            chip.addEventListener("click", () => ChatPanel.sendMessage(q));
            container.appendChild(chip);
        });
    },

    updateDefaultSuggestions() {
        const viewSuggestions = {
            overview: [
                "Repo này làm gì?",
                "Module nào quan trọng nhất?",
                "Flow chính của dự án?",
            ],
            paths: [
                "Which path should I learn first?",
                "Summarize this learning path",
                "What should I open next?",
            ],
            "path-detail": [
                "Explain this lesson more simply",
                "Which source should I inspect first?",
                "What is the next step?",
            ],
            features: [
                "Feature này giải quyết vấn đề gì?",
                "Các symbol quan trọng?",
            ],
            "feature-detail": [
                "Feature này giải quyết vấn đề gì?",
                "Các symbol quan trọng?",
            ],
            node: [
                "Function/class này làm gì?",
                "Ai gọi nó?",
                "Ảnh hưởng nếu sửa?",
            ],
            graph: [
                "Cấu trúc tổng thể?",
                "Module nào quan trọng nhất?",
            ],
        };
        const suggestions = viewSuggestions[state.activeView] || viewSuggestions.overview;
        this._renderSuggestions(suggestions);
    },
};

// Handle citation clicks
function handleCitationClick(nodeId, path, lineStart, lineEnd) {
    if (nodeId) {
        if (state.activeView === "topic-detail") {
            navigate(`#topics/${encodeURIComponent(nodeId)}`);
            return;
        }
        openSymbolPanel(nodeId);
    } else if (path) {
        openSourceSnippet(path, lineStart, lineEnd);
    }
}

// ---------------------------------------------------------------------------
// Event Listeners
// ---------------------------------------------------------------------------

document.getElementById("close-detail").addEventListener("click", () => {
    document.getElementById("detail-panel").classList.remove("visible");
});

// Topic search uses delegation because the topic view is re-rendered by the hash router.
document.addEventListener("click", (event) => {
    if (event.target?.id !== "topic-search-btn") return;
    const input = document.getElementById("topic-search-input");
    searchTopics(input?.value || "");
});

document.addEventListener("keydown", (event) => {
    if (event.target?.id !== "topic-search-input" || event.key !== "Enter") return;
    searchTopics(event.target.value);
});

// Search
document.getElementById("search-input").addEventListener("input", async (event) => {
    const query = event.target.value.trim();
    if (!query) {
        d3.selectAll(".node").classed("highlighted", false);
        return;
    }
    try {
        const data = await apiFetch(`/api/search?q=${encodeURIComponent(query)}&top_k=20`);
        const ids = new Set(data.results.map((result) => result.id));
        d3.selectAll(".node").classed("highlighted", (node) => ids.has(node.id));
    } catch (error) {
        // Search highlighting is best-effort.
    }
});

// Graph control buttons
document.getElementById("btn-hotpath").addEventListener("click", () => GraphView.toggleHotpath());
document.getElementById("btn-reset").addEventListener("click", () => GraphView.resetView());
document.getElementById("edge-filter").addEventListener("change", (event) => {
    GraphView.activeEdgeFilter = event.target.value;
    GraphView.render();
});

// Chat input
document.getElementById("chat-input").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        ChatPanel.sendMessage(event.target.value);
    }
});
document.getElementById("chat-send").addEventListener("click", () => {
    ChatPanel.sendMessage(document.getElementById("chat-input").value);
});

// Hash router
window.addEventListener("hashchange", onRouteChange);

// ---------------------------------------------------------------------------
// Initialize
// ---------------------------------------------------------------------------

onRouteChange();
