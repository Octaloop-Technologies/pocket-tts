# Pocket TTS Subscription Flow Implementation Guide

## Overview

The subscription system has been restructured to provide a complete user journey:

**User → Local Signup/Login → Plan Selection (Monthly/Yearly) → Stripe Payment → TTS App**

---

## What Changed

### 1. Configuration Updates

#### `stripe_subscription/config.py`
- Fixed duplicate STRIPE_PRICE_* configuration entries
- Added proper default URLs for payment success/cancel redirects
- Default success redirect: `http://localhost:8000/?success=true`

#### `.env`
```env
STRIPE_PAYMENT_SUCCESS_URL = "http://localhost:8000/?success=true"
STRIPE_PAYMENT_CANCEL_URL = "http://localhost:8000/"
```

### 2. Backend API Endpoints

#### `/stripe/register` (POST)
**Local user registration - no Stripe data required**
```json
Request: {
  "email": "user@example.com",
  "password": "password123",
  "name": "John Doe"
}
Response: {
  "api_key": "sk_...",
  "user_id": 1
}
```

#### `/stripe/login` (POST)
**Local user authentication**
```json
Request: {
  "email": "user@example.com",
  "password": "password123"
}
Response: {
  "api_key": "sk_...",
  "user_id": 1
}
```

#### `/stripe/plans` (GET)
**Fetch all available plans**
```json
Response: {
  "plans": [
    {
      "tier": "basic",
      "name": "Basic",
      "monthly_price": 500,
      "yearly_price": 4800,
      "quota_limit": 50000
    },
    ...
  ]
}
```

#### `/stripe/subscription` (GET)
**Get user's current subscription status (requires X-API-Key header)**
```json
Response: {
  "plan": "Basic",
  "status": "active",
  "current_period_end": "2024-08-03T12:00:00",
  "remaining_characters": 45000,
  "interval": "monthly",
  "plan_tier": "basic"
}
```

#### `/stripe/payment-link` (GET)
**Get personalized Stripe payment link (requires authentication)**
```
GET /stripe/payment-link?plan=basic&interval=monthly

Response: {
  "url": "https://buy.stripe.com/test_...?client_reference_id=1&prefilled_email=user@example.com"
}
```

#### `/stripe/webhook` (POST)
**Stripe webhook handler (automatically called by Stripe)**
- Listens for `checkout.session.completed` events
- Creates/updates local subscription record
- Syncs subscription status from Stripe

---

## User Flow (Step-by-Step)

### 1. **Signup/Login Page**
```
┌─────────────────────────────────────┐
│  🎙️ Pocket TTS                      │
├─────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐ │
│  │   REGISTER   │  │    LOGIN     │ │
│  │              │  │              │ │
│  │  Email       │  │  Email       │ │
│  │  Password    │  │  Password    │ │
│  │  Name        │  │              │ │
│  │              │  │              │ │
│  │  [Register]  │  │  [Login]     │ │
│  └──────────────┘  └──────────────┘ │
└─────────────────────────────────────┘
```
- **User Action**: User enters email/password and registers or logs in
- **Backend**: Creates local user account, generates API key
- **Frontend**: Stores API key in localStorage, proceeds to plan selection

### 2. **Plan Selection Page**
```
┌─────────────────────────────────────┐
│  Choose Your Plan                   │
├─────────────────────────────────────┤
│  ◉ Monthly    ○ Yearly              │
├─────────────────────────────────────┤
│ ┌──────────┐ ┌──────────┐ ┌──────────┐
│ │  BASIC   │ │   PRO    │ │ENTERPRISE│
│ │ $5.00/mo │ │$15.00/mo │ │$50.00/mo │
│ │ 50k chars│ │250k chars│ │1500k chrs│
│ └──────────┘ └──────────┘ └──────────┘
│                                       │
│  [Next →]                             │
└─────────────────────────────────────┘
```
- **User Action**: 
  - Toggle between Monthly/Yearly pricing
  - Click on a plan card to select it
  - Click "Next" to proceed
- **Frontend**: 
  - Fetches plans from `/stripe/plans` endpoint
  - Updates prices based on selected interval
  - Shows visual selection feedback
- **Backend**: Called when user clicks Next to generate personalized Stripe link

### 3. **Stripe Payment**
- **User Action**: Redirected to Stripe Checkout with:
  - Pre-filled email
  - Client reference ID (user_id) for identification
  - Selected plan and billing period
- **Stripe**: Handles payment processing
- **Webhook**: Confirms payment and creates subscription in database

