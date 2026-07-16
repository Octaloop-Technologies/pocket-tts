import { apiFetch, showError, hideError, showSuccess, hideSuccess, switchView, setApiKey } from './utils.js';

export function initAuth() {
    // Login
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

    // Register
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

    // Forgot password
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

    // Reset password
    document.getElementById('form-reset').addEventListener('submit', async (e) => {
        e.preventDefault();
        hideError(document.getElementById('reset-error'));
        hideSuccess(document.getElementById('reset-success'));
        const token = document.getElementById('form-reset').dataset.token;
        const newPass = document.getElementById('reset-password').value;
        const confirmPass = document.getElementById('reset-confirm').value;
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
                body: JSON.stringify({ token, new_password: newPass, confirm_password: confirmPass })
            });
            showSuccess(document.getElementById('reset-success'), data.message);
            document.getElementById('form-reset').reset();
            delete document.getElementById('form-reset').dataset.token;
            setTimeout(() => switchView('login'), 3000);
        } catch (err) {
            showError(document.getElementById('reset-error'), err.message);
        }
    });

    // Handle token in URL for reset
    // (function initReset() {
    //     const params = new URLSearchParams(window.location.search);
    //     const token = params.get('token');
    //     if (token) {
    //         switchView('reset');
    //         document.getElementById('form-reset').dataset.token = token;
    //         const newUrl = window.location.origin + window.location.pathname;
    //         window.history.replaceState({}, document.title, newUrl);
    //     }
    // })();

    // View switching via data-view links (delegated)
    document.addEventListener('click', (e) => {
        const link = e.target.closest('[data-view]');
        if (!link) return;
        e.preventDefault();
        const viewId = link.getAttribute('data-view');
        if (viewId) switchView(viewId);
    });
}

// After successful auth: check subscription
async function afterAuth() {
    try {
        const sub = await apiFetch('/stripe/subscription');
        if (sub.status === 'active') {
            // app view will be shown by the app module
            switchView('app');
            // We need to update the app UI; the app module will handle that when its init is called.
            // We can dispatch an event or call a function.
            // We'll import and call a function from tts.js
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
