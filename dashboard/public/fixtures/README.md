# Seed fixtures

`seed42_greedy.json` is generated, not hand-written. It is a real captured run
(seed 42, GREEDY) produced by `scripts/seed_data.py`, which the compose
`seeder` service runs once on first boot.

The dashboard's Run Progress page loads it only when the live API reports no
affected bookings, and labels it "Sample data" on screen.

Regenerate it against a running stack:

    make seed-force

The generated file is committed on purpose. The hosted demo (Dockerfile.render)
builds the dashboard straight from the repo and has no seeder service, so a
fixture that is not committed leaves the deployed Live Run page empty.

Re-seeding rewrites it, which shows up as a normal diff. Commit the new one if
the run it captured is a better demo, otherwise `git checkout` it.
