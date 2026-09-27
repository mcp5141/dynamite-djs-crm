# Dynamite DJs CRM — Phase 4

Phase 4 adds the internal automation engine to the Phase 3 wedding-management CRM.

## Included
- Configurable automation rules with enable/disable controls
- Idempotent automation runs (no duplicate tasks for the same trigger)
- New inquiry 24-hour follow-up task
- Proposal follow-up tasks at 3, 7 and 14 days after a sent proposal
- Booked-event welcome workflow
- Automatic planning questionnaire creation around the 90-day milestone
- 30-day final planning task
- 7-day final confirmation task
- Payment reminders at 60/30/14 days and overdue alerts
- Completed-event thank-you task
- Review-request record creation for completed events
- In-app notifications for automation activity and due tasks
- Automation dashboard with manual “Run engine now” control
- Event planning status control for triggering the completed-event workflow

## Safety
Automations create internal CRM tasks/notifications only. They do **not** automatically send email or SMS. External messaging will be added only when integrations and explicit send controls are implemented.

## Run
1. Install dependencies from `requirements.txt`.
2. Run `python app.py`.
3. Sign in with the seeded development accounts shown in the prior README/build documentation.
4. Open **Automations** to inspect rules and run the engine.

## Production note
For true scheduled automation, Phase 4's `run_automations()` function should be invoked by a production scheduler/worker (for example a cron job or hosted task runner). The current manual trigger keeps the local build deterministic and avoids silently sending anything to clients.
