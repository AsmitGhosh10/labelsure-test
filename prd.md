# SIH26034 — AI Legal Metrology Compliance System

## Master Product Requirements Document (PRD)

| Property | Value |
|----------|-------|
| **Version** | 1.0 |
| **Project** | SIH26034 |
| **Category** | Software |
| **Organization** | Department of Consumer Affairs |
| **Primary Technology** | OCR + Computer Vision + RAG + Deterministic Rule Engine + LLM-assisted Extraction |
| **Target** | SIH 2026 |
| **Development Constraint** | 12-day hackathon sprint |
| **Development Style** | AI-agent-assisted / rapid prototyping |

---

## Table of Contents

1. [Product Vision](#1-product-vision)
2. [Core Product Principle](#2-core-product-principle)
3. [Primary User](#3-primary-user)
4. [Secondary Users](#4-secondary-users)
5. [End-to-End Workflow](#5-end-to-end-workflow)
6. [Technology Stack](#6-technology-stack)
7. [Regulatory Knowledge Base](#7-regulatory-knowledge-base)
8. [RAG Requirements](#8-rag-requirements)
9. [OCR Requirements](#9-ocr-requirements)
10. [Fields to Extract](#10-fields-to-extract)
11. [Rule Engine](#11-rule-engine)
12. [Supported Rule Types](#12-supported-rule-types)
13. [Compliance States](#13-compliance-states)
14. [Overall Decision Logic](#14-overall-decision-logic)
15. [Confidence Engine](#15-confidence-engine)
16. [Confidence Components](#16-confidence-components)
17. [Manual Review Prioritization](#17-manual-review-prioritization)
18. [Recommended Initial Thresholds](#18-recommended-initial-thresholds)
19. [Confidence-Based Inspector Queue](#19-confidence-based-inspector-queue)
20. [Visual Evidence](#20-visual-evidence)
21. [Human-in-the-Loop](#21-human-in-the-loop)
22. [LLM Rules](#22-llm-rules)
23. [Product Context](#23-product-context)
24. [Image Quality Gate](#24-image-quality-gate)
25. [Multi-Image Support](#25-multi-image-support)
26. [Compliance Score](#26-compliance-score)
27. [Dashboard](#27-dashboard)
28. [Inspection Repository](#28-inspection-repository)
29. [PDF Report](#29-pdf-report)
30. [Security](#30-security)
31. [Performance Targets](#31-performance-targets)
32. [Offline/Online Architecture](#32-offlineonline-architecture)
33. [Error Handling](#33-error-handling)
34. [Testing Requirements](#34-testing-requirements)
35. [Important Legal Safety Rule](#35-important-legal-safety-rule)
36. [Development Agent Rules](#36-development-agent-rules)
37. [Mandatory Agent Reporting Rule](#37-mandatory-agent-reporting-rule)
38. [Required Report Format](#38-required-report-format)
39. [Git Requirements](#39-git-requirements)
40. [Definition of Done](#40-definition-of-done)
41. [Final MVP](#41-final-mvp)
42. [Final Demo Scenario](#42-final-demo-scenario)

---

## 1. Product Vision

Build an AI-assisted inspection platform that allows a Legal Metrology enforcement officer to photograph or upload a packaged commodity and automatically:

1. Assess image quality
2. Extract package declarations using OCR
3. Identify relevant product information
4. Retrieve applicable Legal Metrology requirements using RAG
5. Validate declarations using a deterministic compliance engine
6. Detect potential violations
7. Calculate confidence for every finding
8. Prioritize products requiring manual inspection
9. Provide visual evidence for every finding
10. Generate an inspection/compliance report

**The system must assist inspectors rather than replace statutory/legal judgment.**

---

## 2. Core Product Principle

The system must follow:

**AI extracts → RAG retrieves → Rules decide → Confidence prioritizes → Human verifies.**

**The LLM must never independently make the final legal compliance decision.**

---

## 3. Primary User

### Legal Metrology Inspector

The inspector should be able to:

- Capture a package
- Upload an image
- Receive an automated assessment
- Understand why a product was flagged
- Manually verify uncertain findings
- Approve/reject the system's suggested finding
- Generate a report
- Search historical inspections

---

## 4. Secondary Users

### Supervisors

Can view:

- Inspection statistics
- Violation trends
- Inspector activity
- Product categories
- Manufacturers
- Recurring violations

### Administrators

Can manage:

- Users
- Rule versions
- Regulatory documents
- Confidence thresholds
- System configuration

---

## 5. End-to-End Workflow

```
Product
  ↓
Camera / Upload
  ↓
Image Quality Assessment
  ↓
Image Preprocessing
  ↓
OCR
  ↓
Text + Bounding Boxes + Confidence
  ↓
Structured Field Extraction
  ↓
Product Classification / Context
  ↓
RAG Regulatory Retrieval
  ↓
Applicable Rules
  ↓
Deterministic Compliance Engine
  ↓
Confidence Engine
  ↓
┌──────────────┬───────────────┬───────────────┐
│              │               │
🟢 PASS       🟡 REVIEW       🔴 FAIL
│              │               │
└──────────────┴───────────────┘
  ↓
Evidence + Explanation
  ↓
Inspector Dashboard
  ↓
PDF Report
```

---

## 6. Technology Stack

### Frontend

- Next.js
- React
- TypeScript
- Tailwind CSS
- shadcn/ui
- Recharts
- Leaflet (where GIS is required)

### Backend

- Python
- FastAPI
- Pydantic
- SQLAlchemy

### Computer Vision

- OpenCV
- Pillow
- NumPy

### OCR

**Primary:**
- PaddleOCR

**Optional:**
- Alternative OCR provider/model for difficult cases

### RAG

> **Use existing:** `./rag/Multimodal_RAG_Project/` (hybrid retrieval with FAISS + BM25 + RRF)

**Components:**
- Qdrant or pgvector (vector database)
- Embedding model (Sentence Transformers or CLIP)
- BM25/keyword retrieval
- Semantic retrieval
- Hybrid fusion (Reciprocal Rank Fusion)
- Cross-Encoder reranking

**Adaptation required:**
- Integrate with Legal Metrology knowledge base
- Configure for regulatory document ingestion
- Ensure source citations include rule references

### LLM

LLM may be used for:

- OCR normalization
- Field extraction
- Query interpretation
- RAG response generation
- Explanation generation

**LLM must NOT be the final compliance decision-maker.**

### Database

- PostgreSQL

### Storage

**Development:**
- Local filesystem

**Production-style prototype:**
- MinIO/S3-compatible storage

### Reports

- HTML → PDF or ReportLab

---

## 7. Regulatory Knowledge Base

The RAG database must prioritize authoritative sources.

### Primary Sources

- Department of Consumer Affairs
- Legal Metrology official publications
- Legal Metrology (Packaged Commodities) Rules, 2011
- Official amendments
- Official notifications
- Official circulars/orders
- Other government-issued documents relevant to packaged commodities

### Source Priority Hierarchy

1. Official Government Document
2. Official Amendment/Notification
3. Official Department Guidance
4. Other authoritative source
5. **Never use random blogs as legal authority**

### Metadata Requirements

Every regulatory statement must have:

- Document
- Rule / Clause
- Page
- Version
- Effective date
- Source URL

---

## 8. RAG Requirements

### ⚠️ IMPORTANT: Reuse Existing Multimodal RAG Project

**Do NOT implement RAG from scratch.** An existing production-grade Multimodal RAG system is available:

**Location:** `./rag/Multimodal_RAG_Project/`

**Repository Path:** `/Users/mohit/Documents/Default Project/rag/Multimodal_RAG_Project/`

**Existing Capabilities:**
- Hybrid Retrieval (FAISS + BM25 + Reciprocal Rank Fusion)
- Multimodal Search (Text + Image via CLIP)
- Real-time RAG Chat Interface
- Explainable Retrieval & Ranking with confidence scoring
- PDF, DOCX, TXT ingestion
- Cross-modal search capabilities
- Production-grade modular architecture

**Development Instructions:**
1. **First:** Review the existing `Multimodal_RAG_Project/README.md` and architecture
2. **If core functionality exists:** Adapt and integrate with Legal Metrology rules/knowledge base
3. **If modifications needed:** Only implement domain-specific customizations (e.g., custom regulatory ingestion, legal domain embeddings)
4. **Integration point:** Ensure the RAG system can be queried with product context and returns regulatory rules with source citations

---

### RAG System Requirements

The RAG system must:

- Ingest regulatory PDFs/documents
- Extract text
- Preserve document structure
- Identify rules/clauses
- Maintain page numbers
- Maintain effective dates
- Maintain amendment/version information
- Create embeddings
- Support semantic retrieval
- Support keyword retrieval
- Support metadata filtering
- Return source citations

### Example Retrieval

**User/Product:** 500g packaged biscuit

**RAG should retrieve relevant requirements concerning:**

- Packaged commodity declarations
- Net quantity
- MRP
- Manufacturer/packer/importer
- Consumer information
- Applicable commodity-specific requirements

---

## 9. OCR Requirements

OCR must return structured data:

```json
{
  "text": "MRP ₹250",
  "confidence": 0.96,
  "bounding_box": [x1, y1, x2, y2]
}
```

For every extracted field, maintain:

- Original OCR text
- Normalized value
- OCR confidence
- Bounding box
- Image ID

**Important rules:**
- Never invent information
- If OCR cannot confidently read something, return: `NOT_DETECTED` or `MANUAL_REVIEW`

---

## 10. Fields to Extract

The system should attempt to identify applicable declarations such as:

- Product name
- Brand
- Manufacturer
- Manufacturer address
- Packer
- Packer address
- Importer
- Importer address
- Net quantity
- Unit
- MRP
- Manufacturing date
- Packing date
- Import date
- Expiry/use-by/best-before (where applicable)
- Consumer-care information
- Customer-care phone
- Customer-care email
- Country of origin (where applicable)

**Important:** The exact applicability of each field must come from the retrieved regulatory rules, not assumptions.

---

## 11. Rule Engine

The rule engine must be deterministic.

**Rules should be stored as structured data rather than buried inside application code.**

### Example Rule Structure

```json
{
  "rule_id": "NET_QTY_001",
  "field": "net_quantity",
  "rule_type": "MANDATORY",
  "validation": "PRESENT_AND_VALID",
  "severity": "HIGH",
  "source": {
    "document": "...",
    "rule": "...",
    "page": 12
  }
}
```

---

## 12. Supported Rule Types

### Presence
Is the declaration present?

### Format
Does the declaration follow the applicable format?

### Numeric Validation
Is the value numeric?

### Unit Validation
Is the unit valid for the applicable declaration?

### Cross-Field Validation
Example: MRP + tax declaration + quantity

### Date Validation
Check:
- Presence
- Recognizable format
- Logical date
- Relationships (where applicable)

### Readability
Check whether text is sufficiently readable.

### Font Measurement
Where technically possible:

```
pixel height
  ↓
scale/calibration
  ↓
estimated physical size
```

**If physical scale cannot be reliably established:** `MANUAL_REVIEW`

### Placement
Only implement placement rules where they can be reliably measured.

---

## 13. Compliance States

Every individual check must have one of three states:

### ✓ PASS
Evidence sufficiently demonstrates compliance.

### ✗ FAIL
A clear violation has been detected.

### ⚠ MANUAL_REVIEW
The system cannot confidently determine compliance.

---

## 14. Overall Decision Logic

**The system must NOT simply average scores.**

**Use this logic:**

```
IF clear mandatory violation exists:
    NON_COMPLIANT
ELSE IF mandatory requirement cannot be confidently evaluated:
    MANUAL_REVIEW
ELSE:
    COMPLIANT
```

**Note:** Warnings may affect the score but should not automatically create a legal violation unless the configured rule says so.

---

## 15. Confidence Engine

Every AI/CV finding must receive a confidence score.

### Example

```
MRP detection          97%
Net quantity           94%
Manufacturer           91%
Manufacturing date     87%
Consumer care          63%
Font measurement       58%
```

**Confidence should reflect the reliability of the specific finding, not legal certainty.**

---

## 16. Confidence Components

Where practical, calculate confidence using:

- OCR confidence
- Field extraction confidence
- Pattern/regex confidence
- Bounding-box quality
- Image quality
- Cross-validation
- RAG retrieval confidence
- Rule applicability confidence

**Important:**
- Do not claim mathematically calibrated probabilities unless the system has actually been calibrated
- Call it **"System Confidence"** rather than "Probability of violation"

---

## 17. Manual Review Prioritization

**This is a core feature.**

The system should classify findings into three categories:

### 🟢 AUTO ACCEPT
High confidence and all mandatory rules pass.

**Example:**
- Confidence: 96%
- No violations detected

### 🟡 REVIEW
Uncertain extraction or measurement.

**Example:**
- Confidence: 68%
- Reason: MRP OCR ambiguous
- Manual verification recommended

### 🔴 PRIORITY REVIEW
Low confidence combined with a potentially serious violation.

**Example:**
- Confidence: 54%
- Potential violation: Mandatory declaration may be missing

---

## 18. Recommended Initial Thresholds

These should be configurable.

**For the prototype:**

- ≥ 90% → High confidence
- 70–89% → Review recommended
- < 70% → Manual review

**Important:** Do not present these thresholds as legally mandated. They are system configuration parameters.

---

## 19. Confidence-Based Inspector Queue

### Dashboard Structure

**MANUAL REVIEW QUEUE**

| Priority | Criteria | Confidence |
|----------|----------|-----------|
| 🔴 Priority | Potential mandatory violations | < 70% |
| 🟡 Review | Uncertain findings | 70–89% |
| 🟢 Auto processed | High-confidence results | ≥ 90% |

### Sort Options

Inspector can sort by:

- Confidence
- Violation severity
- Product
- Manufacturer
- Date
- Location

---

## 20. Visual Evidence

Every finding must provide evidence.

### Example

```
❌ Consumer-care declaration
Confidence: 94%

Evidence:
[Highlighted image region]

OCR: "No customer care information detected"

Applicable requirement: [Rule reference]

Decision: FAIL
```

### For Detected Text

- Bounding box
- OCR text
- Confidence

---

## 21. Human-in-the-Loop

### Inspector Workflow

```
AI Decision
  ↓
Review
  ↓
Accept AI finding
OR
Override
  ↓
Reason
  ↓
Final Inspector Decision
```

### System Record

The system must record:

- AI decision
- Inspector decision
- Inspector ID
- Timestamp
- Reason
- Evidence

---

## 22. LLM Rules

### LLMs MAY be used for:

- OCR cleanup
- Entity extraction
- Natural-language query understanding
- Regulatory question answering
- RAG synthesis
- Explanation generation
- Multilingual translation

### LLMs MUST NOT:

- Invent regulations
- Invent missing package information
- Fabricate citations
- Make unsupported legal claims
- Override deterministic rules
- Declare legal guilt autonomously

**If evidence is unavailable:** Insufficient evidence — manual verification required.

---

## 23. Product Context

The system should support product context such as:

- Product category
- Commodity type
- Quantity
- Domestic/imported
- Package type

**This context determines which regulatory rules should be retrieved.**

---

## 24. Image Quality Gate

Before OCR, calculate:

- Resolution
- Blur
- Brightness
- Contrast
- Glare
- Perspective distortion

### If the image is unusable:

```
IMAGE QUALITY: POOR

Please:
• Move closer
• Avoid glare
• Improve lighting
• Keep label flat
• Capture again
```

**Do not attempt a legal decision from unusable imagery.**

---

## 25. Multi-Image Support

Allow multiple images of the same product.

### Example

- Front
- Back
- Side
- Bottom

**Combine evidence across images.**

**Why this matters:** Mandatory declarations may not appear on one side.

---

## 26. Compliance Score

Provide a score for inspection prioritization, not legal validity.

### Example

```
Compliance Assessment
92 / 100

Mandatory declarations: 9/10
Formatting: 10/10
Readability: 9/10
Potential violations: 1
```

**Clearly state:** Score is an automated assessment and does not replace statutory inspection.

---

## 27. Dashboard

### Display Metrics

- Total inspections
- Compliant
- Non-compliant
- Manual review
- Average confidence
- Common violations
- Recent inspections

### Charts

- Compliance rate
- Violations by type
- Inspections over time
- Manufacturer/category trends
- Manual review rate

---

## 28. Inspection Repository

### Data Stored

Each inspection should store:

- Inspection ID
- Product
- Image(s)
- OCR result
- Extracted fields
- Applicable rules
- Rule version
- Compliance result
- Confidence
- Violations
- Evidence
- Inspector decision
- Timestamp
- Report

### Search Capabilities

Search by:

- Product
- Manufacturer
- Inspection ID
- Date
- Status
- Violation

---

## 29. PDF Report

Generate a professional report containing:

### Header

**LEGAL METROLOGY INSPECTION REPORT**

### Information

- Inspection ID
- Date/time
- Inspector
- Product
- Manufacturer

### Image

Original package image.

### Extracted Declarations

```
Field | Detected Value | Confidence | Status
```

### Compliance

- Overall status
- Compliance assessment

### Violations

For every violation:

- Violation
- Evidence
- Confidence
- Applicable requirement
- Source

### Manual Verification

- Inspector: _____________
- Decision: _____________
- Reason: _____________
- Signature/approval field: _____________

---

## 30. Security

Implement:

- Authentication
- Role-based access
- Secure file handling
- Input validation
- Database access controls
- Audit logging
- No sensitive information in logs
- Configurable retention

---

## 31. Performance Targets

### Latency Targets

- Image → OCR result: < 5 sec
- Image → compliance result: preferably < 10 sec

**Do not sacrifice correctness simply to hit latency targets.**

### Optimization Strategies

- Image resizing
- Selective OCR preprocessing
- Caching
- Asynchronous processing
- Avoiding unnecessary LLM calls
- Vector search caching

---

## 32. Offline/Online Architecture

The system should be designed so that OCR and deterministic rule evaluation can run locally where practical.

### Online Services

Online services can be used for:

- LLM
- RAG infrastructure
- Cloud storage
- Advanced extraction

**Note:** The SIH problem does not impose the same fully-offline constraint, so online models/APIs can be considered unless the official competition rules impose additional restrictions.

**The architecture must still gracefully handle API failure.**

---

## 33. Error Handling

### OCR Failure

```
Unable to reliably read package.
Please capture another image.
```

### RAG Failure

```
Regulatory source could not be retrieved.
Manual verification required.

Never generate a regulatory answer without evidence.
```

### LLM Failure

Fall back to:

- OCR
- Regex
- Rule Engine

### Image Failure

Request recapture.

---

## 34. Testing Requirements

Create test products representing:

### Test A
**Fully compliant package**  
Expected: `COMPLIANT`

### Test B
**Missing mandatory declaration**  
Expected: `NON_COMPLIANT`

### Test C
**Invalid quantity/unit**  
Expected: `NON_COMPLIANT`

### Test D
**Poor OCR**  
Expected: `MANUAL_REVIEW`

### Test E
**Multiple violations**  
Expected: `NON_COMPLIANT`

### Test F
**Glare/blurred package**  
Expected: `RECAPTURE / MANUAL_REVIEW`

---

## 35. Important Legal Safety Rule

The application must describe itself as:

**"AI-assisted compliance screening"**

NOT:

**"Automated legal enforcement system"**

**Final enforcement action must remain with the authorized inspector.**

---

## 36. Development Agent Rules

Every coding agent working on this project MUST:

### Rule 1
Read the existing architecture before modifying files.

### Rule 2
Never rewrite working modules unnecessarily.

### Rule 3
Maintain backward compatibility with existing APIs unless explicitly instructed otherwise.

### Rule 4
Use modular architecture.

### Rule 5
Do not hardcode regulatory requirements inside frontend code.

### Rule 6
Do not hardcode regulatory citations.

### Rule 7
Keep regulatory data separate from application logic.

### Rule 8
Use environment variables for API keys.

### Rule 9
Never commit API keys.

### Rule 10
Never fabricate test results.

### Rule 11
Never claim a model is accurate without testing it.

### Rule 12
Never claim a regulation exists without a source.

### Rule 13
Every AI-generated extraction must maintain traceability to source evidence.

### Rule 14
Every compliance result must be reproducible from:

```
Input + Model version + Ruleset version + Configuration
```

### Rule 15
All important thresholds must be configurable.

### Rule 16 - RAG Implementation
**Do NOT build RAG from scratch.** The project includes a production-grade Multimodal RAG system at `./rag/Multimodal_RAG_Project/`. 

**RAG Development Steps:**
1. Review `./rag/Multimodal_RAG_Project/README.md` and existing architecture
2. Assess what can be directly reused (hybrid retrieval, embedding infrastructure, chat interface)
3. Only implement Legal Metrology-specific customizations:
   - Regulatory document ingestion pipelines
   - Legal domain embeddings (if needed)
   - Source citation formatting for regulations
   - Integration with compliance rule engine
4. If modifications are needed, extend the existing system rather than replacing it
5. Document all adaptations in the implementation report

---

## 37. Mandatory Agent Reporting Rule

After every successful implementation, the agent MUST create a detailed Markdown report.

### Report Storage

Reports must be stored in: `/docs/progress/`

### Naming Convention

- `STEP_01_IMAGE_PROCESSING_REPORT.md`
- `STEP_02_OCR_REPORT.md`
- `STEP_03_RAG_REPORT.md`
- `STEP_04_RULE_ENGINE_REPORT.md`
- `STEP_05_DASHBOARD_REPORT.md`
- `STEP_06_INTEGRATION_REPORT.md`

---

## 38. Required Report Format

Every implementation report MUST contain:

```markdown
# Implementation Report

## 1. Step
Name of implemented step.

## 2. Objective
What this implementation was supposed to accomplish.

## 3. Requirements Implemented
Detailed list.

## 4. Architecture
Explain the components and data flow.

## 5. Files Created
List every new file.

## 6. Files Modified
List every modified file.

## 7. Dependencies Added
List packages and versions.

## 8. APIs Added/Modified
Include endpoints and request/response schemas.

## 9. Models Used
Include:
- Model name
- Source
- Version
- Approximate size (if known)
- Purpose

## 10. Configuration
Environment variables and configuration parameters.

## 11. Tests Performed
List tests.

## 12. Test Results
Actual results only.

## 13. Performance
Include latency/memory measurements where available.

## 14. Known Limitations
Be honest about limitations.

## 15. Security Considerations
Relevant security issues.

## 16. Integration Requirements
What future modules need from this module.

## 17. Next Recommended Step
What should be implemented next.

## 18. Verification Checklist
- [ ] Build succeeds
- [ ] Tests pass
- [ ] API works
- [ ] Error handling works
- [ ] Documentation updated
```

**The agent must never write "all tests passed" unless it actually ran them.**

---

## 39. Git Requirements

### Use Logical Commits

```
feat: add image preprocessing
feat: integrate paddleocr
feat: add structured extraction
feat: add legal metrology rag
feat: add compliance rule engine
feat: add confidence scoring
feat: add inspector dashboard
feat: add pdf reports
```

### Avoid

- `update`
- `changes`
- `final`
- `final2`
- `finalfinal`

---

## 40. Definition of Done

A feature is considered complete only when:

- ✓ Code implemented
- ✓ Integration completed
- ✓ Tests written
- ✓ Tests executed
- ✓ Errors handled
- ✓ Documentation updated
- ✓ API documented
- ✓ Security reviewed
- ✓ Implementation report generated

---

## 41. Final MVP

The minimum SIH demonstration must support:

```
1. Upload/capture product
   ↓
2. Image quality check
   ↓
3. OCR
   ↓
4. Extract declarations
   ↓
5. Retrieve relevant regulations
   ↓
6. Run compliance rules
   ↓
7. Calculate confidence
   ↓
8. PASS / REVIEW / FAIL
   ↓
9. Show visual evidence
   ↓
10. Generate PDF report
```

---

## 42. Final Demo Scenario

**The ideal SIH demo should take approximately 2 minutes.**

### Demo Flow

```
Inspector: "Scan Product"
  ↓
📷 Package image
  ↓
OCR Results:
  MRP ✓
  Net Quantity ✓
  Manufacturer ✓
  Date ✓
  Consumer Care ❌
  ↓
RAG: Applicable requirement retrieved
  ↓
Decision Engine:
  MRP              ✓ 97%
  Net Quantity     ✓ 96%
  Manufacturer     ✓ 94%
  Date             ✓ 92%
  Consumer Care    ❌ 95%
  ↓
🔴 NON-COMPLIANT
Confidence: 95%

Reason: Mandatory declaration not detected.
  ↓
Inspector clicks: "View Evidence"
  ↓
Highlighted package image
+ Applicable rule
+ Source document
+ Page/Clause
  ↓
Generate Report
```

---

## Closing Note

The confidence-based inspection queue is the centerpiece of this system:

**The system doesn't just say whether something is compliant — it tells the inspector how confident it is and which packages actually require human attention.**

### Example Impact

```
100 scanned
🟢 72 — high-confidence compliant
🟡 18 — review recommended
🔴 10 — priority violations
```

This turns OCR into an actual inspection workflow optimization system, which is a much stronger SIH story than simply "we built an OCR app."
