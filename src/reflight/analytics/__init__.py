"""Read-only analytics aggregations for the Flight Analytics page.

Split deliberately in two:

* `queries` holds the SQL and the Session-bound fetch functions. Every
  aggregation runs in Postgres -- the browser never pulls a table down to
  count rows itself.
* `insights` holds pure functions that turn those aggregates into stated
  observations. No database, no I/O, so they are unit-testable.
"""
