// =============================================
// Stock Voice — Main Script
// =============================================

// ---- State ----
let currentUser = null;

// ---- Helpers ----
function isValidFotoUrl(str) {
    return typeof str === 'string' && str.startsWith('http');
}
let consultations = [];

// ---- DOM refs ----
const userSelectScreen = document.getElementById('user-select-screen');
const mainApp          = document.getElementById('main-app');
const container        = document.getElementById('cards-container');
const refreshBtn       = document.getElementById('refresh-btn');
const refreshIcon      = document.getElementById('refresh-icon');
const currentUserLabel = document.getElementById('current-user-label');
const headerSubtitle   = document.getElementById('header-subtitle');

// ---- User Config ----
const USER_DISPLAY = {
    ignacio:    { label: 'Ignacio',     role: 'La Reina',           color: 'ignacio' },
    robinson:   { label: 'Robinson',    role: 'Respuestas Externas', color: 'robinson' },
    callcenter: { label: 'Call Center', role: 'Subir Fotos',         color: 'callcenter' },
};

// ---- Quick Status Buttons (K / M) ----
const QUICK_STATUS = [
    { icon: '✅', text: 'Disponible Nacional' },
    { icon: '♻️', text: 'Disponible Re-Acondicionado' },
    { icon: '🚢', text: 'Importación' },
    { icon: '❌', text: 'No disponible' },
    { icon: '⚡', text: 'Parcialmente Disponible' },
    { icon: '💬', text: 'Otra respuesta' },
    { icon: '📸', text: 'Necesita Foto' },
];

// ---- Quick Explanation Chips (L / N) — MULTI-SELECT ----
const QUICK_CHIPS = [
    'Solo piezas',
    'Precio de Panal',
    '12 días',
    '30 días',
    'Mismo dia',
    'En 3 horas',
    'En Sucursal',
    'Sin Base',
    'CV',
    'YK',
    'LCH',
];

// ---- Chip multi-select state ----
let selectedChips     = {}; // pending cards: { cardIdx: Set<string> }
let editSelectedChips = {}; // history edit:  { histIdx: Set<string> }

// ---- Speech Recognition ----
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;
if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.lang = 'es-CL';
    recognition.interimResults = false;
    recognition.continuous = false;
}

// =============================================
// USER SELECTION
// =============================================
window.selectUser = function(user) {
    currentUser = user;
    localStorage.setItem('stockvoice_user', user);
    if (user === 'callcenter') {
        showCCScreen();
    } else {
        showMainApp();
        fetchConsultations().then(() => {
            lastKnownCount = consultations.length;
            requestNotificationPermission();
            startPolling();
        });
    }
};

window.changeUser = function() {
    currentUser = null;
    if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
    document.getElementById('main-app').style.display      = 'none';
    document.getElementById('history-screen').style.display = 'none';
    document.getElementById('cc-screen').style.display      = 'none';
    userSelectScreen.style.display = 'flex';
};

function showMainApp() {
    userSelectScreen.style.display = 'none';
    mainApp.style.display = 'block';

    const cfg = USER_DISPLAY[currentUser];
    currentUserLabel.textContent = cfg.label;
    headerSubtitle.textContent   = `Pendientes — ${cfg.role}`;
}

// =============================================
// DATA FETCHING
// =============================================
async function fetchConsultations() {
    refreshIcon.classList.add('fa-spin');
    const loader = document.getElementById('main-loader');
    if (loader) loader.style.display = 'block';

    try {
        const res  = await fetch(`/api/pending?user=${currentUser}`);
        const data = await res.json();

        if (data.error) throw new Error(data.error);

        consultations = data;
        renderCards();

        const cfg = USER_DISPLAY[currentUser];
        headerSubtitle.textContent = `${consultations.length} pendiente${consultations.length !== 1 ? 's' : ''} — ${cfg.role}`;

        // Also fetch recent folios to show below
        if (currentUser !== 'callcenter') {
            fetch('/api/recent-folios').then(r => r.json()).then(rfData => {
                const rfDiv = document.getElementById('pending-recent-folios');
                if (rfDiv && !rfData.error) {
                    rfDiv.innerHTML = getRecentFoliosHTML(rfData);
                }
            }).catch(console.error);
        }
    } catch (err) {
        console.error('Error:', err);
        container.innerHTML = `<p style="text-align:center; color:var(--danger); padding:2rem;">Error al cargar datos.<br><small>${err.message}</small></p>`;
    } finally {
        refreshIcon.classList.remove('fa-spin');
        const loader2 = document.getElementById('main-loader');
        if (loader2) loader2.style.display = 'none';
    }
}

