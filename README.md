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

### Invariants

Run and inspect the six correctness checks.

### Saga Inspector

Search passengers and inspect the complete saga event timeline.

### Compare

Compare **Greedy vs CP-SAT** planning performance.

### Tenants & Ops

Monitor airline fairness and system observability through metrics and Grafana.

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
                    → Grafana
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
| Observability      | OpenTelemetry, Prometheus, Grafana    |
| Infrastructure     | Docker, Kubernetes, KEDA              |
| Testing            | Pytest, k6                            |
| CI/CD              | GitHub Actions                        |

---

## 🎯 Application

FlightFlow demonstrates how distributed systems can support **airline disruption management**, where large numbers of passenger recovery operations must be processed concurrently while preserving correctness.

The same reliability patterns can also apply to other systems involving **high-volume workflows, reservations, inventory, payments, logistics, and asynchronous task processing**.

> **Note:** FlightFlow uses synthetic airline data and mock partner services. It is an engineering simulation and does not connect to real airline reservation systems.