### 4. **Success Redirect**
- **Stripe**: Redirects user to `http://localhost:8000/?success=true`
- **Frontend**: Detects `?success=true` parameter
- **Frontend**: Calls `afterAuth()` to check subscription status
- **Backend**: Returns active subscription
- **Frontend**: Shows TTS application interface

### 5. **TTS Application**
```
┌──────────────────────────────────────────┐
│  Pocket TTS        User✓ Plan: Basic    │
├──────────────────────────────────────────┤
│                                          │
│  [Text Input Area]                       │
│  ┌──────────────────────────────────┐    │
│  │ Hello world! I am Pocket TTS     │    │
│  └──────────────────────────────────┘    │
│                                          │
│  [Voice URL/File] [Generate Audio]      │
│                                          │
│  [Generated Audio Player]                │
│  [Download]                              │
│                                          │
│  [Logout] [Settings]                     │
└──────────────────────────────────────────┘
```
- User can now generate audio using their allocated character quota
- Remaining characters displayed and updated after each generation

---

## Database Schema

### Users Table
```
- id (primary key)
- email (unique, required)
- password_hash (required)
- api_key (unique, required)
- stripe_customer_id (optional - not required for signup)
- created_at
- updated_at
- last_login
```

### Plans Table
```
- id (primary key)
- name (e.g., "Basic", "Pro", "Enterprise")
- tier (e.g., "basic", "pro", "enterprise")
- monthly_price (in cents, e.g., 500 = $5.00)
- yearly_price (in cents, e.g., 4800 = $48.00)
- quota_limit (characters per billing period)
- stripe_price_monthly (optional - Stripe price ID)
- stripe_price_yearly (optional - Stripe price ID)
- is_active
- created_at
- updated_at
```

### Subscriptions Table
```
- id (primary key)
- user_id (foreign key → users)
- plan_id (foreign key → plans)
- stripe_subscription_id (Stripe subscription ID)
- status (active, inactive, expired, canceled)
- start_date
- end_date (current billing period end)
- characters_used (cumulative in current period)
- quota_limit (copied from plan at signup time)
- interval (monthly or yearly)
- created_at
- updated_at
```

### Audit Logs Table
```
- id (primary key)
- user_id (foreign key → users, nullable)
- action (e.g., "register", "login", "payment_success")
- details (JSON string)
- ip_address
- user_agent
- created_at
```

---

## How the Payment Works

### Flow Diagram
```
┌─────────┐
│  User   │
└────┬────┘
     │
     │ 1. Registers/Logs in
     ▼
┌──────────────┐
│ Local Server │ ← Creates user locally (NO Stripe customer created yet)
└────┬─────────┘
     │
     │ 2. Selects plan
     ▼
┌──────────────┐
│ Local Server │ ← Generates personalized Stripe payment link
└────┬─────────┘
     │
     │ 3. Clicks payment link
     ▼
┌───────────────────────┐
│  Stripe Checkout      │ ← Handles payment (card, Apple Pay, etc.)
└────┬──────────────────┘
     │
     │ 4. Payment successful
     ▼
┌───────────────────────┐
│  Stripe Webhook       │ ← Sends checkout.session.completed
└────┬──────────────────┘
     │
     ▼
┌──────────────────────────────┐
│ Local Server Webhook Handler │ ← Receives webhook
│                              │
│ • Extract user_id from       │
│   client_reference_id        │
│ • Fetch Stripe subscription  │
│ • Create/update local        │
│   subscription record        │
└────┬───────────────────────────┘
     │
     │ 5. Redirects to success URL
     ▼
┌─────────────────────────────┐
│ Browser: /?success=true     │
│                             │
│ • Detects ?success param    │
│ • Calls afterAuth()         │
│ • Checks subscription status│
│ • Shows app interface       │
└─────────────────────────────┘
```

---

## Testing the Flow

### Prerequisites
1. Stripe Test Account with payment links configured
2. Environment variables set in `.env`:
   ```env
   STRIPE_SECRET_KEY=sk_test_...
   STRIPE_PRICE_BASIC_MONTHLY=https://buy.stripe.com/test_...
   STRIPE_PRICE_BASIC_YEARLY=https://buy.stripe.com/test_...
   STRIPE_PRICE_PRO_MONTHLY=https://buy.stripe.com/test_...
   STRIPE_PRICE_PRO_YEARLY=https://buy.stripe.com/test_...
   STRIPE_PRICE_ENTERPRISE_MONTHLY=https://buy.stripe.com/test_...
   STRIPE_PRICE_ENTERPRISE_YEARLY=https://buy.stripe.com/test_...
   ```

