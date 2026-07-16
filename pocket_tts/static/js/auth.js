import { apiFetch, showError, hideError, showSuccess, hideSuccess, switchView, setApiKey } from './utils.js';

export function initAuth() {
    document.getElementById('form-login').addEventListener('submit', async (e) => {
        e.preventDefault();
        hideError(document.getElementById('login-error'));
        const email = document.getElementById('login-email').value.trim();
        const password = document.getElementById('login-password').value;
        try {
            const data = await apiFetch('/stripe/login', {
                method: 'POST',
                body: JSON.stringify({ email, password })
            });
            setApiKey(data.api_key);
            afterAuth();
        } catch (err) {
            showError(document.getElementById('login-error'), err.message);
        }
    });

    document.getElementById('form-register').addEventListener('submit', async (e) => {
        e.preventDefault();
        hideError(document.getElementById('reg-error'));
        const email = document.getElementById('reg-email').value.trim();
        const password = document.getElementById('reg-password').value;
        const confirm = document.getElementById('reg-confirm').value;
        const name = document.getElementById('reg-name').value.trim();
        if (password !== confirm) {
            showError(document.getElementById('reg-error'), 'Passwords do not match');
            return;
        }
        try {
            const data = await apiFetch('/stripe/register', {
                method: 'POST',
                body: JSON.stringify({ email, password, name })
            });
            setApiKey(data.api_key);
            afterAuth();
        } catch (err) {
            showError(document.getElementById('reg-error'), err.message);
        }
    });

    document.getElementById('form-forgot').addEventListener('submit', async (e) => {
        e.preventDefault();
        hideError(document.getElementById('forgot-error'));
        hideSuccess(document.getElementById('forgot-message'));
        const email = document.getElementById('forgot-email').value.trim();
        try {
            const data = await apiFetch('/stripe/request-password-reset', {
                method: 'POST',
                body: JSON.stringify({ email })
            });
            showSuccess(document.getElementById('forgot-message'), data.message || 'Reset link sent if email exists.');
            document.getElementById('forgot-email').value = '';
        } catch (err) {
            showError(document.getElementById('forgot-error'), err.message);
        }
    });

    document.getElementById('form-reset').addEventListener('submit', async (e) => {
        e.preventDefault();
        hideError(document.getElementById('reset-error'));
        hideSuccess(document.getElementById('reset-success'));
        const token = document.getElementById('form-reset').dataset.token;
        const newPass = document.getElementById('reset-password').value;
        const confirmPass = document.getElementById('reset-confirm').value;
        const csrfToken = document.getElementById('reset-csrf').value;
        if (newPass !== confirmPass) {
            showError(document.getElementById('reset-error'), 'Passwords do not match');
            return;
        }
        if (newPass.length < 8) {
            showError(document.getElementById('reset-error'), 'Password must be at least 8 characters');
            return;
        }
        try {
            const data = await apiFetch('/stripe/reset-password', {
                method: 'POST',
                body: JSON.stringify({
                    token,
                    new_password: newPass,
                    confirm_password: confirmPass,
                    csrf_token: csrfToken
                })
            });
            showSuccess(document.getElementById('reset-success'), data.message);
            document.getElementById('form-reset').reset();
            delete document.getElementById('form-reset').dataset.token;
            document.getElementById('reset-csrf').value = '';
            setTimeout(() => switchView('login'), 3000);
        } catch (err) {
            showError(document.getElementById('reset-error'), err.message);
        }
    });

    document.addEventListener('click', (e) => {
        const link = e.target.closest('[data-view]');
        if (!link) return;
        e.preventDefault();
        const viewId = link.getAttribute('data-view');
        if (viewId) switchView(viewId);
    });
}

async function afterAuth() {
    try {
        const sub = await apiFetch('/stripe/subscription');
        if (sub.status === 'active') {
            const { showApp } = await import('./tts.js');
            showApp(sub);
        } else {
            switchView('plan');
            const { initPlan } = await import('./plan.js');
            initPlan();
        }
    } catch (err) {
        switchView('plan');
        const { initPlan } = await import('./plan.js');
        initPlan();
    }
}

export async function handleResetToken(token) {
    try {
        const response = await fetch(`${window.location.origin}/stripe/reset-password?token=${encodeURIComponent(token)}`, {
            method: 'GET',
            credentials: 'include'
        });
        if (!response.ok) {
            throw new Error('Invalid or expired token');
        }
        const data = await response.json();
        const form = document.getElementById('form-reset');
        form.dataset.token = data.token;
        document.getElementById('reset-csrf').value = data.csrf_token;
        switchView('reset');
    } catch (err) {
        console.error('Token validation failed:', err.message);
        switchView('login');
        const errorEl = document.getElementById('login-error');
        if (errorEl) {
            errorEl.textContent = 'Password reset link is invalid or expired. Please request a new one.';
            errorEl.style.display = 'block';
        }
        const cleanUrl = window.location.origin + window.location.pathname;
        window.history.replaceState({}, document.title, cleanUrl);
    }
}