// =============================================
// RENDER CARDS
// =============================================
function renderCards() {
    if (consultations.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-check-circle"></i>
                <h2>¡Todo al día!</h2>
                <p>No hay consultas pendientes en este momento.</p>
            </div>
            <div id="pending-recent-folios"></div>`;
        return;
    }

    container.innerHTML = consultations.map((item, idx) => {

        // Other user's response block
        let otherBlock = '';
        if (item.other_status || item.other_resp) {
            const otherClass = item.other_user.toLowerCase() === 'ignacio' ? 'ignacio' : 'robinson';
            otherBlock = `
                <div class="other-response other-response--${otherClass}">
                    <i class="fas fa-user-check"></i>
                    <div class="other-response-text">
                        <div class="other-response-name">${item.other_user} respondió</div>
                        <div class="other-response-status">${item.other_status || '—'}</div>
                        ${item.other_resp ? `<div class="other-response-detail">${item.other_resp}</div>` : ''}
                    </div>
                </div>`;
        }

        // Duplicates block
        let dupBlock = '';
        if (item.duplicates && item.duplicates.length > 0) {
            dupBlock = `
                <div class="duplicates">
                    <i class="fas fa-exclamation-triangle"></i>
                    Ya respondido antes:
                    ${item.duplicates.map(d => `<br>• Fila ${d.row}: ${d.response}`).join('')}
                </div>`;
        }

        // Quick status buttons
        const statusBtns = QUICK_STATUS.map(s =>
            `<button class="status-btn" onclick="selectStatus(${idx}, '${s.text}')">${s.icon} ${s.text}</button>`
        ).join('');

        // Quick explanation chips — multi-select
        const chips = QUICK_CHIPS.map(c =>
            `<button class="chip" data-card="${idx}" data-chip="${c}" onclick="toggleChip(${idx}, '${c.replace(/'/g, "\\'")}')"> ${c}</button>`
        ).join('');

        return `
        <div class="card" id="card-${idx}" style="animation-delay: ${idx * 0.05}s">
            <div class="card-header">
            <div style="display:flex; flex-direction:column; gap:3px;">
                <span class="badge">Folio ${item.folio || 'S/N'}</span>
                ${item.fecha ? `<span class="fecha-badge"><i class="fas fa-calendar-alt"></i> ${item.fecha}</span>` : ''}
            </div>
            <span class="ejecutivo-badge"><i class="fas fa-headset" style="margin-right:4px;"></i>${item.ejecutivo || '—'}</span>
        </div>

            <h2 class="product-title">${item.producto}</h2>

            <div class="product-details">
                <div class="detail-item">
                    <span class="detail-label">Vehículo</span>
                    <span class="detail-value">${item.marca_modelo_año || '—'}</span>
                </div>
                <div class="detail-item">
                    <span class="detail-label">Lado</span>
                    <span class="detail-value">${item.lado || '—'}</span>
                </div>
                <div class="detail-item" style="grid-column: span 2;">
                    <span class="detail-label">Características</span>
                    <span class="detail-value">${item.caracteristicas || '—'}</span>
                </div>
            </div>

            ${(item.fotos || []).filter(isValidFotoUrl).length > 0 ? `
            <div class="fotos-gallery" style="display:flex; gap:0.5rem; flex-wrap:wrap; margin-bottom:0.75rem;">
                ${(item.fotos || []).map((url, i) => isValidFotoUrl(url) ? `
                <a href="${url}" target="_blank" class="foto-preview-btn" style="margin-bottom:0;">
                    <i class="fas fa-image"></i> Foto ${i+1}
                </a>` : '').join('')}
            </div>` : ''}

            ${otherBlock}
            ${dupBlock}

            <div class="action-area">

                <!-- Status quick buttons -->
                <div class="status-grid" id="status-grid-${idx}">
                    ${statusBtns}
                </div>

                <!-- Quick explanation chips -->
                <div class="quick-chips-label">Explicación rápida</div>
                <div class="quick-chips">${chips}</div>

                <!-- Explanation textarea + voice -->
                <div class="input-group">
                    <textarea id="response-${idx}" placeholder="Escribe o dicta la explicación..."></textarea>
                    <button class="voice-btn" id="voice-btn-${idx}" onclick="startVoice(${idx})" title="Dictado por voz">
                        <i class="fas fa-microphone"></i>
                    </button>
                </div>

                <!-- Link field -->
                <div class="link-group">
                    <i class="fas fa-link"></i>
                    <input type="url" id="link-${idx}" placeholder="Pega el link de cotización (opcional)..." />
                </div>

                <button class="submit-btn" id="submit-${idx}" onclick="submitResponse(${idx})">
                    <i class="fas fa-paper-plane"></i> Enviar Respuesta
                </button>
            </div>
        </div>`;
    }).join('') + `<div id="pending-recent-folios"></div>`;

    selectedStatuses = {};
}

// =============================================
// INTERACTIONS
// =============================================
let selectedStatuses = {};

window.selectStatus = function(idx, status) {
    selectedStatuses[idx] = status;
    document.querySelectorAll(`#status-grid-${idx} .status-btn`).forEach(btn => {
        // Match by stripping the emoji prefix
        const btnText = btn.innerText.replace(/^[\u{1F000}-\u{1FFFF}\u2600-\u27FF]\s*/u, '').trim();
        btn.classList.toggle('selected', btnText === status);
    });
};