### Test Scenario 1: Complete Payment Flow
```bash
# 1. Start the server
uv run pocket-tts serve

# 2. Open browser
# http://localhost:8000

# 3. Register new account
# Email: test@example.com
# Password: test123
# Name: Test User

# 4. Select plan (e.g., Basic, Monthly)

# 5. Click "Next" button

# 6. You'll be redirected to Stripe Checkout
# Use test card: 4242 4242 4242 4242
# Any future expiry date
# Any 3-digit CVC

# 7. Complete payment

# 8. Redirected to http://localhost:8000/?success=true
# Wait a moment for webhook to process
# Should see TTS app with "Plan: Basic" and "Remaining: 50000" characters

# 9. Test text-to-speech generation
```

### Test Scenario 2: Check Webhook
```bash
# Check server logs for:
# "Audit: user=1, action=payment_success"
# "Subscription X synced for user 1"
```

### Test Scenario 3: Login After Payment
```bash
# 1. Open http://localhost:8000 in a new private window
# 2. Click "Login"
# 3. Use credentials from scenario 1
# 4. Should go directly to TTS app (subscription detected)
```

### Test Scenario 4: Monthly vs Yearly Pricing
```bash
# 1. Start fresh signup
# 2. In plan selection:
#    - Note monthly price: $5.00 → $15.00 → $50.00
#    - Toggle to Yearly: $48.00 → $144.00 → $480.00
# 3. Test selecting different intervals
# 4. Verify price updates correctly
```

---

## Troubleshooting

### Issue: "Payment link not found"
**Cause**: Environment variable not set or key name mismatch
**Solution**: Check `.env` has `STRIPE_PRICE_BASIC_MONTHLY`, etc.

### Issue: Webhook not processing
**Cause**: 
- Webhook secret not configured
- Network issue (localhost not accessible to Stripe)
**Solution**: 
- Set `STRIPE_WEBHOOK_SECRET` in `.env`
- For local testing, use Stripe CLI: `stripe listen --forward-to localhost:8000/stripe/webhook`

### Issue: "No subscription" after payment
**Cause**: Webhook not processed yet (timing issue)
**Solution**: Wait 10-30 seconds and refresh page

### Issue: Plan selection not showing
**Cause**: `/stripe/plans` endpoint not working
**Solution**: Check server logs, verify database has plans seeded

### Issue: User data not persisting
**Cause**: Database not created
**Solution**: Delete `subscriptions.db` and restart server to recreate

---

## Security Considerations

1. **Password Storage**: Currently uses SHA-256 with salt
   - ⚠️ Not production-ready
   - Replace with bcrypt: `pip install bcrypt`

2. **API Keys**: Generated with `secrets.token_urlsafe(32)`
   - Securely transmitted in `X-API-Key` header
   - Never exposed in URLs

3. **HTTPS**: Use HTTPS in production
   - Update `STRIPE_PAYMENT_SUCCESS_URL` to use `https://`

4. **Stripe Keys**: Keep `STRIPE_SECRET_KEY` secret
   - Never commit to version control
   - Use environment variables only

5. **Webhook Verification**: Uses Stripe signature validation
   - Verify `STRIPE_WEBHOOK_SECRET` is set

---

## Production Checklist

- [ ] Upgrade password hashing to bcrypt
- [ ] Enable HTTPS for all URLs
- [ ] Set up proper webhook secret
- [ ] Configure webhook endpoint in Stripe dashboard
- [ ] Use Stripe production keys (live mode)
- [ ] Update redirect URLs to production domain
- [ ] Enable database backups
- [ ] Set up proper logging and monitoring
- [ ] Review security policies
- [ ] Load test the payment flow

---

## Files Modified

1. `stripe_subscription/config.py` - Fixed configuration
2. `stripe_subscription/routes.py` - Added endpoints
3. `.env` - Added redirect URLs
4. `stripe_subscription/dependencies.py` - Fixed column name bug

## Frontend

- `pocket_tts/static/index.html` - Already has complete flow (no changes needed)

---

## Notes

- User data is stored locally in the database
- No Stripe customer account is created until first payment
- After successful payment, subscription is linked to user_id
- Each user can have multiple subscriptions (though typically one active)
- Character usage is tracked and enforced at generation time
- Plans are seeded automatically on server startup
