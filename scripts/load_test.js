// k6 load test for the API's read path -- the endpoints the dashboard
// polls while a run is in flight.
//
//   RUN_ID=<run-id> k6 run scripts/load_test.js
//
// The write path (POST /runs/{id}/start) is deliberately not load-tested:
// one start per run is the real access pattern, and the interesting
// throughput number is sagas/second, which scripts/measure_run.py
// measures directly.
import http from 'k6/http'
import { check, sleep } from 'k6'

const BASE = __ENV.BASE || 'http://localhost:8000'
const API_KEY = __ENV.API_KEY || 'dev-local-key-change-me'
const RUN_ID = __ENV.RUN_ID

export const options = {
  stages: [
    { duration: '20s', target: 20 },
    { duration: '40s', target: 50 },
    { duration: '20s', target: 0 },
  ],
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500'],
  },
}

export default function () {
  if (!RUN_ID) throw new Error('set RUN_ID to an existing run')

  const params = { headers: { 'X-API-Key': API_KEY } }
  const responses = http.batch([
    ['GET', `${BASE}/runs/${RUN_ID}`, null, params],
    ['GET', `${BASE}/runs/${RUN_ID}/sagas/summary`, null, params],
    ['GET', `${BASE}/runs/${RUN_ID}/disruptions`, null, params],
    ['GET', `${BASE}/runs/${RUN_ID}/tenants`, null, params],
  ])

  responses.forEach((res) => check(res, { 'status is 200': (r) => r.status === 200 }))
  sleep(1)
}
