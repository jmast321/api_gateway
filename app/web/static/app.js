// Hermes AI Gateway Dashboard Logic
let allModels = [];

document.addEventListener('DOMContentLoaded', () => {
    initModeSelector();
    initPlayground();
    initRefreshButton();
    loadDashboardData();

    // Auto-refresh telemetry & stats every 4 seconds
    setInterval(loadTelemetryAndStats, 4000);
});

async function loadDashboardData() {
    await Promise.all([
        loadModels(),
        loadTelemetryAndStats()
    ]);
}

// 1. Stats and Telemetry
async function loadTelemetryAndStats() {
    try {
        const statsRes = await fetch('/api/telemetry/stats');
        if (statsRes.ok) {
            const stats = await statsRes.json();
            document.getElementById('stat-free-models').textContent = stats.total_free_models || '--';
            document.getElementById('stat-total-requests').textContent = stats.total_requests || '0';
            document.getElementById('stat-avg-latency').textContent = `${stats.average_latency_ms || 0} ms`;
            document.getElementById('stat-fallbacks').textContent = `${stats.total_fallbacks || 0} (retries: ${stats.total_retries || 0})`;

            // Sync mode selector if not focused
            const modeSelect = document.getElementById('mode-select');
            if (modeSelect && document.activeElement !== modeSelect && stats.active_mode) {
                modeSelect.value = stats.active_mode;
            }
        }

        const logsRes = await fetch('/api/telemetry/logs?limit=30');
        if (logsRes.ok) {
            const logs = await logsRes.json();
            renderTelemetryFeed(logs);
        }
    } catch (err) {
        console.error('Error fetching telemetry/stats:', err);
    }
}

function renderTelemetryFeed(logs) {
    const feed = document.getElementById('telemetry-feed');
    if (!logs || logs.length === 0) {
        feed.innerHTML = `
            <div class="empty-state">
                <span class="empty-icon">⏳</span>
                <p>No requests recorded yet.</p>
                <small>Send requests to <code>http://localhost:8000/v1/chat/completions</code></small>
            </div>
        `;
        return;
    }

    feed.innerHTML = logs.map(log => {
        let cardClass = 'telemetry-card';
        if (log.fallback_used) cardClass += ' fallback';
        if (log.status_code >= 400 || log.error) cardClass += ' error';

        const timeStr = new Date(log.timestamp).toLocaleTimeString();
        const tagsHtml = (log.tags || []).map(t => `<span class="tag">${escapeHtml(t)}</span>`).join('');

        return `
            <div class="${cardClass}">
                <div class="telemetry-card-top">
                    <span class="telemetry-model">${escapeHtml(log.selected_model)}</span>
                    <span>${timeStr} · ${log.latency_ms}ms</span>
                </div>
                ${log.prompt_snippet ? `<div class="telemetry-snippet">"${escapeHtml(log.prompt_snippet)}"</div>` : ''}
                <div class="telemetry-meta">
                    <span>Mode: <strong>${escapeHtml(log.routing_mode)}</strong></span>
                    ${log.fallback_used ? '<span style="color:var(--accent-amber)">⚠️ Fallback Used</span>' : ''}
                    ${log.retries_count > 0 ? `<span>Retries: ${log.retries_count}</span>` : ''}
                </div>
                ${tagsHtml ? `<div class="tag-list">${tagsHtml}</div>` : ''}
                ${log.error ? `<div style="color:var(--accent-rose); font-size:11px;">Error: ${escapeHtml(log.error)}</div>` : ''}
            </div>
        `;
    }).join('');
}

// 2. Free Models Explorer
async function loadModels() {
    const container = document.getElementById('models-container');
    try {
        const res = await fetch('/api/models/free');
        if (!res.ok) throw new Error('Failed to fetch models');
        const data = await res.json();
        allModels = data.models || [];
        document.getElementById('models-count-badge').textContent = `${allModels.length} Active`;
        renderModelsList(allModels);
    } catch (err) {
        container.innerHTML = `<div style="color:var(--accent-rose); padding: 12px;">Failed to load models: ${err.message}</div>`;
    }
}

