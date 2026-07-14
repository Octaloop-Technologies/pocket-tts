import { apiFetch, showError, hideError } from './utils.js';

let selectedPlan = null;
let selectedInterval = 'monthly';

const PLANS = [
    { tier: 'basic', name: 'Basic', monthly_price: 500, yearly_price: 4800, quota: 50000 },
    { tier: 'pro', name: 'Pro', monthly_price: 1500, yearly_price: 14400, quota: 250000 },
    { tier: 'enterprise', name: 'Enterprise', monthly_price: 5000, yearly_price: 48000, quota: 1500000 }
];

export function initPlan() {
    renderPlans();
    selectedInterval = 'monthly';
    document.querySelector('input[name="interval"][value="monthly"]').checked = true;
    updatePlanVisibility();

    document.querySelectorAll('input[name="interval"]').forEach(radio => {
        radio.addEventListener('change', updatePlanVisibility);
    });

    document.getElementById('next-btn').addEventListener('click', async () => {
        const selected = document.querySelector('.plan-card.selected');
        if (!selected) {
            showError(document.getElementById('plan-error'), 'Please select a plan.');
            return;
        }
        hideError(document.getElementById('plan-error'));
        const plan = selected.dataset.plan;
        const interval = selected.dataset.interval;
        try {
            const data = await apiFetch(`/stripe/payment-link?plan=${plan}&interval=${interval}`);
            window.location.href = data.url;
        } catch (err) {
            showError(document.getElementById('plan-error'), err.message);
        }
    });
}

function renderPlans() {
    const container = document.getElementById('plan-cards');
    container.innerHTML = '';
    PLANS.forEach(p => {
        const card = document.createElement('div');
        card.className = 'plan-card';
        card.dataset.plan = p.tier;
        card.innerHTML = `
            <h3>${p.name}</h3>
            <div class="price">$${(p.monthly_price / 100).toFixed(2)}</div>
            <small>per month</small>
            <div style="margin-top:0.5rem;">${(p.quota / 1000).toFixed(0)}k chars</div>
        `;
        card.addEventListener('click', () => selectPlan(card));
        container.appendChild(card);
    });
    updatePlanVisibility();
}

function selectPlan(card) {
    document.querySelectorAll('.plan-card').forEach(c => c.classList.remove('selected'));
    card.classList.add('selected');
    selectedPlan = card.dataset.plan;
}

function updatePlanVisibility() {
    const interval = document.querySelector('input[name="interval"]:checked').value;
    selectedInterval = interval;
    document.querySelectorAll('.plan-card').forEach(card => {
        const p = PLANS.find(p => p.tier === card.dataset.plan);
        if (!p) return;
        const price = (interval === 'monthly') ? p.monthly_price : p.yearly_price;
        const period = (interval === 'monthly') ? 'month' : 'year';
        card.querySelector('.price').textContent = `$${(price / 100).toFixed(2)}`;
        card.querySelector('small').textContent = `per ${period}`;
        card.dataset.interval = interval;
        card.classList.remove('selected');
    });
    selectedPlan = null;
}