window.fillChip = function(idx, text) {
    document.getElementById(`response-${idx}`).value = text;
};

window.startVoice = function(idx) {
    if (!recognition) {
        alert('Tu navegador no soporta dictado por voz. Usa Chrome o Safari.');
        return;
    }
    const btn      = document.getElementById(`voice-btn-${idx}`);
    const textarea = document.getElementById(`response-${idx}`);

    btn.classList.add('recording');
    recognition.start();

    recognition.onresult = (e) => {
        textarea.value = e.results[0][0].transcript;
        btn.classList.remove('recording');
    };
    recognition.onerror = () => {
        btn.classList.remove('recording');
    };
    recognition.onspeechend = () => {
        recognition.stop();
        btn.classList.remove('recording');
    };
};

// ---- Multi-select chip toggle (pending cards) ----
window.toggleChip = function(idx, chip) {
    if (!selectedChips[idx]) selectedChips[idx] = new Set();
    const set = selectedChips[idx];
    if (set.has(chip)) { set.delete(chip); } else { set.add(chip); }
    // Reflect on button
    document.querySelectorAll(`[data-card="${idx}"][data-chip]`).forEach(btn => {
        btn.classList.toggle('selected', set.has(btn.dataset.chip));
    });
    // Update textarea preserving chip order
    const ta = document.getElementById(`response-${idx}`);
    if (ta) ta.value = QUICK_CHIPS.filter(c => set.has(c)).join(', ');
};

// ---- Multi-select chip toggle (history edit) ----
window.toggleEditChip = function(idx, chip) {
    if (!editSelectedChips[idx]) editSelectedChips[idx] = new Set();
    const set = editSelectedChips[idx];
    if (set.has(chip)) { set.delete(chip); } else { set.add(chip); }
    document.querySelectorAll(`[data-ecard="${idx}"][data-chip]`).forEach(btn => {
        btn.classList.toggle('selected', set.has(btn.dataset.chip));
    });
    const ta = document.getElementById(`edit-resp-${idx}`);
    if (ta) ta.value = QUICK_CHIPS.filter(c => set.has(c)).join(', ');
};

window.submitResponse = async function(idx) {
    const status      = selectedStatuses[idx];
    const responseText= document.getElementById(`response-${idx}`).value.trim();
    const linkVal     = document.getElementById(`link-${idx}`).value.trim();
    const submitBtn   = document.getElementById(`submit-${idx}`);
    const card        = document.getElementById(`card-${idx}`);

    if (!status) {
        alert('Selecciona un estado primero (Disponible, No disponible, etc.)');
        return;
    }

    submitBtn.disabled = true;
    submitBtn.innerHTML = '<div class="loader" style="width:18px;height:18px;border-width:2px;display:inline-block;"></div> Enviando...';

    try {
        const res = await fetch('/api/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                row_index: consultations[idx].row_index,
                status,
                response: responseText,
                link: linkVal,
                user: currentUser,
            }),
        });

        const data = await res.json();

        if (data.success) {
            card.style.transform = 'translateX(110%)';
            card.style.opacity   = '0';
            setTimeout(() => {
                consultations.splice(idx, 1);
                renderCards();
                const cfg = USER_DISPLAY[currentUser];
                headerSubtitle.textContent = `${consultations.length} pendiente${consultations.length !== 1 ? 's' : ''} — ${cfg.role}`;
            }, 320);
        } else {
            throw new Error(data.error || 'Error desconocido');
        }
    } catch (err) {
        alert(`Error: ${err.message}`);
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<i class="fas fa-paper-plane"></i> Enviar Respuesta';
    }
};

// =============================================
// CALL CENTER SCREEN
// =============================================
const ccScreen  = document.getElementById('cc-screen');
const ccResults = document.getElementById('cc-results');

let ccSearchTimer = null;
let currentFotoRowIndex = null;
let currentFotoInfo    = { rowIndex: null, folio: '', producto: '', cardIdx: null };

function showCCScreen() {
    userSelectScreen.style.display  = 'none';
    mainApp.style.display           = 'none';
    document.getElementById('history-screen').style.display = 'none';
    ccScreen.style.display          = 'block';
    document.getElementById('cc-search').value = '';
    ccResults.innerHTML = `<div style="text-align:center;padding:1.5rem;">
        <div class="loader" style="display:inline-block;"></div></div>`;
    // Load recent folios immediately
    fetchRecentFolios();
}

async function fetchRecentFolios() {
    try {
        const res  = await fetch('/api/recent-folios');
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        renderRecentFolios(data);
    } catch(err) {
        ccResults.innerHTML = `<p style="color:var(--text-muted);text-align:center;padding:1rem;font-size:0.88rem;">
            Escribe para buscar</p>`;
    }
}

