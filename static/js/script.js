// =============================================
// Stock Voice — Main Script
// =============================================

// ---- State ----
let currentUser = null;
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
    ignacio:  { label: 'Ignacio',  role: 'La Reina',          color: 'ignacio' },
    robinson: { label: 'Robinson', role: 'Respuestas Externas', color: 'robinson' },
};

// ---- Quick Status Buttons (K / M) ----
const QUICK_STATUS = [
    { icon: '✅', text: 'Disponible' },
    { icon: '❌', text: 'No Disponible' },
    { icon: '📦', text: 'A Pedido' },
    { icon: '📸', text: 'Necesita Foto' },
    { icon: '💰', text: 'Precio Actualizado' },
    { icon: '🔔', text: 'Falta Información' },
];

// ---- Quick Explanation Chips (L / N) ----
const QUICK_CHIPS = [
    'Para el mismo dia, Precio de Panal',
    'Para 12 dias, Se puede Poner provisorio',
    'Todo menos la Base',
    'Para 30 dias',
    'Solo piezas reacondicionadas',
];

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
    showMainApp();
    fetchConsultations();
};

window.changeUser = function() {
    currentUser = null;
    mainApp.style.display = 'none';
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
            </div>`;
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

        // Quick explanation chips
        const chips = QUICK_CHIPS.map(c =>
            `<button class="chip" onclick="fillChip(${idx}, '${c.replace(/'/g, "\\'")}')">${c}</button>`
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
    }).join('');

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
// INIT
// =============================================
refreshBtn.addEventListener('click', fetchConsultations);

window.addEventListener('load', () => {
    const savedUser = localStorage.getItem('stockvoice_user');
    if (savedUser && USER_DISPLAY[savedUser]) {
        currentUser = savedUser;
        showMainApp();
        fetchConsultations();
    } else {
        userSelectScreen.style.display = 'flex';
        mainApp.style.display = 'none';
    }
});
