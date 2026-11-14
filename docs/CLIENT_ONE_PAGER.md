# What the service does, and what it does not

For a client before a pilot. Plain words; the measured figures are on the service's own Results page, which reads them from the build it runs.

## What it does

- Scores each email, SMS and link your people report, from the text alone. No link is opened.
- Links messages that reached one person within an hour and share a domain, a phone number or a sender, and scores them together as a possible
  campaign.
- Opens one alert per campaign that reaches the alert line, with the reason, the shared indicators and a timeline.
- Lets your analysts triage alerts (new, investigating, confirmed, false alarm, closed), assign them, add notes, and export reports.
- Accepts messages from a reporting mailbox or any system that can call its API, and lets your SIEM pull alerts.

## What it does not do

- It does not assess voice calls or video. They appear as "not assessed", never as safe.
- Its campaign scoring was measured on simulated campaigns built from real messages. It has not yet been tested on real coordinated attacks.
  Your pilot is part of that test.
- It does not block anything by itself. The email model raises false alarms on some real legitimate mail, such as bank and order notices.
  Treat its verdicts as advice for an analyst.
- Its scores are not probabilities.
- It is a research prototype from a university capstone project. It has had no penetration test and no load test yet.

## Your data

- People and identifiers are stored as keyed hashes. Message text is not kept unless you switch it on.
- You set how long data is kept; older data is deleted automatically every day.
- Your data is separate from every other client's, with its own key.
- Nothing is sent to an outside service, and nothing is used to train models without a separate written agreement.
- Before any real data, we agree in writing on purpose, retention and deletion, as India's Digital Personal Data Protection Act, 2023 requires.

## A pilot looks like this

1. We agree the purpose, the data, the retention period and who may see it, in writing.
2. We create your organisation and your first admin. Your admin adds analysts.
3. Your people forward suspicious messages to a reporting mailbox; the connector sends them in.
4. Every week we review the alerts with your analysts: what was real, what was a false alarm.
5. At the end you get a report, and we measure false alarms and misses on your own traffic.
