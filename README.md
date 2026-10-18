# ✈️ FlightFlow

> **Fault-tolerant distributed system for automated airline disruption recovery and passenger rebooking.**

FlightFlow is a distributed airline disruption-recovery system that simulates how passengers can be safely rebooked when large-scale flight disruptions occur.

It is designed to handle **high-concurrency rebooking, worker failures, duplicate messages, seat contention, and partially completed workflows** while maintaining consistent system state.

---

## 🚨 Problem

Large-scale disruptions such as **storms, aircraft failures, crew shortages, and cascading delays** can affect hundreds or thousands of passengers simultaneously.

A distributed rebooking system must avoid:

* Double-selling available seats
* Duplicate processing of the same booking
* Lost work when workers crash
* Partially completed rebooking operations
* Inconsistent booking states
* Messages being lost between services

FlightFlow addresses these problems through reliability patterns commonly used in distributed systems.

---

## 💡 How FlightFlow Works

```text
Disruption
    ↓
Rebooking Planner
    ↓
Transactional Outbox
    ↓
RabbitMQ
    ↓
Distributed Workers
    ↓
Saga Workflow
    ↓
Seat → Ticket → Baggage → Notification
    ↓
PostgreSQL
    ↓
React Monitoring Dashboard
```

The system generates a synthetic airline network and disruption scenario, identifies affected bookings, creates alternative itineraries, and processes each rebooking through a distributed workflow.

---

## ⚙️ Key Features

### 🔄 Saga-Based Rebooking

Each passenger rebooking is handled as a saga:

**HOLD SEATS → ISSUE TICKET → RETAG BAGS → NOTIFY**

If a later step repeatedly fails, previously completed actions can be compensated to prevent inconsistent state.

### 📦 Transactional Outbox

Database changes and outgoing messages are committed together.

A separate relay publishes messages to RabbitMQ, preventing events from being lost between database transactions and message delivery.

### 🔁 Idempotent Processing

The system handles duplicate message delivery safely using:

* Processed-message tracking
* Saga state protection
* Partner idempotency keys

This provides reliable effects over an **at-least-once delivery** system.

### 🪑 Concurrency-Safe Seat Allocation

Seat inventory is protected using PostgreSQL transactions and atomic conditional updates, preventing multiple workers from successfully claiming the same seat.

### 💥 Chaos Engineering

Workers can be intentionally terminated during processing to simulate real failures.

The system verifies that work can recover without corrupting booking state.

### 🧮 Rebooking Optimization

Two planning strategies can be compared:

* **Greedy** — fast heuristic approach
* **CP-SAT** — constraint-based optimization using Google OR-Tools

The dashboard compares delay, recovery, CPU time, and other metrics.

### ✅ Invariant Verification

Six automated invariants verify system correctness, including:

* No seat overselling
* One terminal saga per disrupted booking
* At most one confirmed itinerary
* No compensation leaks
* Valid completed sagas
* Drained outbox

---

## 📊 Reliability Demonstration

FlightFlow includes failure and concurrency tests such as:

* **30% worker failures** during a run
* **0 invariant violations** after recovery
* **200 concurrent seat requests** against 50 seats → exactly 50 successful holds
* Duplicate message handling
* Worker crash recovery
* Partner API failures with retries and compensation

---

## 🖥️ Dashboard

The React dashboard provides operational visibility into the distributed system.

### Run Control

Configure disruption scenarios, planner strategy, seed, severity, and chaos parameters.

### Live Run

Monitor:

* Recovery progress
* Worker activity
* Queue depth
* Throughput
* Saga states
* Disruption events

