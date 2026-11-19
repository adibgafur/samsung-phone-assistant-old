/**
 * Samsung Phone Assistant - Interactive Web Application
 * Handles API Key management (localStorage + headers), RAG Chatbot, Multi-Agent reviews, and phone catalog.
 */

const STORAGE_KEY = 'groq_api_key';
const STORAGE_PROVIDER = 'ai_provider_mode';
const STORAGE_BASE_URL = 'ai_base_url';
const STORAGE_MODEL = 'ai_model_name';

let userApiKey = localStorage.getItem(STORAGE_KEY) || '';
let providerMode = localStorage.getItem(STORAGE_PROVIDER) || 'groq';
let localBaseUrl = localStorage.getItem(STORAGE_BASE_URL) || 'http://localhost:11434/v1';
let localModelName = localStorage.getItem(STORAGE_MODEL) || 'llama3';
let sessionId = 'session_' + Math.random().toString(36).substring(2, 9);
let cachedPhones = [];

// DOM Elements
const elements = {
  apiKeyPill: document.getElementById('apiKeyPill'),
  apiKeyDot: document.getElementById('apiKeyDot'),
  apiKeyText: document.getElementById('apiKeyText'),
  apiBanner: document.getElementById('apiAlertBanner'),
  apiKeyModal: document.getElementById('apiKeyModal'),
  apiKeyInput: document.getElementById('apiKeyInput'),
  apiKeyFeedback: document.getElementById('apiKeyFeedback'),
  serverKeyNotice: document.getElementById('serverKeyNotice'),
  
  // Navigation
  tabButtons: document.querySelectorAll('.tab-btn'),
  tabPanes: document.querySelectorAll('.tab-pane'),
  
  // Chat
  chatMessages: document.getElementById('chatMessages'),
  chatInput: document.getElementById('chatInput'),
  chatSendBtn: document.getElementById('chatSendBtn'),
  clearChatBtn: document.getElementById('clearChatBtn'),
  promptChips: document.querySelectorAll('.prompt-chip'),
  
  // Review
  phoneSelect: document.getElementById('phoneSelect'),
  reviewBtn: document.getElementById('reviewBtn'),
  reviewContent: document.getElementById('reviewContent'),
  reviewHeader: document.getElementById('reviewHeader'),
  copyReviewBtn: document.getElementById('copyReviewBtn'),
  step1Node: document.getElementById('step1Node'),
  step2Node: document.getElementById('step2Node'),
  
  // Catalog
  phonesGrid: document.getElementById('phonesGrid'),
  catalogSearch: document.getElementById('catalogSearch'),
  specsModal: document.getElementById('specsModal'),
  specsModalBody: document.getElementById('specsModalBody'),
  specsModalTitle: document.getElementById('specsModalTitle')
};

// Initial setup
document.addEventListener('DOMContentLoaded', async () => {
  setupNavigation();
  setupApiKeyManagement();
  setupChat();
  setupReviews();
  setupCatalog();
  
  // Check key status on startup
  await refreshKeyStatus();
  await loadPhones();
});

