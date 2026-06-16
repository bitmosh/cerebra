# Event Sourcing

Event sourcing is an architectural pattern where state changes are persisted as an
immutable sequence of events rather than updating records in place.

## Core idea

Instead of storing "the current balance is $450", you store:
- `AccountOpened { balance: 500 }`
- `MoneyWithdrawn { amount: 50 }`

Current state is derived by replaying events from the beginning (or from a snapshot).

## Key properties

- **Audit trail**: every change is recorded with a timestamp and actor.
- **Temporal queries**: reconstruct state at any point in time by replaying up to
  that moment.
- **Projection rebuilds**: derive new read models from the event log at any time
  without touching the source of truth.
- **Event-driven integration**: downstream services subscribe to the event stream
  instead of polling for state changes.

## Trade-offs

### Advantages

- Complete audit trail with no extra work
- Ability to replay history and rebuild projections
- Natural fit for event-driven architectures
- Decouples write model (command + event) from read model (projection)

### Disadvantages

- Read complexity: queries may require materializing projections
- Eventual consistency between projections
- Long event streams require snapshotting for acceptable performance
- Schema evolution is harder — you cannot edit past events

## Snapshotting

For long-lived aggregates, reading all events from the beginning becomes slow.
A snapshot captures state at a point in time; replay starts from the nearest
snapshot rather than event zero.

## When to use

Event sourcing fits well when:
- Auditability is a first-class requirement (finance, healthcare, legal)
- You need to support temporal queries ("what did the system think at time T?")
- Multiple projections serve different read needs from the same write model
- The domain is naturally event-shaped (order placed, payment received, item shipped)

Avoid it when state history is irrelevant, the domain is simple CRUD, or the team
lacks experience with eventual consistency patterns.
