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

let allNodes = [];
let allEdges = [];
let simulation;
let svg;
let showHotpath = false;
let activeEdgeFilter = "";

async function apiFetch(url) {
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`API error: ${response.status} ${response.statusText}`);
    }
    return response.json();
}

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