function getRecentFoliosHTML(items) {
    if (!items || !items.length) {
        return '<p style="text-align:center;color:var(--text-muted);padding:1rem;font-size:0.88rem;">No hay folios recientes</p>';
    }
    const header = `<p style="font-size:0.72rem;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.7rem;margin-top:2rem;">Folios recientes rápidos</p>`;
    const grid   = `<div class="recent-folios-grid" style="padding-bottom:2rem;">
        ${items.map((item, idx) => {
            const hasPhoto = (item.fotos || []).some(isValidFotoUrl);
            const hasAnswer = !!(item.la_reina || item.externo);
            const isCC = currentUser === 'callcenter';
            const clickAction = isCC
                ? `showSingleFolio(${JSON.stringify(item).replace(/"/g, '&quot;')}, ${idx})`
                : `openHistoryForFolio('${item.folio}')`;
            
            return `
            <button class="recent-folio-chip" onclick="${clickAction}">
                <span class="rfc-folio">${item.folio}</span>
                <span class="rfc-product">${(item.producto || '').slice(0, 28)}</span>
                <div class="rfc-status">
                    ${hasPhoto ? `<span class="rfc-dot rfc-dot--green" title="Con foto"></span>` : `<span class="rfc-dot rfc-dot--empty" title="Sin foto"></span>`}
                    ${hasAnswer ? `<span class="rfc-dot rfc-dot--green" title="Con respuesta"></span>` : `<span class="rfc-dot rfc-dot--red" title="Sin respuesta"></span>`}
                </div>
            </button>`;
        }).join('')}
    </div>`;
    return header + grid;
}

window.openHistoryForFolio = function(folio) {
    showHistory();
    setTimeout(() => {
        const hSearch = document.getElementById('history-search');
        if (hSearch) {
            hSearch.value = folio;
            hSearch.dispatchEvent(new Event('input'));
        }
    }, 600); // Give API enough time to load History
};

function renderRecentFolios(items) {
    ccResults.innerHTML = getRecentFoliosHTML(items);
}

window.showSingleFolio = function(item, idx) {
    renderCCResults([item]);
};

window.debouncedSearch = function(val) {
    clearTimeout(ccSearchTimer);
    if (val.length < 2) {
        ccResults.innerHTML = `<p style="text-align:center;color:var(--text-muted);padding:1rem;font-size:0.9rem;">
            Escribe al menos 2 caracteres</p>`;
        return;
    }
    ccSearchTimer = setTimeout(() => searchConsultations(val), 500);
};

async function searchConsultations(q) {
    ccResults.innerHTML = `<div style="text-align:center;padding:1.5rem;">
        <div class="loader" style="display:inline-block;"></div></div>`;
    try {
        const res  = await fetch(`/api/consultations?q=${encodeURIComponent(q)}`);
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        renderCCResults(data);
    } catch(err) {
        ccResults.innerHTML = `<p style="color:var(--danger);text-align:center;padding:1rem;">Error: ${err.message}</p>`;
    }
}

function renderCCResults(items) {
    if (items.length === 0) {
        ccResults.innerHTML = `<div class="empty-state"><i class="fas fa-search"></i>
            <h2>Sin resultados</h2><p>Intenta con otro término.</p></div>`;
        return;
    }
    ccResults.innerHTML = items.map((item, idx) => `
        <div class="cc-card" id="cc-card-${idx}">
            <div class="card-header" style="margin-bottom:0.6rem;">
                <div style="display:flex;flex-direction:column;gap:3px;">
                    <span class="badge">Folio ${item.folio || 'S/N'}</span>
                    ${item.fecha ? `<span class="fecha-badge"><i class="fas fa-calendar-alt"></i> ${item.fecha}</span>` : ''}
                </div>
                <span class="ejecutivo-badge"><i class="fas fa-headset" style="margin-right:4px;"></i>${item.ejecutivo || '—'}</span>
            </div>
            <div style="font-weight:700;font-size:0.95rem;margin-bottom:3px;">${item.producto}</div>
            <div style="font-size:0.8rem;color:var(--text-muted);margin-bottom:0.75rem;">
                ${item.marca_modelo_año || ''} ${item.lado ? '· ' + item.lado : ''}
            </div>

            <!-- Respuestas de La Reina e Ignacio -->
            ${(item.la_reina || item.la_reina_resp || item.externo || item.robinson_resp) ? `
            <div class="cc-responses">
                ${item.la_reina || item.la_reina_resp ? `
                <div class="cc-response-row">
                    <span class="cc-resp-label" style="color:var(--ignacio);">La Reina</span>
                    <div class="cc-resp-content">
                        ${item.la_reina ? `<span class="status-pill status--blue">${item.la_reina}</span>` : ''}
                        ${item.la_reina_resp ? `<span class="cc-resp-text">${item.la_reina_resp}</span>` : ''}
                    </div>
                </div>` : ''}
                ${item.externo || item.robinson_resp ? `
                <div class="cc-response-row">
                    <span class="cc-resp-label" style="color:var(--robinson);">Externo</span>
                    <div class="cc-resp-content">
                        ${item.externo ? `<span class="status-pill status--green">${item.externo}</span>` : ''}
                        ${item.robinson_resp ? `<span class="cc-resp-text">${item.robinson_resp}</span>` : ''}
                    </div>
                </div>` : ''}
            </div>` : '<p style="font-size:0.8rem;color:var(--text-muted);margin-bottom:0.6rem;">Sin respuesta aún</p>'}

            ${(function(){
                const validFotos = (item.fotos || []).map((url, i) => ({url, i})).filter(f => isValidFotoUrl(f.url));
                if (validFotos.length > 0) {
                    return `
                    <div class="cc-fotos-grid" style="display:flex; gap:0.5rem; flex-wrap:wrap; margin-bottom:0.5rem;">
                        ${validFotos.map((f, arrayIdx) => `
                            <div class="foto-thumb-wrapper" style="display:flex; align-items:stretch; gap:0.2rem; min-width:130px; flex:1; background:var(--primary-dim); border:1px solid rgba(0,113,227,0.15); border-radius:var(--radius-sm); padding:2px;">
                                <a href="${f.url}" target="_blank" class="foto-preview-btn" style="margin-bottom:0; flex:1; justify-content:center; background:transparent; border:none; padding:0.4rem;">
                                    <i class="fas fa-image"></i> Foto ${arrayIdx+1}
                                </a>
                                <button class="delete-foto-btn" onclick="deleteFoto(${item.row_index}, ${f.i}, ${idx}, '${(item.folio||'').replace(/'/g,'')}', '${(item.producto||'').replace(/'/g,'').replace(/`/g,'')}')" title="Eliminar foto" style="background:rgba(255,59,48,0.1); border:none; color:var(--danger); border-radius:8px; width:34px; cursor:pointer;">
                                    <i class="fas fa-times"></i>
                                </button>
                            </div>
                        `).join('')}
                    </div>`;
                }
                return '';
            })()}

            <div style="display:flex; gap:0.5rem; margin-top:0.75rem;">
                ${(item.fotos || []).filter(isValidFotoUrl).length < 6 ? `
                <button class="cc-upload-btn" onclick="triggerFotoUpload(${item.row_index}, ${idx}, '${(item.folio||'').replace(/'/g,'')}', '${(item.producto||'').replace(/'/g,'').replace(/`/g,'')}')" style="flex:1;">
                    <i class="fas fa-camera"></i> Subir foto
                </button>` : `<p style="font-size:0.8rem; color:var(--text-muted); width:100%; text-align:center; padding:0.5rem 0;"><i class="fas fa-info-circle"></i> Límite de 6 fotos alcanzado.</p>`}
            </div>
            <div id="cc-status-${idx}" class="cc-upload-status"></div>
        </div>
    `).join('');
}