// ==========================================
// 1. API Key Management
// ==========================================
function setupApiKeyManagement() {
  elements.apiKeyInput.value = userApiKey;
  
  const providerGroq = document.getElementById('providerGroq');
  const providerLocal = document.getElementById('providerLocalhost');
  const localSettings = document.getElementById('localhostSettings');
  const localBaseUrlInput = document.getElementById('localBaseUrl');
  const localModelInput = document.getElementById('localModelName');
  const getFreeKeyLink = document.getElementById('getFreeKeyLink');
  const apiKeyLabel = document.getElementById('apiKeyLabel');

  const groqModelSelect = document.getElementById('groqModelSelect');
  const groqModelGroup = document.getElementById('groqModelGroup');

  localBaseUrlInput.value = localBaseUrl;
  localModelInput.value = localModelName;
  if (localModelName && [...groqModelSelect.options].some(o => o.value === localModelName)) {
    groqModelSelect.value = localModelName;
  }

  function updateProviderUI() {
    if (providerMode === 'localhost') {
      providerLocal.checked = true;
      localSettings.style.display = 'flex';
      groqModelGroup.style.display = 'none';
      getFreeKeyLink.style.display = 'none';
      apiKeyLabel.textContent = 'API Key (Optional for Localhost)';
    } else {
      providerGroq.checked = true;
      localSettings.style.display = 'none';
      groqModelGroup.style.display = 'flex';
      getFreeKeyLink.style.display = 'block';
      apiKeyLabel.textContent = 'Groq API Key';
    }
  }

  providerGroq.addEventListener('change', () => {
    providerMode = 'groq';
    updateProviderUI();
  });

  providerLocal.addEventListener('change', () => {
    providerMode = 'localhost';
    updateProviderUI();
  });

  updateProviderUI();

  async function detectAvailableModels() {
    const key = elements.apiKeyInput.value.trim();
    if (!key) {
      showKeyFeedback('Enter your API key first to detect models', 'error');
      return;
    }
    showKeyFeedback('Detecting active models on your account...', 'info');
    try {
      const res = await fetch('/api/models', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: key })
      });
      const data = await res.json();
      if (data.models && data.models.length > 0) {
        groqModelSelect.innerHTML = data.models.map(m => 
          `<option value="${escapeHtml(m)}">${escapeHtml(m)}</option>`
        ).join('');
        showKeyFeedback(`Found ${data.models.length} active models! Selected: ${data.models[0]}`, 'success');
      } else {
        showKeyFeedback('Could not fetch models. Check your API key.', 'error');
      }
    } catch (err) {
      showKeyFeedback('Detection error: ' + err.message, 'error');
    }
  }

  document.getElementById('detectModelsBtn')?.addEventListener('click', () => detectAvailableModels());
  elements.apiKeyPill.addEventListener('click', () => openApiKeyModal());
  document.getElementById('bannerSetKeyBtn')?.addEventListener('click', () => openApiKeyModal());
  document.getElementById('closeKeyModalBtn').addEventListener('click', () => closeApiKeyModal());
  
  // Toggle password visibility
  document.getElementById('toggleKeyVisibility').addEventListener('click', (e) => {
    const isPass = elements.apiKeyInput.type === 'password';
    elements.apiKeyInput.type = isPass ? 'text' : 'password';
    e.target.textContent = isPass ? '🔒' : '👁️';
  });

  // Test & Save Key
  document.getElementById('testAndSaveKeyBtn').addEventListener('click', async () => {
    const key = elements.apiKeyInput.value.trim();
    const mode = providerGroq.checked ? 'groq' : 'localhost';
    const baseUrl = mode === 'localhost' ? localBaseUrlInput.value.trim() : null;
    const model = mode === 'localhost' ? localModelInput.value.trim() : groqModelSelect.value;

    if (mode === 'groq' && !key) {
      showKeyFeedback('Please enter your Groq API key', 'error');
      return;
    }
    showKeyFeedback(mode === 'localhost' ? 'Testing connection to localhost...' : `Testing Groq connection (${model})...`, 'info');
    try {
      const res = await fetch('/api/verify-key', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          api_key: key || undefined,
          base_url: baseUrl || undefined,
          model: model || undefined
        })
      });
      const data = await res.json();
      if (data.valid) {
        if (data.available_models && data.available_models.length > 0 && mode === 'groq') {
          groqModelSelect.innerHTML = data.available_models.map(m => 
            `<option value="${escapeHtml(m)}" ${m === data.model ? 'selected' : ''}>${escapeHtml(m)}</option>`
          ).join('');
        }
        if (data.model && mode === 'groq') {
          groqModelSelect.value = data.model;
        }
        saveSettings(key, mode, baseUrl, data.model || model);
        showKeyFeedback(`Verified! Connected to ${data.model} ${data.base_url ? '(' + data.base_url + ')' : ''}`, 'success');
        setTimeout(() => closeApiKeyModal(), 1200);
      } else {
        showKeyFeedback(`Connection failed: ${data.error}`, 'error');
      }
    } catch (err) {
      showKeyFeedback(`Network error: ${err.message}`, 'error');
    }
  });

  // Save Without Testing
  document.getElementById('saveKeyBtn').addEventListener('click', () => {
    const key = elements.apiKeyInput.value.trim();
    const mode = providerGroq.checked ? 'groq' : 'localhost';
    const baseUrl = mode === 'localhost' ? localBaseUrlInput.value.trim() : null;
    const model = mode === 'localhost' ? localModelInput.value.trim() : groqModelSelect.value;
    saveSettings(key, mode, baseUrl, model);
    showKeyFeedback('Settings saved locally.', 'success');
    setTimeout(() => closeApiKeyModal(), 800);
  });

  // Reset
  document.getElementById('clearKeyBtn').addEventListener('click', () => {
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(STORAGE_PROVIDER);
    localStorage.removeItem(STORAGE_BASE_URL);
    localStorage.removeItem(STORAGE_MODEL);
    userApiKey = '';
    providerMode = 'groq';
    elements.apiKeyInput.value = '';
    updateProviderUI();
    showKeyFeedback('Settings reset.', 'info');
    refreshKeyStatus();
  });
}

