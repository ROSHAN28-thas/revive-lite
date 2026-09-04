# ReviveLite — AI Revenue Recovery Console

**Razorpay AI Buildathon 2026 — Track 3: AI Revenue Recovery**

ReviveLite is a human-in-the-loop recovery dashboard for failed subscription payments. It helps merchants prioritize recovery opportunities while enforcing safety rules before an action is executed.

## Problem

Failed payments cause revenue loss. Retrying every failed payment in the same way can waste attempts, create poor customer experiences, and mishandle high-value or repeatedly failed transactions.

## Solution

ReviveLite scores each failed payment using:

- Failure reason
- Previous retry count
- Payment amount band

It then recommends one of four actions:

- `retry`
- `email`
- `whatsapp`
- `manual_review`

The merchant must approve every action.

## Razorpay Integration

For an approved `retry` action, the FastAPI backend creates a Razorpay **Test Mode Order**. The returned Razorpay Order ID is shown in the dashboard and stored in the recovery audit trail.

## Safety Guardrails

- Maximum two retry attempts per payment
- High-value payments with previous failures go to manual review
- Email and WhatsApp are simulated recommendations in this prototype
- Merchant approval is required before every action
- Every approved action is recorded in an audit trail

## Tech Stack

- Frontend: Next.js, React, TypeScript, Tailwind CSS
- Backend: FastAPI, Python, Pandas
- Payments: Razorpay Orders API, Test Mode
- Storage: Synthetic CSV dataset and JSON audit log

## Run Locally

### Backend

```bash
cd backend
pip install -r requirements.txt
pip install python-multipart
python -m uvicorn main:app --reload
```

Create a local `backend/.env` file. Do not commit it:

```env
RAZORPAY_KEY_ID=your_test_key_id
RAZORPAY_KEY_SECRET=your_test_key_secret
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Create a local `frontend/.env.local` file:

```env
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000
```

Open `http://localhost:3000`.

## Evaluation Note

The project uses a synthetic failed-payment dataset. Recovery outcomes displayed in the dashboard are simulated for prototype demonstration. The baseline comparison represents a naive policy that retries every failed payment once.

A production version would validate recovery uplift with privacy-safe merchant data, verified payment outcomes, customer-consent controls, contact-frequency limits, and Razorpay webhook events.

## Dashboard Screenshot

![ReviveLite dashboard](docs/screenshots/revivelite-dashboard.png)

## Demo Video

Demo video link: `To be added`
