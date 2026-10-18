# Seed fixtures

`seed42_greedy.json` is generated, not hand-written. It is a real captured run
(seed 42, GREEDY) produced by `scripts/seed_data.py`, which the compose
`seeder` service runs once on first boot.

The dashboard's Run Progress page loads it only when the live API reports no
affected bookings, and labels it "Sample data" on screen.

Regenerate it against a running stack:

    make seed-force

The generated file is gitignored, since it is build output rather than source.
Commit it with `git add -f dashboard/public/fixtures/seed42_greedy.json` if you
want a fresh clone to show data before the stack has ever been seeded.