window.triggerFotoUpload = function(rowIndex, cardIdx, folio, producto) {
    currentFotoInfo = { rowIndex, folio: folio || '', producto: producto || '', cardIdx };
    currentFotoRowIndex = rowIndex;
    document.getElementById('foto-input').click();
};

window.handleFotoSelected = async function(event) {
    const file = event.target.files[0];
    if (!file) return;
    event.target.value = '';

    const cardIdx   = currentFotoInfo.cardIdx;
    const statusDiv = document.getElementById(`cc-status-${cardIdx}`);
    const btn       = document.querySelector(`#cc-card-${cardIdx} .cc-upload-btn`);

    statusDiv.innerHTML = '<div class="loader" style="display:inline-block;width:18px;height:18px;border-width:2px;margin-right:6px;"></div> Subiendo foto...';
    if (btn) { btn.disabled = true; }

    try {
        // Convert to base64
        const base64 = await fileToBase64(file);

        // Upload to imgbb
        const formData = new FormData();
        formData.append('key', window.IMGBB_KEY);
        formData.append('image', base64.split(',')[1]);

        const imgRes  = await fetch('https://api.imgbb.com/1/upload', { method: 'POST', body: formData });
        const imgData = await imgRes.json();

        if (!imgData.success) throw new Error('Error al subir la foto a imgbb');

        const fotoUrl = imgData.data.url;

        // Save URL to sheet
        const saveRes  = await fetch('/api/update-foto', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                row_index: currentFotoInfo.rowIndex,
                foto_url:  fotoUrl,
                folio:     currentFotoInfo.folio,
                producto:  currentFotoInfo.producto,
            }),
        });
        const saveData = await saveRes.json();
        if (!saveData.success) throw new Error(saveData.error);

        statusDiv.innerHTML = '<span style="color:var(--success);"><i class="fas fa-check"></i> Foto subida correctamente</span>';
        
        // Refresh active list smoothly after short delay
        setTimeout(() => {
            const currentSearch = document.getElementById('cc-search').value;
            if (currentSearch.length >= 2) searchConsultations(currentSearch);
            else fetchRecentFolios();
        }, 1200);

    } catch(err) {
        statusDiv.innerHTML = `<span style="color:var(--danger);">❌ ${err.message}</span>`;
        if (btn) { btn.disabled = false; }
    }
};