function renderModelsList(models) {
    const container = document.getElementById('models-container');
    if (!models || models.length === 0) {
        container.innerHTML = `<div class="empty-state"><p>No models match your filter.</p></div>`;
        return;
    }

    container.innerHTML = models.map(m => {
        return `
            <div class="model-item">
                <div class="model-item-top">
                    <span class="model-name">${escapeHtml(m.name || m.id)}</span>
                    <span class="model-provider">${escapeHtml(m.provider || 'OpenRouter')}</span>
                </div>
                <div class="model-id">${escapeHtml(m.id)}</div>
                <div class="model-item-badges">
                    <span class="feature-badge ${m.has_vision ? 'active' : ''}">👁️ Vision</span>
                    <span class="feature-badge ${m.has_tools ? 'active' : ''}">🛠️ Tools</span>
                    <span class="feature-badge ${m.is_coder ? 'active' : ''}">💻 Coder</span>
                    <span class="feature-badge ${m.is_reasoning ? 'active' : ''}">🧠 Reasoning</span>
                    <span class="feature-badge">${Math.round(m.context_length / 1024)}k Context</span>
                </div>
            </div>
        `;
    }).join('');
}

// Filter models input
const filterInput = document.getElementById('filter-models');
if (filterInput) {
    filterInput.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase().trim();
        if (!query) {
            renderModelsList(allModels);
            return;
        }
        const filtered = allModels.filter(m => 
            m.id.toLowerCase().includes(query) ||
            (m.name && m.name.toLowerCase().includes(query)) ||
            (m.provider && m.provider.toLowerCase().includes(query))
        );
        renderModelsList(filtered);
    });
}

// 3. Routing Mode Selector
function initModeSelector() {
    const modeSelect = document.getElementById('mode-select');
    if (!modeSelect) return;

    modeSelect.addEventListener('change', async (e) => {
        const newMode = e.target.value;
        try {
            const res = await fetch('/api/config/mode', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mode: newMode })
            });
            if (res.ok) {
                console.log(`Routing mode changed to ${newMode}`);
            }
        } catch (err) {
            console.error('Failed to change mode:', err);
        }
    });
}

// 4. Refresh Models Button
function initRefreshButton() {
    const btn = document.getElementById('btn-refresh-models');
    if (!btn) return;

    btn.addEventListener('click', async () => {
        btn.disabled = true;
        btn.innerHTML = `<span class="icon">⏳</span> Refreshing...`;
        try {
            await fetch('/api/models/refresh', { method: 'POST' });
            await loadModels();
            await loadTelemetryAndStats();
        } finally {
            btn.disabled = false;
            btn.innerHTML = `<span class="icon">🔄</span> Refresh Models`;
        }
    });

    const btnLogs = document.getElementById('btn-refresh-logs');
    if (btnLogs) {
        btnLogs.addEventListener('click', loadTelemetryAndStats);
    }
}

// 5. Interactive Playground
function initPlayground() {
    const btnTest = document.getElementById('btn-test-route');
    const promptInput = document.getElementById('play-prompt');
    const checkImage = document.getElementById('play-image');
    const checkTools = document.getElementById('play-tools');
    const resultBox = document.getElementById('playground-result');

    // Preset chips
    document.querySelectorAll('.btn-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            promptInput.value = chip.getAttribute('data-prompt') || '';
            checkImage.checked = chip.getAttribute('data-img') === 'true';
            checkTools.checked = false;
            triggerPlaygroundTest();
        });
    });

    if (btnTest) {
        btnTest.addEventListener('click', triggerPlaygroundTest);
    }

    async function triggerPlaygroundTest() {
        const promptText = promptInput.value.trim();
        if (!promptText) {
            promptInput.focus();
            return;
        }

        btnTest.disabled = true;
        btnTest.textContent = '⚡ Analyzing...';

        try {
            const res = await fetch('/api/test/classify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    prompt: promptText,
                    has_image: checkImage.checked,
                    has_tools: checkTools.checked
                })
            });

            if (!res.ok) throw new Error('Classification request failed');
            const data = await res.json();
            const dec = data.decision;

            resultBox.classList.remove('hidden');
            document.getElementById('res-primary-model').textContent = dec.primary_model;
            document.getElementById('res-tokens').textContent = `~${dec.estimated_tokens} tokens`;
            document.getElementById('res-rationale').textContent = dec.rationale || '--';

            // Tags
            const tagsCont = document.getElementById('res-tags');
            const detected = dec.heuristic_profile ? dec.heuristic_profile.detected_tags : [];
            tagsCont.innerHTML = detected.length ? detected.map(t => `<span class="tag">${escapeHtml(t)}</span>`).join('') : '<span class="tag">general</span>';

            // Fallbacks
            const fallbacksCont = document.getElementById('res-fallbacks');
            fallbacksCont.innerHTML = (dec.fallback_models || []).map(f => `<span class="tag tag-fallback">${escapeHtml(f)}</span>`).join(' ') || 'None';

        } catch (err) {
            alert('Error during simulation test: ' + err.message);
        } finally {
            btnTest.disabled = false;
            btnTest.textContent = '⚡ Test Decision';
        }
    }
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}
