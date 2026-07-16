import { getApiKey, switchView } from './utils.js';
import { initAuth } from './auth.js';
import { initPlan } from './plan.js';
import { initTTS, showApp, setDefaultText } from './tts.js';

let defaultText = "";

try {
    defaultText = JSON.parse(document.currentScript.dataset.defaultText);
} catch (exception) {
    console.warn("Could not parse default text, using fallback");
    defaultText = "Hello World";
}

async function bootstrap() {

    // 1. CHECK FOR PASSWORD RESET TOKEN
    const params = new URLSearchParams(window.location.search);
    const token = params.get('token');
    if (token) {
        console.log('Reset token found in URL:', token);

        // Validate token with backend before showing the form
        try {
            const { apiFetch } = await import('./utils.js');
            const result = await apiFetch(`/stripe/reset-password?token=${encodeURIComponent(token)}`);
            // If we get here, token is valid
            console.log('Token is valid for email:', result.email);
            switchView('reset');
            const form = document.getElementById('form-reset');
            if (form) {
                form.dataset.token = token;
                console.log('Token stored in form dataset');
            }
            // Clear token from URL
            const cleanUrl = window.location.origin + window.location.pathname;
            window.history.replaceState({}, document.title, cleanUrl);
            initAuth(); // sets up the form submission
            return; // stop – do not run auth checks
        } catch (err) {
            // Token invalid – show an error message on the login page or a dedicated error view
            console.error('Token validation failed:', err.message);
            // You can show an error on the login view or redirect to login with an error param
            switchView('login');
            const errorEl = document.getElementById('login-error');
            if (errorEl) {
                errorEl.textContent = 'Password reset link is invalid or expired. Please request a new one.';
                errorEl.style.display = 'block';
            }
            // Also clear the token from URL
            const cleanUrl = window.location.origin + window.location.pathname;
            window.history.replaceState({}, document.title, cleanUrl);
            initAuth();
            return;
        }
    }

    // ------------------------------------------------------------------
    // 2. NORMAL AUTHENTICATION FLOW
    // ------------------------------------------------------------------
    const apiKey = getApiKey();
    if (!apiKey) {
        switchView('login');
        initAuth();
        return;
    }

    // Try to fetch subscription
    try {
        const { apiFetch } = await import('./utils.js');
        const sub = await apiFetch('/stripe/subscription');
        if (sub.status === 'active') {
            showApp(sub);
        } else {
            switchView('plan');
            initPlan();
        }
    } catch (err) {
        console.warn('Subscription fetch failed, showing plan selection:', err);
        switchView('plan');
        initPlan();
    }
    initAuth();
}

// ------------------------------------------------------------------
// HANDLE PAYMENT SUCCESS REDIRECT (?success=true)
// ------------------------------------------------------------------
if (new URLSearchParams(window.location.search).has('success')) {
    console.log('Payment success detected, re-checking subscription after delay...');
    const apiKey = getApiKey();
    if (apiKey) {
        // Wait a few seconds for webhook to process
        setTimeout(bootstrap, 3000);
    } else {
        switchView('login');
        initAuth();
    }
    const cleanUrl = window.location.origin + window.location.pathname;
    window.history.replaceState({}, document.title, cleanUrl);
} else {
    bootstrap();
}