function openApiKeyModal() {
  elements.apiKeyInput.value = userApiKey;
  elements.apiKeyFeedback.textContent = '';
  elements.apiKeyModal.classList.add('open');
}

function closeApiKeyModal() {
  elements.apiKeyModal.classList.remove('open');
}

function saveSettings(key, mode, baseUrl, model) {
  userApiKey = key;
  providerMode = mode;
  localStorage.setItem(STORAGE_PROVIDER, mode);

  if (key) {
    localStorage.setItem(STORAGE_KEY, key);
  } else {
    localStorage.removeItem(STORAGE_KEY);
  }

  if (baseUrl) {
    localBaseUrl = baseUrl;
    localStorage.setItem(STORAGE_BASE_URL, baseUrl);
  }
  if (model) {
    localModelName = model;
    localStorage.setItem(STORAGE_MODEL, model);
  }
  refreshKeyStatus();
}

function showKeyFeedback(message, type) {
  elements.apiKeyFeedback.textContent = message;
  elements.apiKeyFeedback.style.color = type === 'success' ? 'var(--success)' : type === 'error' ? 'var(--danger)' : 'var(--text-secondary)';
}

async function refreshKeyStatus() {
  try {
    const headers = getRequestHeaders();
    const res = await fetch('/api/key-status', { headers });
    const data = await res.json();
    
    if (providerMode === 'localhost') {
      elements.apiKeyDot.className = 'status-dot active';
      elements.apiKeyText.textContent = 'Host: Localhost';
      elements.apiBanner.classList.add('hidden');
    } else if (userApiKey) {
      elements.apiKeyDot.className = 'status-dot active';
      elements.apiKeyText.textContent = 'API Key: Configured';
      elements.apiBanner.classList.add('hidden');
    } else if (data.has_server_key) {
      elements.apiKeyDot.className = 'status-dot active';
      elements.apiKeyText.textContent = 'API Key: Server Default';
      elements.apiBanner.classList.add('hidden');
    } else {
      elements.apiKeyDot.className = 'status-dot inactive';
      elements.apiKeyText.textContent = 'API Key: Not Set';
      elements.apiBanner.classList.remove('hidden');
    }

    if (data.has_server_key) {
      elements.serverKeyNotice.textContent = 'A default Groq key is detected on the server .env. Your custom settings take precedence.';
    } else {
      elements.serverKeyNotice.textContent = 'Configure Groq API key or Localhost (Ollama) to start querying.';
    }
  } catch (err) {
    console.warn('Status check error:', err);
  }
}

function getRequestHeaders() {
  const headers = { 'Content-Type': 'application/json' };
  if (providerMode === 'localhost') {
    headers['X-Base-URL'] = localBaseUrl;
    if (userApiKey) headers['X-API-Key'] = userApiKey;
  } else if (userApiKey) {
    headers['X-API-Key'] = userApiKey;
  }
  return headers;
}

// ==========================================
// 2. Navigation
// ==========================================
function setupNavigation() {
  elements.tabButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.dataset.tab;
      elements.tabButtons.forEach(b => b.classList.remove('active'));
      elements.tabPanes.forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(target).classList.add('active');
    });
  });
}