window.deleteFoto = async function(rowIndex, fotoIdx, cardIdx, folio, producto) {
    if (!confirm('¿Estás seguro de que deseas eliminar esta fotografía adjunta?')) return;
    
    const statusDiv = document.getElementById(`cc-status-${cardIdx}`);
    const btns      = document.querySelectorAll(`#cc-card-${cardIdx} button`);
    
    statusDiv.innerHTML = '<div class="loader" style="display:inline-block;width:18px;height:18px;border-width:2px;margin-right:6px;"></div> Eliminando foto...';
    btns.forEach(b => b.disabled = true);

    try {
        const saveRes  = await fetch('/api/update-foto', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                row_index: rowIndex,
                foto_url:  '',
                foto_index: fotoIdx,
                folio:     folio,
                producto:  producto,
            }),
        });
        const saveData = await saveRes.json();
        if (!saveData.success) throw new Error(saveData.error);

        statusDiv.innerHTML = '<span style="color:var(--success);"><i class="fas fa-check"></i> Foto eliminada correctamente</span>';
        
        setTimeout(() => {
            const currentSearch = document.getElementById('cc-search').value;
            if (currentSearch.length >= 2) searchConsultations(currentSearch);
            else fetchRecentFolios();
        }, 1200);

    } catch(err) {
        statusDiv.innerHTML = `<span style="color:var(--danger);">Error: ${err.message}</span>`;
        btns.forEach(b => b.disabled = false);
    }
};

function fileToBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload  = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

// =============================================
// HISTORY
// =============================================
const historyScreen    = document.getElementById('history-screen');
const historyContainer = document.getElementById('history-container');
const historySubtitle  = document.getElementById('history-subtitle');

let historyData = [];
let editingIndex = null;

window.showHistory = async function() {
    mainApp.style.display = 'none';
    historyScreen.style.display = 'block';
    historySubtitle.textContent = 'Cargando...';
    historyContainer.innerHTML = `
        <div style="text-align:center;padding:2rem;">
            <div class="loader" style="display:inline-block;"></div>
            <p style="margin-top:1rem;color:var(--text-muted);">Cargando historial...</p>
        </div>`;
    await fetchHistory();
};

window.showMain = function() {
    historyScreen.style.display = 'none';
    mainApp.style.display = 'block';
};

async function fetchHistory() {
    try {
        const res  = await fetch(`/api/history?user=${currentUser}`);
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        historyData = data;
        renderHistory();
    } catch(err) {
        historyContainer.innerHTML = `<p style="text-align:center;color:var(--danger);padding:2rem;">Error: ${err.message}</p>`;
    }
}

