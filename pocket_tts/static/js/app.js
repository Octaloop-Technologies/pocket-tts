import { getApiKey, switchView } from './utils.js';
import { initAuth } from './auth.js';
import { initPlan } from './plan.js';
import { initTTS, showApp, setDefaultText } from './tts.js';

let defaultText = "";

try{
    defaultText = JSON.parse(document.currentScript.dataset.defaultText);
}
catch (exception) {
    console.warn("Could not parse default text, using fallback")
    defaultText = "Hello World";
}

// Check initial authentication and subscription
async function bootstrap() {
    const apiKey = getApiKey();
    if (!apiKey) {
        switchView('login');
        initAuth();
        return;
    }

    // Try to fetch subscription
    try {
        // We need to import auth's afterAuth logic or duplicate the check.
        // We'll use a dynamic import to avoid circular deps.
        const { apiFetch } = await import('./utils.js');
        const sub = await apiFetch('/stripe/subscription');
        if (sub.status === 'active') {
            showApp(sub);
        } else {
            switchView('plan');
            initPlan();
        }
    } catch (err) {
        // No active subscription or error
        switchView('plan');
        initPlan();
    }
    // Initialize auth module for handling forms (login, register, etc.)
    // But we need to ensure that auth module doesn't run its own afterAuth again.
    // So we'll call initAuth() but it will only set up event listeners.
    initAuth();
}

// Handle success param
if (new URLSearchParams(window.location.search).has('success')) {
    // After payment, we re-check subscription
    const apiKey = getApiKey();
    if (apiKey) {
        // We need to re-run bootstrap after a short delay to allow webhook processing
        setTimeout(bootstrap, 3000);
    } else {
        // No key, show login
        switchView('login');
        initAuth();
    }
    // Clean URL
    const cleanUrl = window.location.origin + window.location.pathname;
    window.history.replaceState({}, document.title, cleanUrl);
} else {
    bootstrap();
}