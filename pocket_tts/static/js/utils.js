export const API_BASE = window.location.origin;

export async function apiFetch(path, options = {}) {
    const headers = { 'Content-Type': 'application/json' };
    const apiKey = localStorage.getItem('pocket_tts_api_key');
    if (apiKey) headers['X-API-Key'] = apiKey;
    const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || err.message || 'Request failed');
    }
    return res.json();
}

export function showError(el, msg) { el.textContent = msg; el.style.display = 'block'; }
export function hideError(el) { el.style.display = 'none'; }
export function showSuccess(el, msg) { el.textContent = msg; el.style.display = 'block'; }
export function hideSuccess(el) { el.style.display = 'none'; }

export function showStatus(msg, isError = false) {
    const el = document.getElementById('status');
    el.textContent = msg;
    el.style.display = 'block';
    el.className = 'error';
    if (!isError) { el.style.background = '#dbeafe'; el.style.color = '#1e3a8a'; }
    else { el.style.background = '#fee2e2'; el.style.color = '#b91c1c'; }
}
export function hideStatus() { document.getElementById('status').style.display = 'none'; }

export function getApiKey() { return localStorage.getItem('pocket_tts_api_key'); }
export function setApiKey(key) { localStorage.setItem('pocket_tts_api_key', key); }
export function clearApiKey() { localStorage.removeItem('pocket_tts_api_key'); }

export function switchView(viewId) {
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    const el = document.getElementById(`view-${viewId}`);
    if (el) el.classList.add('active');
    else console.warn('View not found:', viewId);
}