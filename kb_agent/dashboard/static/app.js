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
            const detail = response.headers.get("content-type")?.includes("json")
                ? (await response.json()).detail || response.statusText
                : response.statusText;
            throw new Error(`API error: ${response.status} ${detail}`);
        }
        return response.json();
    } finally {
        clearTimeout(timer);
    }
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
        tab.classList.toggle("active", tab.dataset.view === route.view || (tab.dataset.view === "features" && route.view === "feature-detail"));
    });

    // Toggle graph controls
    document.getElementById("graph-controls").style.display = route.view === "graph" ? "flex" : "none";

    // Toggle main areas
    const mainContent = document.getElementById("main-content");
    const graphContainer = document.getElementById("graph-container");

    if (route.view === "graph") {
        mainContent.style.display = "none";
        graphContainer.style.display = "block";
        if (!state.graphLoaded) {
            GraphView.loadData();
        } else {
            GraphView.render();
        }
    } else {
        mainContent.style.display = "block";
        graphContainer.style.display = "none";
        renderCurrentView(route);
    }

    // Update suggestions when view changes
    ChatPanel.updateDefaultSuggestions();
}

function renderCurrentView(route) {
    const container = document.getElementById("main-content");
    switch (route.view) {
        case "overview":
            renderOverview(container);
            break;
        case "features":
            renderFeatures(container);
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
        const data = await apiFetch("/api/overview");
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
        html += `<button class="action-btn primary" onclick="navigate('#graph')">Start with Architecture</button>`;
        html += `<button class="action-btn primary" onclick="navigate('#features')">Explore Features</button>`;
        html += `<button class="action-btn primary" onclick="ChatPanel.focus()">Ask about this project</button>`;
        html += `</div>`;

        container.innerHTML = html;
    } catch (error) {
        container.innerHTML = `<div class="error-card"><p>Error loading overview: ${escapeHtml(error.message)}</p></div>`;
    }
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
async function loadGraph() {
    try {
        const [nodesData, edgesData, statusData] = await Promise.all([
            apiFetch("/api/nodes"),
            apiFetch("/api/edges"),
            apiFetch("/api/status"),
        ]);

        allNodes = nodesData.nodes;
        allEdges = edgesData.edges;
        document.getElementById("stats").textContent =
            `${allNodes.length} nodes | ${allEdges.length} edges | ${statusData.languages?.join(", ") || ""}`;
        document.getElementById("loading").style.display = "none";
        renderGraph();
    } catch (error) {
        document.getElementById("loading").textContent = `Error loading graph: ${error.message}`;
    }
}

function renderGraph() {
    const container = document.getElementById("graph-container");
    const width = container.clientWidth;
    const height = container.clientHeight;
    d3.select("#graph-container svg").remove();

    svg = d3.select("#graph-container").append("svg").attr("width", width).attr("height", height);
    const graph = svg.append("g");

    svg.call(d3.zoom().scaleExtent([0.1, 8]).on("zoom", (event) => graph.attr("transform", event.transform)));

    let filteredEdges = allEdges;
    if (activeEdgeFilter) {
        filteredEdges = allEdges.filter((edge) => edge.kind === activeEdgeFilter);
    }

    const nodeIds = new Set(allNodes.map((node) => node.id));
    const validEdges = filteredEdges.filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target));

    allNodes.forEach((node) => {
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
        .data(allNodes)
        .join("g")
        .attr("class", "node")
        .call(d3.drag().on("start", dragStart).on("drag", dragged).on("end", dragEnd));

    node.append("circle")
        .attr("r", 6)
        .attr("fill", (item) => KIND_COLORS[item.kind] || "#8b949e")
        .attr("stroke", (item) => KIND_COLORS[item.kind] || "#8b949e")
        .attr("stroke-opacity", 0.3);

    node.append("text")
        .attr("dx", 10)
        .attr("dy", 4)
        .text((item) => (item.name.length > 20 ? `${item.name.slice(0, 20)}...` : item.name));

    node.on("click", (event, item) => {
        event.stopPropagation();
        showDetail(item);
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

    simulation = d3
        .forceSimulation(allNodes)
        .force("link", d3.forceLink(validEdges).id((item) => item.id).distance(60).strength(0.3))
        .force("charge", d3.forceManyBody().strength(-80))
        .force("center", d3.forceCenter(width / 2, height / 2))
        .force("collision", d3.forceCollide(12));

    simulation.on("tick", () => {
        link
            .attr("x1", (edge) => edge.source.x)
            .attr("y1", (edge) => edge.source.y)
            .attr("x2", (edge) => edge.target.x)
            .attr("y2", (edge) => edge.target.y);
        node.attr("transform", (item) => `translate(${item.x},${item.y})`);
    });

    function dragStart(event, item) {
        if (!event.active) {
            simulation.alphaTarget(0.3).restart();
        }
        item.fx = item.x;
        item.fy = item.y;
    }

    function dragged(event, item) {
        item.fx = event.x;
        item.fy = event.y;
    }

    function dragEnd(event, item) {
        if (!event.active) {
            simulation.alphaTarget(0);
        }
        item.fx = null;
        item.fy = null;
    }
}

async function showDetail(node) {
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
        html += `<button class="action-btn" onclick="ChatPanel.sendFromButton('Giải thích ${escapeAttribute(data.name)}')">Explain</button>`;
        html += `<button class="action-btn" onclick="ChatPanel.sendFromButton('${escapeAttribute(data.name)} gọi những gì?')">Trace calls</button>`;
        html += `<button class="action-btn" onclick="ChatPanel.sendFromButton('Ảnh hưởng nếu sửa ${escapeAttribute(data.name)}?')">Impact</button>`;
        html += `<button class="action-btn" onclick="openSourceSnippet('${escapeAttribute(data.path)}', ${data.line_start}, ${data.line_end})">Open source</button>`;
        html += `</div>`;

        html += `<h2>${escapeHtml(data.name)}</h2>`;
    content.innerHTML = "<p>Loading...</p>";
    try {
        const data = await apiFetch(`/api/node/${encodeURIComponent(node.id)}`);

        let html = `<h2>${escapeHtml(data.name)}</h2>`;
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
        if (data.connections.length) {
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
                const nodeId = element.dataset.nodeId;
                const nextNode = allNodes.find((item) => item.id === nodeId);
                if (nextNode) {
                    showDetail(nextNode);
                }
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
        openSymbolPanel(nodeId);
    } else if (path) {
        openSourceSnippet(path, lineStart, lineEnd);
    }
}

// ---------------------------------------------------------------------------
// Event Listeners
// ---------------------------------------------------------------------------

// Close detail panel
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

document.getElementById("close-detail").addEventListener("click", () => {
    document.getElementById("detail-panel").classList.remove("visible");
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
        // Search highlighting is best-effort in the graph UI.
    }
});

document.getElementById("btn-hotpath").addEventListener("click", async () => {
    showHotpath = !showHotpath;
    document.getElementById("btn-hotpath").classList.toggle("active", showHotpath);
    if (showHotpath) {
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
});

document.getElementById("btn-reset").addEventListener("click", () => {
    d3.selectAll(".node").classed("highlighted", false).classed("hot", false).select("circle").attr("r", 6);
    document.getElementById("search-input").value = "";
    document.getElementById("btn-hotpath").classList.remove("active");
    showHotpath = false;
    if (simulation) {
        simulation.alpha(0.3).restart();
    }
});

document.getElementById("edge-filter").addEventListener("change", (event) => {
    activeEdgeFilter = event.target.value;
    renderGraph();
});

loadGraph();
