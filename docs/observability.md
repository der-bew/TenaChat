# Observability Guide

This document describes the logging conventions, correlation IDs, and monitoring approach for TenaChat.

---

## Correlation IDs

Every chat request is assigned a **correlation ID** for end-to-end tracing.

- If the client sends an `X-Request-Id` header, that value is used.
- Otherwise, a UUID is generated server-side.
- The correlation ID appears in all log lines for that request under `correlation_id`.

**Frontend usage (optional):**

```typescript
const requestId = crypto.randomUUID();
fetch(`${API_BASE_URL}/api/chat/chat`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-Request-Id": requestId,
  },
  body: JSON.stringify(payload),
});
```

---

## Structured log fields

The backend emits structured log lines. Key fields:

| Field | Description |
|-------|-------------|
| `correlation_id` | Request-scoped ID for tracing |
| `conversation_id` | Conversation-scoped ID |
| `user` | Anonymized user reference |
| `triage` | Triage level: `routine` or `emergency` |
| `sources` | Number of sources retrieved |
| `latency_ms` | Retrieval latency in milliseconds |
| `anonymous` | Whether the request is anonymous |
| `cached` | Whether a cached response was returned |

### Example log lines

```
INFO  Processing text chat | user=abc123 | conversation=xyz | anonymous=False
INFO  Triage result for conversation xyz: routine
INFO  Retrieval metrics — conversation: xyz | sources: 3 | has_evidence: True | latency_ms: 124.5
INFO  Generated AI response | user=abc123 | triage=routine | sources=3
```

```
INFO  Triage result for conversation xyz: emergency
INFO  Generated AI response | user=abc123 | triage=emergency | sources=0
```

```
INFO  Retrieval metrics — conversation: xyz | sources: 0 | has_evidence: False | latency_ms: 98.2
INFO  Insufficient evidence for conversation xyz — returning fallback response
```

---

## Key metrics to monitor

### Chat flow

| Metric | How to derive |
|--------|---------------|
| Request rate | Count of `POST /api/chat/chat` calls |
| Cache hit rate | `cached=True` vs total requests |
| Emergency escalation rate | `triage=emergency` log count |
| Fallback rate | "Insufficient evidence" log count |
| Error rate | HTTP 5xx responses |
| p50 / p95 response latency | Measure from request to response |

### Retrieval

| Metric | How to derive |
|--------|---------------|
| Retrieval latency | `latency_ms` field in retrieval metrics log |
| Source count per request | `sources=N` in retrieval metrics log |
| Zero-source rate | `sources=0` in retrieval metrics log |
| Has-evidence rate | `has_evidence=True` vs total |

### Safety

| Metric | How to derive |
|--------|---------------|
| Emergency detection rate | `triage=emergency` count |
| Non-health refusal rate | Log from refusal message path |
| Fallback (insufficient evidence) rate | "Insufficient evidence" log count |

---

## Recommended dashboard foundations

If using a log aggregation tool (e.g. Datadog, Grafana Loki, CloudWatch):

1. **Parse structured logs** — extract `correlation_id`, `triage`, `sources`, `latency_ms`, `cached`.
2. **Create counters** for emergency rate, fallback rate, cache hit rate, error rate.
3. **Create histograms** for retrieval latency and end-to-end response latency.
4. **Alert on** emergency rate spike, error rate spike, zero-source rate above threshold.

### Minimal approach without a dedicated tool

Use `grep`/`jq` on application logs:

```bash
# Count emergency escalations in the last hour
grep "triage=emergency" app.log | wc -l

# Find all requests with zero sources
grep "sources: 0" app.log

# Average retrieval latency
grep "latency_ms" app.log | grep -oP 'latency_ms: \K[\d.]+' | awk '{sum+=$1; n++} END {print sum/n}'
```

---

## Health check endpoint

`GET /health` returns `{"status": "healthy", "environment": "..."}`.

Suitable for liveness probes. Use it in Docker Compose, Kubernetes, or load balancer health checks.

---

## Future improvements

- Add OpenTelemetry traces for distributed tracing across frontend → backend → LLM calls.
- Emit token usage per LLM call (available from OpenAI response metadata).
- Track conversation completion rate and follow-up rate as product metrics.
- Add safety incident logging (persisted, queryable records when emergency escalation fires).