function renderHistory(initialSearch = '') {
    const cfg = USER_DISPLAY[currentUser];

    if (historyData.length === 0) {
        historyContainer.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-inbox"></i>
                <h2>Sin respuestas aún</h2>
                <p>Aún no tienes respuestas registradas.</p>
            </div>`;
        historySubtitle.textContent = `0 respuestas — ${cfg.role}`;
        return;
    }

    historyContainer.innerHTML =
        `<div class="search-bar" style="margin-bottom:0;">
            <i class="fas fa-search"></i>
            <input type="text" id="history-search" placeholder="Folio, producto, vehículo..." value="${initialSearch}" />
        </div>
        <div id="history-cards"></div>`;

    const searchEl = document.getElementById('history-search');
    const cardsEl  = document.getElementById('history-cards');

    // Always map full data so idx matches historyData[idx]
    cardsEl.innerHTML = historyData.map((item, idx) => renderHistoryCard(item, idx)).join('');

    const applySearch = () => {
        const q = searchEl.value.toLowerCase().trim();
        let visible = 0;
        cardsEl.querySelectorAll('.history-card').forEach(card => {
            const match = !q || (card.dataset.searchText || '').includes(q);
            card.style.display = match ? '' : 'none';
            if (match) visible++;
        });
        historySubtitle.textContent = `${visible} respuesta${visible !== 1 ? 's' : ''} — ${cfg.role}`;
    };

    searchEl.addEventListener('input', applySearch);
    applySearch(); // initial application of filter
}

function renderHistoryCard(item, idx) {
    const isEditing = editingIndex === idx;
    const statusClass =
        item.my_status.includes('Disponible') && !item.my_status.includes('No') ? 'status--green' :
        item.my_status.includes('No') ? 'status--red' : 'status--blue';

    const otherClass = item.other_user.toLowerCase() === 'ignacio' ? 'ignacio' : 'robinson';
    const otherBlock = (item.other_status || item.other_resp) ? `
        <div class="other-response other-response--${otherClass}" style="margin-bottom:0.75rem;">
            <i class="fas fa-user-check"></i>
            <div class="other-response-text">
                <div class="other-response-name">${item.other_user}</div>
                <div class="other-response-status">${item.other_status || '—'}</div>
                ${item.other_resp ? `<div class="other-response-detail">${item.other_resp}</div>` : ''}
            </div>
        </div>` : '';

    const editForm = isEditing ? `
        <div class="history-edit-form" id="edit-form-${idx}">
            <div class="status-grid" id="edit-status-grid-${idx}">
                ${QUICK_STATUS.map(s =>
                    `<button class="status-btn ${item.my_status === s.text ? 'selected' : ''}" onclick="selectEditStatus(${idx}, '${s.text}')">${s.icon} ${s.text}</button>`
                ).join('')}
            </div>
            <div class="quick-chips">
                ${QUICK_CHIPS.map(c =>
                    `<button class="chip ${editSelectedChips[idx]?.has(c) ? 'selected' : ''}" data-ecard="${idx}" data-chip="${c}" onclick="toggleEditChip(${idx}, '${c.replace(/'/g, "\\'")}')"> ${c}</button>`
                ).join('')}
            </div>
            <div class="input-group">
                <textarea id="edit-resp-${idx}" placeholder="Explicación...">${item.my_resp}</textarea>
            </div>
            <div class="link-group" style="margin-bottom:0.75rem;">
                <i class="fas fa-link"></i>
                <input type="url" id="edit-link-${idx}" value="${item.link || ''}" placeholder="Link de cotización (opcional)..." />
            </div>
            <div style="display:flex;gap:0.5rem;">
                <button class="submit-btn" id="edit-save-${idx}" onclick="saveHistoryEdit(${idx}, ${item.row_index})" style="flex:1;">
                    <i class="fas fa-check"></i> Guardar
                </button>
                <button onclick="cancelEdit()" style="flex:0.4;background:var(--bg3);border:1px solid var(--border);color:var(--text-muted);border-radius:var(--radius-sm);font-family:Inter,sans-serif;font-size:0.85rem;cursor:pointer;">
                    Cancelar
                </button>
            </div>
        </div>` : `
        <button class="edit-btn" onclick="startEditHistory(${idx})">
            <i class="fas fa-pen"></i> Editar
        </button>`;

    const linkBtn = item.link && !isEditing
        ? `<a href="${item.link}" target="_blank" class="link-pill"><i class="fas fa-link"></i> Ver link</a>` : '';

    const validFotos = (item.fotos || []).filter(isValidFotoUrl);
    const fotosBtn = validFotos.length > 0 && !isEditing ? `
        <div class="history-fotos-gallery" style="display:flex; gap:0.4rem; flex-wrap:wrap; margin-bottom:0.5rem; width:100%;">
            ${validFotos.map((url, i) => `
                <a href="${url}" target="_blank" class="foto-preview-btn" style="margin-bottom:0;"><i class="fas fa-image"></i> Foto ${i+1}</a>
            `).join('')}
        </div>` : '';

    return `
    <div class="history-card" id="hcard-${idx}"
         data-search-text="${[item.producto, item.folio, item.marca_modelo_año, item.my_status, item.ejecutivo].join(' ').toLowerCase()}">
        <div class="card-header" style="margin-bottom:0.75rem;">
            <div style="display:flex;flex-direction:column;gap:3px;">
                <span class="badge">Folio ${item.folio || 'S/N'}</span>
                ${item.fecha ? `<span class="fecha-badge"><i class="fas fa-calendar-alt"></i> ${item.fecha}</span>` : ''}
            </div>
            <span class="ejecutivo-badge"><i class="fas fa-headset" style="margin-right:4px;"></i>${item.ejecutivo || '—'}</span>
        </div>

        <div style="margin-bottom:0.6rem;">
            <div style="font-weight:700;font-size:1rem;color:var(--text);">${item.producto}</div>
            <div style="font-size:0.8rem;color:var(--text-muted);margin-top:2px;">${item.marca_modelo_año || ''} ${item.lado ? '· ' + item.lado : ''}</div>
        </div>

        <div class="history-response-block">
            <span class="status-pill ${statusClass}">${item.my_status}</span>
            ${item.my_resp ? `<span class="history-resp-text">${item.my_resp}</span>` : ''}
            ${linkBtn}
            ${fotosBtn}
        </div>

        ${otherBlock}
        ${editForm}
    </div>`;
}

let editSelectedStatuses = {};

window.startEditHistory = function(idx) {
    editingIndex = idx;
    editSelectedStatuses[idx] = historyData[idx].my_status;
    // Pre-select chips that match the current response text
    const currentResp = historyData[idx].my_resp || '';
    editSelectedChips[idx] = new Set(QUICK_CHIPS.filter(c => currentResp.includes(c)));
    renderHistory(document.getElementById('history-search')?.value.toLowerCase() || '');
    setTimeout(() => document.getElementById(`edit-resp-${idx}`)?.focus(), 100);
};

window.cancelEdit = function() {
    editingIndex = null;
    editSelectedChips = {};
    renderHistory(document.getElementById('history-search')?.value.toLowerCase() || '');
};

window.selectEditStatus = function(idx, status) {
    editSelectedStatuses[idx] = status;
    document.querySelectorAll(`#edit-status-grid-${idx} .status-btn`).forEach(btn => {
        const t = btn.innerText.replace(/^[\u{1F000}-\u{1FFFF}\u2600-\u27FF]\s*/u, '').trim();
        btn.classList.toggle('selected', t === status);
    });
};

