# Dynamite DJs CRM — Phase 6

Phase 6 turns the CRM into a deployment-ready integration hub.

## Included
- Public `/inquiry` lead form that creates a CRM lead and follow-up task.
- JSON `/api/public/leads` endpoint for Wix or another website.
- Optional `X-CRM-Key` protection via `CRM_PUBLIC_API_KEY`.
- Admin Integrations screen for Google Calendar, Gmail, Outlook, Stripe, PayPal, Venmo, HoneyBook, Google Drive and Website Lead Form connection states.
- Event `.ics` calendar export.
- HoneyBook-compatible CSV export.
- Generic inbound webhook receiver with optional shared-key protection.
- Admin Settings screen for public URL/company settings.
- `.env.example` and Procfile for production deployment.

## Important
This build does not pretend OAuth/payment providers are connected before authorization. The integration UI and safe connection points are present; actual provider credentials must be added during deployment/authorization.

## Local run
1. Create a virtual environment.
2. `pip install -r requirements.txt`
3. Set `SECRET_KEY` in the environment.
4. Run `python app.py`.

For production, use Gunicorn (add `gunicorn` to your environment) and HTTPS.

## Wix launch path
The simplest first launch is to put a "Check Availability / Get a Quote" button on the Wix site pointing to the CRM's `/inquiry` URL. This avoids exposing a CRM API key in browser-side JavaScript.

A later Wix custom-form integration can POST server-side to `/api/public/leads` with `X-CRM-Key`.

## Security
- Do not send CRM, Wix, payment, Google, Microsoft or other account passwords to ChatGPT.
- Change the seeded demo passwords before production.
- Set a real random `SECRET_KEY`.
- Use HTTPS.
- Do not store raw payment card information in this application.
