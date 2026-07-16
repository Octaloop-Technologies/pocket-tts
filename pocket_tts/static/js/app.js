// pocket_tts/static/js/app.js
import { getApiKey, switchView } from './utils.js';
import { initAuth, handleResetToken } from './auth.js';
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
        await handleResetToken(token);
        // Clear token from URL
        const cleanUrl = window.location.origin + window.location.pathname;
        window.history.replaceState({}, document.title, cleanUrl);
        initAuth(); // sets up the form submission (already done, but safe)
        return; // stop – do not run auth checks
    }

    // 2. NORMAL AUTHENTICATION FLOW
    const apiKey = getApiKey();
    if (!apiKey) {
        switchView('login');
        initAuth();
        return;
    }

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