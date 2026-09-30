**Concept Paper: Trust-by-Design — A Customer-Centric AI Privacy Framework for New Telecom Ltd.** 

_Responsible AI Adoption under Bangladesh's Personal Data Protection Act (PDPA)_ 

# **1. Deconstruction of the Problem** 

New Telecom Ltd has mature technical security controls but fragmented privacy ownership across business units, just as it scales six AI-enabled use cases touching financial, location, and behavioral data. The PDPA converts prior best practices into binding duties — lawful basis, minimization, explainability, cross-border transfer control, and child-data protection — while AI introduces new threats: bias, opacity, prompt injection, and model inversion. The core failure is not a missing control but missing visibility and accountability: no single source of truth for what data exists, which AI systems touch it, and who answers for each decision. 

# **2. Key Privacy Challenges** 

- Compliance: no live data/AI inventory; unclear lawful basis and transfer treatment for AI vendors. 

- Security: expanded attack surface (prompt injection, model inversion); undefined AI-vendor risk criteria. 

- Ethical: opaque, potentially biased automated decisions in fraud, churn, and marketing models; weak protection for children's data. 

- Organizational: privacy owned by many units with no single accountable authority; customers have no visibility into or control over AI use. 

# **3. Proposed Approach — "Trust Cockpit + PRISM Governance"** 

Rather than a compliance-only checklist, we propose a customer-facing layer paired with an engineering-embedded governance engine. 

**Customer Privacy Cockpit:** an in-app dashboard (Bangla/English) where customers see which AI systems touch their data, toggle consent per use case, request a plain-language explanation for any automated decision, and view an immutable, timestamped consent log — turning PDPA rights (access, withdrawal, transparency) into a self-service product feature rather than a manual back-office process. 

**PRISM Governance Engine:** a live AI/data Register; Risk-tiering with DPIA required before any high-tier model ships, enforced as a CI/CD gate ("DPIA-as-code") so non-compliant models cannot deploy; privacy-preserving design by default (on-device/federated inference, synthetic training data); continuous Security monitoring for bias, prompt injection, and model inversion; and a vendor "Privacy Passport" score (residency, retention, sub-processing, certification) reviewed before any AI procurement decision. 

# **4. Expected Impact** 

For customers: visible control over personal data, faster self-served rights fulfillment, explainable AI decisions, and stronger safeguards for minors. For New Telecom: audit-ready evidence (register, DPIA logs, consent ledger) for PDPA inspection; reduced breach and reputational risk; faster and safer AI rollout because governance is built into deployment pipelines rather than bolted on afterward; and a differentiated brand position as Bangladesh's most transparent digital operator — turning compliance into a trust advantage. 

# **5. Applicability to Bangladesh** 

With mobile access driving most digital usage and PDPA still newly enacted with limited enforcement precedent, telecom operators are natural trust anchors for the wider digital economy, as fintech, health-tech, and e-commerce increasingly rely on telecom-linked identity and data. A Bangla-first, low-literacy-friendly Trust Cockpit sets a practical, replicable transparency standard other regulated sectors can adopt, while DPIA-as-code offers Bangladeshi regulators a concrete, auditable reference model for PDPA enforcement guidance — directly addressing the case's own observation that some areas still need regulatory clarification. 