On a fresh stack, before anyone has triggered a storm, Live Run falls back to a
seeded fixture so the page is never blank — see [Seed data](#-seed-data).

### Invariants

Run and inspect the six correctness checks.

### Saga Inspector

Search passengers and inspect the complete saga event timeline.

### Compare

Compare **Greedy vs CP-SAT** planning performance.

### Tenants

Monitor airline fairness: how evenly worker capacity was split across airlines.

### Flight Analytics

Scheduling and operations analytics computed over the database: departure-hour
volume and disruption rate, delay distribution, disruption causes, recovery
outcome per cause, worst-hit routes and airports, plus a derived insights panel
that shows the counts behind every observation. See
[Flight analytics](#-flight-analytics).

---

## 🌱 Seed data

Live Run's charts are built from the live counter stream, so on a fresh stack
they have nothing to draw until someone starts a run. `scripts/seed_data.py`
closes that gap: it drives one deterministic run (**seed 42, GREEDY**) through
the normal API flow, samples the counters once a second while it settles, and
writes the whole series plus the final snapshot to
`dashboard/public/fixtures/seed42_greedy.json`.

The dashboard loads that fixture **only** when the live API reports no affected
bookings, and labels it `Sample data` on screen with its capture time, so
seeded numbers are never mistaken for a live run. Start a run and the page
switches to live data on its own.

`docker compose up` runs this once automatically: the `seeder` service waits
for the API healthcheck and the consumers, seeds, and exits. It skips the work
if the fixture is already there.

```bash
make seed                      # seed if the fixture is missing
make seed-force                # re-seed and overwrite it

# or against a stack you are already running, outside Docker:
python scripts/seed_data.py --force --preset storm --severity 0.9
```

Affected-booking count is emergent, not a dial — it falls out of preset size,
severity and which flights the storm hits. `--target-bookings` only sets the
band the script warns outside of; use `--preset` / `--severity` to move the
number. The fixture is generated at runtime rather than shipped; commit it if
you want a fresh clone to show data before the stack has ever been seeded.

---

## 📈 Flight analytics

`/analytics` in the dashboard is a scheduling and operations analytics view
built directly on the FlightFlow database. It replaced an embedded Grafana
page, which added a second service and a second query language to maintain for
charts the app can compute itself.

**Panels**

| Panel | Question it answers | Source |
| --- | --- | --- |
| Departures by hour | Which departure windows carry the most flights, and what share was hit? | `flights` grouped by `EXTRACT(HOUR FROM sched_dep_at)` |
| Delay distribution | How severe are the delays that exist? | `flights.dep_at - flights.sched_dep_at`, bucketed in SQL |
| Disruption causes | What drove the disruption? | `disruption_events` by cause and type |
| Recovery by cause | Which causes are hardest to recover from? | `disruption_events` → `booking_segments` → `sagas` |
| Worst-hit routes / airports | Where did the schedule break? | `flights` joined to `airports` |
| Recovery performance | How did the saga machinery behave? | `sagas`, `dead_letters` |
| What the data shows | Observations, each with its supporting counts | derived from the above |

Everything is aggregated in Postgres by `GET /analytics`; the browser never
pulls a table down to count rows. The pure derivations live in
`src/reflight/analytics/insights.py` and are unit-tested in
`tests/unit/test_analytics_insights.py`.

**Honesty rules this page follows**

* The underlying network is **synthetic** — produced by the seeded scenario
  generator — and the page says so in a provenance strip rather than implying
  an operational feed.
* A departure is only late where a scenario injected a delay, so "undisrupted"
  is labelled as such instead of being sold as observed on-time performance.
* The generator lays every departure inside one synthetic 24-hour day, so
  day-of-week analysis is listed under *what this data can't answer yet*
  rather than approximated. Hour-of-day volume is near-uniform by
  construction, and the insight that names the worst departure hour says so.
* Thin samples are labelled **Limited data** instead of being presented as
  findings. Nothing claims significance or prediction.
* The analytics page reads the database only. It never falls back to the Live
  Run sample fixture, so live and sample numbers are never mixed.

---

## 🏗️ Architecture

```text
                    React Dashboard
                           │
                    REST + SSE
                           │
                       FastAPI
                           │
        ┌──────────────────┼──────────────────┐
        ↓                  ↓                  ↓
     Planner            Relay            Workers × N
        │                  │                  │
        └────────────── RabbitMQ ─────────────┘
                           │
                      PostgreSQL
                    ↙      ↓       ↘
                 Sagas   Outbox   Inventory
                           │
                    Mock Partners

       Observability → OpenTelemetry
                    → Prometheus
```

---

## 🛠️ Tech Stack

| Layer              | Technologies                          |
| ------------------ | ------------------------------------- |
| Frontend           | React, TypeScript, Vite, Tailwind CSS |
| Backend            | Python, FastAPI, SQLAlchemy           |
| Database           | PostgreSQL                            |
| Messaging          | RabbitMQ                              |
| Caching / Fairness | Redis                                 |
| Object Storage     | MinIO                                 |
| Optimization       | Google OR-Tools CP-SAT                |
| Real-time          | Server-Sent Events                    |
| Observability      | OpenTelemetry, Prometheus             |
| Infrastructure     | Docker, Kubernetes, KEDA              |
| Testing            | Pytest, k6                            |
| CI/CD              | GitHub Actions                        |

---

## 🎯 Application

FlightFlow demonstrates how distributed systems can support **airline disruption management**, where large numbers of passenger recovery operations must be processed concurrently while preserving correctness.

The same reliability patterns can also apply to other systems involving **high-volume workflows, reservations, inventory, payments, logistics, and asynchronous task processing**.

> **Note:** FlightFlow uses synthetic airline data and mock partner services. It is an engineering simulation and does not connect to real airline reservation systems.
