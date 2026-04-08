const container = document.getElementById('cards-container');
const refreshBtn = document.getElementById('refresh-btn');
const refreshIcon = document.getElementById('refresh-icon');

let consultations = [];

// Speech Recognition Setup
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;
if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.lang = 'es-CL';
    recognition.interimResults = false;
    recognition.continuous = false;
}

async function fetchConsultations() {
    refreshIcon.classList.add('fa-spin');
    try {
        const response = await fetch('/api/pending');
        const data = await response.json();
        consultations = data;
        renderCards();
    } catch (error) {
        console.error('Error fetching consultations:', error);
        container.innerHTML = '<p style="text-align:center; color:var(--danger)">Error al cargar datos. Revisa la conexión.</p>';
    } finally {
        refreshIcon.classList.remove('fa-spin');
        const loader = document.getElementById('main-loader');
        if (loader) loader.style.display = 'none';
    }
}

function renderCards() {
    if (consultations.length === 0) {
        container.innerHTML = `
            <div class="card" style="text-align: center; padding: 3rem;">
                <i class="fas fa-check-circle" style="font-size: 3rem; color: var(--success); margin-bottom: 1rem;"></i>
                <h2 style="margin-bottom: 0.5rem;">¡Todo listo!</h2>
                <p style="color: var(--text-muted)">No hay consultas pendientes en este momento.</p>
            </div>
        `;
        return;
    }

    container.innerHTML = consultations.map((item, index) => `
        <div class="card" id="card-${index}">
            <div class="badge">Folio: ${item.folio || 'N/A'}</div>
            <h2 class="product-title">${item.producto}</h2>
            
            <div class="product-details">
                <div class="detail-item">
                    <span class="detail-label">Vehículo:</span>
                    <span class="detail-value">${item.marca_modelo_año || '-'}</span>
                </div>
                <div class="detail-item">
                    <span class="detail-label">Características:</span>
                    <span class="detail-value">${item.caracteristicas || '-'}</span>
                </div>
                <div class="detail-item">
                    <span class="detail-label">Lado:</span>
                    <span class="detail-value">${item.lado || '-'}</span>
                </div>
                <div class="detail-item">
                    <span class="detail-label">CC Ej:</span>
                    <span class="detail-value">${item.ejecutivo || '-'}</span>
                </div>
            </div>

            ${item.duplicates && item.duplicates.length > 0 ? `
                <div class="duplicates" style="display: block;">
                    <i class="fas fa-exclamation-triangle"></i> Encontrado en otras filas: 
                    ${item.duplicates.map(d => `<br>• Row ${d.row}: ${d.response}`).join('')}
                </div>
            ` : ''}

            <div class="action-area">
                <div class="status-grid" id="status-grid-${index}">
                    <button class="status-btn" onclick="selectStatus(${index}, 'Disponible')">Disponible</button>
                    <button class="status-btn" onclick="selectStatus(${index}, 'No disponible')">No disponible</button>
                    <button class="status-btn" onclick="selectStatus(${index}, 'Necesita Foto')">Falta Foto</button>
                    <button class="status-btn" onclick="selectStatus(${index}, 'Precio subido')">Precio subido</button>
                </div>

                <div class="input-group">
                    <textarea id="response-${index}" placeholder="Escribe o dicta tu respuesta..."></textarea>
                    <button class="voice-btn" id="voice-btn-${index}" onclick="startVoice(${index})">
                        <i class="fas fa-microphone"></i>
                    </button>
                </div>

                <button class="submit-btn" id="submit-${index}" onclick="submitResponse(${index})">Enviar Respuestas</button>
            </div>
        </div>
    `).join('');
}

let selectedStatuses = {};

window.selectStatus = (index, status) => {
    selectedStatuses[index] = status;
    const buttons = document.querySelectorAll(`#status-grid-${index} .status-btn`);
    buttons.forEach(btn => {
        if (btn.innerText === status || (status === 'Falta Foto' && btn.innerText === 'Falta Foto')) {
            btn.classList.add('selected');
        } else {
            btn.classList.remove('selected');
        }
    });
};

window.startVoice = (index) => {
    if (!recognition) {
        alert('Tu navegador no soporta reconocimiento de voz. Intenta con Chrome o Safari.');
        return;
    }

    const btn = document.getElementById(`voice-btn-${index}`);
    const textarea = document.getElementById(`response-${index}`);

    btn.classList.add('recording');
    recognition.start();

    recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        textarea.value = transcript;
        btn.classList.remove('recording');
    };

    recognition.onerror = () => {
        btn.classList.remove('recording');
        alert('Error al reconocer voz. Intenta de nuevo.');
    };

    recognition.onspeechend = () => {
        recognition.stop();
        btn.classList.remove('recording');
    };
};

window.submitResponse = async (index) => {
    const status = selectedStatuses[index];
    const responseText = document.getElementById(`response-${index}`).value;
    const submitBtn = document.getElementById(`submit-${index}`);
    const card = document.getElementById(`card-${index}`);

    if (!status) {
        alert('Por favor selecciona un estado (Disponible, No disponible, etc.)');
        return;
    }

    submitBtn.disabled = true;
    submitBtn.innerHTML = '<div class="loader" style="display:inline-block"></div> Enviando...';

    try {
        const res = await fetch('/api/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                row_index: consultations[index].row_index,
                status: status,
                response: responseText
            })
        });

        if (res.ok) {
            card.style.transform = 'translateX(100px)';
            card.style.opacity = '0';
            setTimeout(() => {
                consultations.splice(index, 1);
                renderCards();
            }, 300);
        } else {
            alert('Error al actualizar la hoja. Intenta de nuevo.');
            submitBtn.disabled = false;
            submitBtn.innerText = 'Enviar Respuestas';
        }
    } catch (error) {
        console.error('Submit error:', error);
        alert('Error de red.');
        submitBtn.disabled = false;
        submitBtn.innerText = 'Enviar Respuestas';
    }
};

refreshBtn.addEventListener('click', fetchConsultations);

// Initial Load
window.addEventListener('load', fetchConsultations);