// ==========================================
// 3. Conversational RAG Chatbot
// ==========================================
function setupChat() {
  elements.chatSendBtn.addEventListener('click', () => sendChatMessage());
  elements.chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendChatMessage();
    }
  });

  elements.clearChatBtn.addEventListener('click', () => {
    elements.chatMessages.innerHTML = `
      <div class="chat-bubble assistant">
        <p>👋 Hello! I am your <strong>Samsung Phone Intelligence Assistant</strong>.</p>
        <p style="margin-top: 0.5rem; font-size: 0.85rem; color: var(--text-secondary);">
          Ask me about specifications, camera details, battery comparisons, or prices for any Samsung Galaxy phone. All answers are grounded strictly in the scraped database.
        </p>
      </div>
    `;
    sessionId = 'session_' + Math.random().toString(36).substring(2, 9);
  });

  elements.promptChips.forEach(chip => {
    chip.addEventListener('click', () => {
      elements.chatInput.value = chip.textContent.trim();
      sendChatMessage();
    });
  });
}

async function sendChatMessage() {
  const text = elements.chatInput.value.trim();
  if (!text) return;

  // Append user bubble
  appendChatBubble(text, 'user');
  elements.chatInput.value = '';
  elements.chatSendBtn.disabled = true;

  // Append typing indicator bubble
  const typingBubble = appendChatBubble('Thinking and retrieving database context...', 'assistant', true);

  try {
    const modelToUse = providerMode === 'localhost' ? localModelName : (document.getElementById('groqModelSelect')?.value || 'llama-3.1-8b-instant');
    const payload = {
      question: text,
      session_id: sessionId,
      api_key: userApiKey || undefined,
      base_url: providerMode === 'localhost' ? localBaseUrl : undefined,
      model: modelToUse
    };

    const res = await fetch('/chat', {
      method: 'POST',
      headers: getRequestHeaders(),
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    typingBubble.remove();

    if (!res.ok) {
      const errorMsg = data.detail || 'Failed to get answer';
      appendChatBubble(`⚠️ ${errorMsg}`, 'assistant');
      if (errorMsg.includes('GROQ_API_KEY')) {
        openApiKeyModal();
      }
      return;
    }

    appendChatBubble(data.answer, 'assistant', false, data.sources);
  } catch (err) {
    typingBubble.remove();
    appendChatBubble(`⚠️ Error contacting server: ${err.message}`, 'assistant');
  } finally {
    elements.chatSendBtn.disabled = false;
    elements.chatInput.focus();
  }
}

function appendChatBubble(text, role, isTyping = false, sources = []) {
  const bubble = document.createElement('div');
  bubble.className = `chat-bubble ${role}`;

  if (isTyping) {
    bubble.innerHTML = `<span class="spinner" style="vertical-align: middle; margin-right: 8px;"></span> ${text}`;
  } else {
    bubble.innerHTML = renderMarkdown(text);
    if (sources && sources.length > 0) {
      const sourcesDiv = document.createElement('div');
      sourcesDiv.className = 'msg-sources';
      sourcesDiv.innerHTML = '<strong>Context:</strong> ' + sources.map(s => `<span class="source-tag">${escapeHtml(s)}</span>`).join('');
      bubble.appendChild(sourcesDiv);
    }
  }

  elements.chatMessages.appendChild(bubble);
  elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
  return bubble;
}

// ==========================================
// 4. Multi-Agent Review Pipeline
// ==========================================
function setupReviews() {
  elements.reviewBtn.addEventListener('click', () => runReviewPipeline());

  elements.copyReviewBtn.addEventListener('click', () => {
    const text = elements.reviewContent.dataset.rawMarkdown || elements.reviewContent.innerText;
    navigator.clipboard.writeText(text);
    const orig = elements.copyReviewBtn.textContent;
    elements.copyReviewBtn.textContent = '✅ Copied!';
    setTimeout(() => elements.copyReviewBtn.textContent = orig, 1800);
  });
}

async function runReviewPipeline() {
  const phone = elements.phoneSelect.value.trim();
  if (!phone) {
    alert('Please select a phone model first.');
    return;
  }

  elements.reviewBtn.disabled = true;
  elements.step1Node.className = 'pipeline-node running';
  elements.step2Node.className = 'pipeline-node';

  elements.reviewHeader.textContent = `Generating review for ${phone}...`;
  elements.reviewContent.innerHTML = `
    <div style="text-align: center; padding: 3rem; color: var(--text-secondary);">
      <div class="spinner" style="width: 32px; height: 32px; margin-bottom: 1rem;"></div>
      <p>Multi-Agent pipeline executing: SpecRetrievalAgent is querying PostgreSQL/SQLite...</p>
    </div>
  `;

  try {
    // Step 1 done animation
    setTimeout(() => {
      elements.step1Node.className = 'pipeline-node done';
      elements.step2Node.className = 'pipeline-node running';
    }, 600);

    const modelToUse = providerMode === 'localhost' ? localModelName : (document.getElementById('groqModelSelect')?.value || 'llama-3.1-8b-instant');
    const payload = {
      phone: phone,
      api_key: userApiKey || undefined,
      base_url: providerMode === 'localhost' ? localBaseUrl : undefined,
      model: modelToUse
    };

    const res = await fetch('/review', {
      method: 'POST',
      headers: getRequestHeaders(),
      body: JSON.stringify(payload)
    });

    const data = await res.json();

    if (!res.ok) {
      elements.step1Node.className = 'pipeline-node';
      elements.step2Node.className = 'pipeline-node';
      elements.reviewHeader.textContent = 'Review Generation Error';
      elements.reviewContent.innerHTML = `<div style="color: var(--danger); padding: 1rem;">⚠️ ${data.detail || 'Failed to generate review'}</div>`;
      if ((data.detail || '').includes('GROQ_API_KEY')) {
        openApiKeyModal();
      }
      return;
    }

    elements.step1Node.className = 'pipeline-node done';
    elements.step2Node.className = 'pipeline-node done';

    elements.reviewHeader.textContent = `${data.phone} - Comprehensive Review`;
    elements.reviewContent.dataset.rawMarkdown = data.review;
    elements.reviewContent.innerHTML = renderMarkdown(data.review);
    elements.copyReviewBtn.style.display = 'block';

  } catch (err) {
    elements.reviewHeader.textContent = 'Review Failed';
    elements.reviewContent.innerHTML = `<div style="color: var(--danger); padding: 1rem;">⚠️ ${err.message}</div>`;
  } finally {
    elements.reviewBtn.disabled = false;
  }
}

// ==========================================
// 5. Phone Catalog & Specs Explorer
// ==========================================
function setupCatalog() {
  elements.catalogSearch.addEventListener('input', (e) => {
    filterCatalog(e.target.value);
  });

  document.getElementById('closeSpecsModalBtn').addEventListener('click', () => {
    elements.specsModal.classList.remove('open');
  });
}

async function loadPhones() {
  try {
    const res = await fetch('/phones');
    if (!res.ok) return;
    cachedPhones = await res.json();

    // Populate review select
    elements.phoneSelect.innerHTML = cachedPhones.map(p => 
      `<option value="${escapeHtml(p.name)}">${escapeHtml(p.name)}</option>`
    ).join('');

    renderCatalogGrid(cachedPhones);
  } catch (err) {
    console.error('Failed to load phones:', err);
  }
}

function renderCatalogGrid(phones) {
  if (phones.length === 0) {
    elements.phonesGrid.innerHTML = `
      <div style="grid-column: 1 / -1; text-align: center; color: var(--text-muted); padding: 3rem;">
        No phones found in database. Run database ingestion to populate records.
      </div>
    `;
    return;
  }

  elements.phonesGrid.innerHTML = phones.map(p => `
    <div class="phone-card">
      <div>
        <div class="phone-card-title">${escapeHtml(p.name)}</div>
        <div style="font-size: 0.75rem; color: var(--text-muted); margin: 0.25rem 0 0.75rem 0;">
          ${escapeHtml(p.announced || 'Announcement Date N/A')}
        </div>
        <div class="specs-pills">
          ${p.battery_mah ? `<span class="spec-pill">🔋 ${p.battery_mah} mAh</span>` : ''}
          ${p.display_inches ? `<span class="spec-pill">📱 ${p.display_inches}"</span>` : ''}
          ${p.ram_gb ? `<span class="spec-pill">⚡ ${p.ram_gb} GB RAM</span>` : ''}
          ${p.price ? `<span class="spec-pill">💰 ${escapeHtml(p.price)}</span>` : ''}
        </div>
      </div>
      <div class="phone-card-actions">
        <button class="btn-card" onclick="viewPhoneSpecs('${escapeHtml(p.name)}')">🔍 View Specs</button>
        <button class="btn-card" onclick="reviewThisPhone('${escapeHtml(p.name)}')">✍️ Review</button>
      </div>
    </div>
  `).join('');
}

function filterCatalog(term) {
  const query = term.toLowerCase().trim();
  const filtered = cachedPhones.filter(p => p.name.toLowerCase().includes(query));
  renderCatalogGrid(filtered);
}

window.viewPhoneSpecs = async function(phoneName) {
  elements.specsModalTitle.textContent = phoneName;
  elements.specsModalBody.innerHTML = `<div style="text-align: center; padding: 2rem;"><span class="spinner"></span> Loading specs...</div>`;
  elements.specsModal.classList.add('open');

  try {
    const res = await fetch(`/phones/${encodeURIComponent(phoneName)}`);
    const data = await res.json();
    if (!res.ok) {
      elements.specsModalBody.innerHTML = `<p style="color: var(--danger)">Error: ${data.detail}</p>`;
      return;
    }

    let html = `<div style="display: flex; flex-direction: column; gap: 1rem;">`;
    for (const [category, rows] of Object.entries(data.specs)) {
      html += `
        <div style="background: var(--bg-secondary); border-radius: 8px; padding: 0.75rem 1rem; border: 1px solid var(--border-color);">
          <h4 style="color: #38bdf8; font-size: 0.88rem; margin-bottom: 0.5rem; text-transform: uppercase; letter-spacing: 0.05em;">${escapeHtml(category)}</h4>
          <table style="width: 100%; border-collapse: collapse; font-size: 0.8rem;">
            <tbody>
              ${Object.entries(rows).map(([k, v]) => `
                <tr style="border-bottom: 1px solid rgba(255, 255, 255, 0.04);">
                  <td style="color: var(--text-muted); padding: 0.35rem 0.5rem 0.35rem 0; width: 35%;">${escapeHtml(k)}</td>
                  <td style="color: var(--text-primary); padding: 0.35rem 0;">${escapeHtml(v)}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      `;
    }
    html += `</div>`;
    elements.specsModalBody.innerHTML = html;
  } catch (err) {
    elements.specsModalBody.innerHTML = `<p style="color: var(--danger)">Failed to fetch specs: ${err.message}</p>`;
  }
};

window.reviewThisPhone = function(phoneName) {
  elements.phoneSelect.value = phoneName;
  document.querySelector('[data-tab="agentTab"]').click();
  runReviewPipeline();
};

// ==========================================
// 6. Helpers & Markdown Formatter
// ==========================================
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function renderMarkdown(md) {
  if (!md) return '';
  let html = escapeHtml(md);

  // Headers
  html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
  html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
  html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');

  // Bold & Italic
  html = html.replace(/\*\*(.*?)\*\*/gim, '<strong>$1</strong>');
  html = html.replace(/\*(.*?)\*/gim, '<em>$1</em>');

  // Bullet items
  html = html.replace(/^\s*[-*]\s+(.*)$/gim, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>)/gims, '<ul>$1</ul>');

  // Line breaks & paragraphs
  html = html.split('\n\n').map(p => {
    if (p.startsWith('<h2>') || p.startsWith('<h3>') || p.startsWith('<ul>')) return p;
    return `<p>${p.replace(/\n/g, '<br>')}</p>`;
  }).join('');

  return html;
}
