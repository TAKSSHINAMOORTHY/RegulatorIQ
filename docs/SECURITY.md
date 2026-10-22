# Security Architecture & Threat Model

RegulatorIQ enforces comprehensive defense-in-depth across the API, container runtime, and web client.

---

## 1. Threat Mitigation Matrix

| Threat Vector | Mitigation Strategy | Enforcement Layer |
| :--- | :--- | :--- |
| **Data Exfiltration / Malicious Links** | Citation links strictly allow-listed to `*.rbi.org.in`. Non-whitelisted hosts rendered as plain text. | Web client + API response sanitizer |
| **Prompt Injection** | Deterministic injection pattern scanner rejects jailbreaks with code 400. | Agent router & preflight guard |
| **API DoS / Resource Exhaustion** | In-memory token bucket rate limiter (30 req burst, 200/day cap per IP). | FastAPI Middleware |
| **Buffer Overflow / Huge Payload** | Body size limiter terminates incoming requests > 64 KB with code 413. | FastAPI Middleware |
| **Container Privilege Escalation** | Image runs as non-root user `appuser` (UID 1000) with read-only root filesystem. | Docker runtime & Compose |
| **Cross-Site Scripting (XSS)** | Nonce-based Content Security Policy with `strict-dynamic` and zero `dangerouslySetInnerHTML`. | Next.js Middleware & React renderer |
| **Zip Slip / Path Traversal** | Index unpacker validates all relative paths stay strictly within target directory. | `api/index_fetch.py` |
| **Accidental PII Logging** | Regex redaction cleans emails, phone numbers, PAN, and Aadhaar numbers before writing traces. | `api/observability.py` & `api/feedback_store.py` |
