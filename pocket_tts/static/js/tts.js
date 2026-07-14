import { apiFetch, showStatus, hideStatus, getApiKey, clearApiKey, switchView } from './utils.js';

let defaultText = 'Hello world! I am Kyutai Pocket TTS.';

export function setDefaultText(text) {
    defaultText = text;
    const textarea = document.getElementById('text-input');
    if (textarea && !textarea.value) textarea.value = text;
}

export function initTTS() {
    // Set default text if not already set
    const textarea = document.getElementById('text-input');
    if (!textarea.value) textarea.value = defaultText;

    document.getElementById('generate-btn').addEventListener('click', generateAudio);
    document.getElementById('logout-btn').addEventListener('click', logout);
    document.getElementById('settings-gear').addEventListener('click', openBilling);
}

export function showApp(sub) {
    // Update UI elements
    document.getElementById('user-email').textContent = sub.plan || 'User';
    document.getElementById('plan-badge').textContent = `Plan: ${sub.plan || 'None'}`;
    document.getElementById('remaining-badge').textContent = `Remaining: ${sub.remaining_characters || 0}`;
    switchView('app');
    // Ensure TTS is initialized (if not already)
    initTTS();
}

async function generateAudio() {
    const text = document.getElementById('text-input').value.trim();
    if (!text) { showStatus('Please enter text.', true); return; }
    const formData = new FormData();
    formData.append('text', text);
    const voiceUrlVal = document.getElementById('voice-url').value.trim();
    const voiceFileVal = document.getElementById('voice-file').files[0];
    if (voiceFileVal) formData.append('voice_wav', voiceFileVal);
    else if (voiceUrlVal) formData.append('voice_url', voiceUrlVal);

    const btn = document.getElementById('generate-btn');
    btn.disabled = true;
    btn.textContent = 'Generating...';
    hideStatus();
    document.getElementById('audio-section').style.display = 'none';

    try {
        const res = await fetch(`${window.location.origin}/tts`, {
            method: 'POST',
            headers: { 'X-API-Key': getApiKey() },
            body: formData,
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || `Server error ${res.status}`);
        }
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const audioEl = document.getElementById('audio');
        audioEl.src = url;
        document.getElementById('download-link').href = url;
        document.getElementById('download-link').download = 'tts-output.wav';
        document.getElementById('audio-section').style.display = 'block';
        showStatus('Audio generated!');
        // Update remaining quota
        const sub = await apiFetch('/stripe/subscription');
        document.getElementById('remaining-badge').textContent = `Remaining: ${sub.remaining_characters || 0}`;
    } catch (err) {
        showStatus(err.message, true);
    } finally {
        btn.disabled = false;
        btn.textContent = 'Generate Audio';
    }
}

async function openBilling() {
    try {
        const data = await apiFetch('/stripe/manage-billing');
        window.open(data.portal_url, '_blank');
    } catch (err) {
        alert('Could not open billing portal: ' + err.message);
    }
}

function logout() {
    clearApiKey();
    switchView('login');
}