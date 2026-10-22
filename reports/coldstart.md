# RegulatorIQ Cold-Start Latency Report

**Target Tested:** `http://127.0.0.1:8005`  
**Measured At:** `2026-10-22T09:25:13.430482+00:00`  

| Metric | Measured Duration | Free Host Expectations |
| :--- | :--- | :--- |
| **Time-to-First-Byte (TTFB)** | **0.008s** | < 1.0s (warm), 15-30s (cold) |
| **Time-to-Ready (/ready)** | **0.001s** | < 0.5s (warm), 20-45s (cold index load) |
| **First Answer Stream Latency** | **0.141s** | < 2.0s (warm inference) |

## Implications for Keep-Warm Schedule

- For scale-to-zero providers (Cloud Run, Render Free), 10 pings/day warms instances during peak business hours (07:00 - 22:00 IST).
- For persistent Always-Free VMs (Oracle Ampere, AWS EC2), memory-mapped indices avoid disk re-reads and maintain sub-second TTFB continuously.