window.fillEditChip = window.toggleEditChip; // alias for backwards compatibility

window.saveHistoryEdit = async function(idx, rowIndex) {
    const status = editSelectedStatuses[idx] || historyData[idx].my_status;
    const resp   = document.getElementById(`edit-resp-${idx}`).value.trim();
    const link   = document.getElementById(`edit-link-${idx}`).value.trim();
    const saveBtn= document.getElementById(`edit-save-${idx}`);

    saveBtn.disabled = true;
    saveBtn.innerHTML = '<div class="loader" style="width:16px;height:16px;border-width:2px;display:inline-block;"></div> Guardando...';

    try {
        const res = await fetch('/api/update', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ row_index: rowIndex, status, response: resp, link, user: currentUser }),
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.error);

        // Update local data
        historyData[idx].my_status = status;
        historyData[idx].my_resp   = resp;
        historyData[idx].link      = link;
        editingIndex = null;
        renderHistory(document.getElementById('history-search')?.value.toLowerCase() || '');
    } catch(err) {
        alert(`Error al guardar: ${err.message}`);
        saveBtn.disabled = false;
        saveBtn.innerHTML = '<i class="fas fa-check"></i> Guardar';
    }
};

// =============================================
// INIT
// =============================================
let pollInterval    = null;
let lastKnownCount  = null;
let lastFotoEventTime = Math.floor(Date.now() / 1000);

function requestNotificationPermission() {
    if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission();
    }
}

function fireNotification(newItems) {
    const diff = newItems - lastKnownCount;
    if (diff <= 0) return;

    // In-page sound (simple beep via AudioContext)
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain); gain.connect(ctx.destination);
        osc.frequency.value = 880;
        gain.gain.setValueAtTime(0.3, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
        osc.start(ctx.currentTime);
        osc.stop(ctx.currentTime + 0.4);
    } catch(_) {}

    // Browser notification (works in background tab)
    if ('Notification' in window && Notification.permission === 'granted') {
        const cfg = USER_DISPLAY[currentUser];
        new Notification('Stock Voice — Nueva consulta 📦', {
            body: `${diff} nueva${diff > 1 ? 's' : ''} consulta${diff > 1 ? 's' : ''} para ${cfg.label}`,
            tag: 'stock-voice-new',
            renotify: true,
        });
    }
}

async function autoPoll() {
    if (!currentUser) return;
    try {
        const res  = await fetch(`/api/pending?user=${currentUser}`);
        const data = await res.json();
        if (!Array.isArray(data)) return;

        const count = data.length;
        if (lastKnownCount !== null && count > lastKnownCount) {
            fireNotification(count);
            consultations = data;
            renderCards();
            const cfg = USER_DISPLAY[currentUser];
            headerSubtitle.textContent = `${count} pendiente${count !== 1 ? 's' : ''} — ${cfg.role}`;
        }
        lastKnownCount = count;
    } catch(_) { /* silent */ }

    // Check for new foto uploads from Call Center
    try {
        const fRes  = await fetch(`/api/foto-events?since=${lastFotoEventTime}`);
        const fData = await fRes.json();
        lastFotoEventTime = Math.floor(Date.now() / 1000);
        if (Array.isArray(fData) && fData.length > 0) {
            fData.forEach(ev => {
                if ('Notification' in window && Notification.permission === 'granted') {
                    new Notification('📷 Nueva foto recibida', {
                        body: `Folio ${ev.folio || '?'}: ${ev.producto || 'Consulta'}`,
                        tag:  'foto-' + ev.folio,
                        renotify: true,
                    });
                }
            });
        }
    } catch(_) { /* silent */ }
}

function startPolling() {
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(autoPoll, 60000); // cada 60 segundos
}

refreshBtn.addEventListener('click', fetchConsultations);

window.addEventListener('load', () => {
    const savedUser = localStorage.getItem('stockvoice_user');
    if (savedUser && USER_DISPLAY[savedUser]) {
        currentUser = savedUser;
        showMainApp();
        fetchConsultations().then(() => {
            lastKnownCount = consultations.length;
            requestNotificationPermission();
            startPolling();
        });
    } else {
        userSelectScreen.style.display = 'flex';
        mainApp.style.display = 'none';
    }
});
