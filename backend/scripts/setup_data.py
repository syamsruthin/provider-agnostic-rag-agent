"""
Synthetic Data Generation Script for HealthGuard Agentic RAG.
Generates: SQLite DB (50 plans), CSV (500 providers), 3 Markdown policy docs.
"""

import csv
import os
import random
import sqlite3
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
DATA_DIR = BASE_DIR / "data"
DOCS_DIR = DATA_DIR / "docs"
LOGS_DIR = BASE_DIR / "logs"

DB_PATH = DATA_DIR / "insurance.db"
CSV_PATH = DATA_DIR / "providers.csv"


# ---------------------------------------------------------------------------
# 1. SQLite – plan_benefits (50 rows)
# ---------------------------------------------------------------------------
PLAN_TIERS = [
    ("BRZ", "Bronze"),
    ("SLV", "Silver"),
    ("GLD", "Gold"),
    ("PLT", "Platinum"),
    ("CAT", "Catastrophic"),
]

PLAN_SUFFIXES = ["Basic", "Plus", "Elite", "Premier", "Essential",
                 "Standard", "Enhanced", "Select", "Advantage", "Value"]


def _generate_plans(n: int = 50) -> list[dict]:
    plans = []
    used_ids = set()
    for i in range(n):
        tier_code, tier_name = random.choice(PLAN_TIERS)
        suffix = random.choice(PLAN_SUFFIXES)
        seq = f"{i + 1:03d}"
        plan_id = f"{tier_code}-{seq}"
        while plan_id in used_ids:
            seq = f"{random.randint(1, 999):03d}"
            plan_id = f"{tier_code}-{seq}"
        used_ids.add(plan_id)

        # Realistic ranges per tier
        premium_base = {"BRZ": 180, "SLV": 320, "GLD": 480, "PLT": 620, "CAT": 120}
        deductible_base = {"BRZ": 6000, "SLV": 3500, "GLD": 1500, "PLT": 500, "CAT": 8000}

        plans.append({
            "plan_id": plan_id,
            "plan_name": f"{tier_name} {suffix}",
            "monthly_premium": round(premium_base[tier_code] + random.uniform(-40, 80), 2),
            "individual_deductible": round(deductible_base[tier_code] + random.uniform(-300, 500), 2),
            "specialist_copay": round(random.uniform(30, 85), 2),
            "emergency_room_copay": round(random.uniform(150, 500), 2),
            "pharmacy_tier_1_copay": round(random.uniform(5, 30), 2),
        })
    return plans


def create_sqlite_db(plans: list[dict]) -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE plan_benefits (
            plan_id TEXT PRIMARY KEY,
            plan_name TEXT NOT NULL,
            monthly_premium REAL NOT NULL,
            individual_deductible REAL NOT NULL,
            specialist_copay REAL NOT NULL,
            emergency_room_copay REAL NOT NULL,
            pharmacy_tier_1_copay REAL NOT NULL
        )
    """)
    cur.executemany(
        "INSERT INTO plan_benefits VALUES (?,?,?,?,?,?,?)",
        [(p["plan_id"], p["plan_name"], p["monthly_premium"],
          p["individual_deductible"], p["specialist_copay"],
          p["emergency_room_copay"], p["pharmacy_tier_1_copay"]) for p in plans],
    )
    conn.commit()
    conn.close()
    print(f"✅ SQLite DB created: {DB_PATH}  ({len(plans)} plans)")


# ---------------------------------------------------------------------------
# 2. CSV – providers.csv (500 rows)
# ---------------------------------------------------------------------------
SPECIALTIES = [
    "PCP", "Cardiologist", "Dermatologist", "Orthopedic Surgeon",
    "Neurologist", "Pediatrician", "Psychiatrist", "Oncologist",
    "Endocrinologist", "Gastroenterologist", "Pulmonologist",
    "Rheumatologist", "Ophthalmologist", "Urologist", "ENT Specialist",
]

CITIES = [
    ("Austin", "TX", ["78701", "78702", "78703", "78704", "78745"]),
    ("Houston", "TX", ["77001", "77002", "77003", "77004", "77005"]),
    ("Dallas", "TX", ["75201", "75202", "75203", "75204", "75205"]),
    ("New York", "NY", ["10001", "10002", "10003", "10004", "10005"]),
    ("Brooklyn", "NY", ["11201", "11202", "11203", "11204", "11205"]),
    ("Los Angeles", "CA", ["90001", "90002", "90003", "90004", "90005"]),
    ("San Francisco", "CA", ["94102", "94103", "94104", "94105", "94107"]),
    ("Seattle", "WA", ["98101", "98102", "98103", "98104", "98105"]),
    ("Chicago", "IL", ["60601", "60602", "60603", "60604", "60605"]),
    ("Miami", "FL", ["33101", "33102", "33109", "33125", "33130"]),
    ("Denver", "CO", ["80201", "80202", "80203", "80204", "80205"]),
    ("Phoenix", "AZ", ["85001", "85002", "85003", "85004", "85005"]),
    ("Portland", "OR", ["97201", "97202", "97203", "97204", "97205"]),
    ("Atlanta", "GA", ["30301", "30302", "30303", "30304", "30305"]),
    ("Boston", "MA", ["02101", "02102", "02103", "02104", "02105"]),
]

FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael",
    "Linda", "David", "Elizabeth", "William", "Barbara", "Richard", "Susan",
    "Joseph", "Jessica", "Thomas", "Sarah", "Christopher", "Karen",
    "Charles", "Lisa", "Daniel", "Nancy", "Matthew", "Betty", "Anthony",
    "Margaret", "Mark", "Sandra", "Steven", "Ashley", "Andrew", "Dorothy",
    "Paul", "Kimberly", "Joshua", "Emily", "Kenneth", "Donna",
    "Raj", "Priya", "Wei", "Mei", "Carlos", "Maria", "Ahmed", "Fatima",
    "Hiroshi", "Yuki",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
    "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
    "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark",
    "Ramirez", "Lewis", "Robinson", "Walker", "Young", "Allen", "King",
    "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores",
    "Patel", "Chen", "Kim", "Singh", "Tanaka", "Müller", "Ivanov",
    "Okafor", "Johansson", "Ali",
]


def _generate_providers(n: int = 500) -> list[dict]:
    providers = []
    used_npis = set()
    for _ in range(n):
        npi = random.randint(1_000_000_000, 1_999_999_999)
        while npi in used_npis:
            npi = random.randint(1_000_000_000, 1_999_999_999)
        used_npis.add(npi)

        city, state, zips = random.choice(CITIES)
        providers.append({
            "provider_npi": npi,
            "doctor_name": f"Dr. {random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
            "specialty": random.choice(SPECIALTIES),
            "city": city,
            "state": state,
            "zip_code": random.choice(zips),
            "network_tier": random.choice(["Tier 1", "Tier 2"]),
            "is_accepting_new_patients": random.choice([True, False]),
        })
    return providers


def create_csv(providers: list[dict]) -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "provider_npi", "doctor_name", "specialty", "city", "state",
        "zip_code", "network_tier", "is_accepting_new_patients",
    ]
    with open(CSV_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(providers)
    print(f"✅ CSV created: {CSV_PATH}  ({len(providers)} providers)")


# ---------------------------------------------------------------------------
# 3. Text Knowledge Base – 3 Markdown files
# ---------------------------------------------------------------------------
EXCLUSIONS_MD = """\
# HealthGuard Insurance — Policy Exclusions & Limitations

## 1. General Exclusions

The following services, treatments, and supplies are **not covered** under any HealthGuard plan unless explicitly stated otherwise in the member's Summary of Benefits and Coverage (SBC):

### 1.1 Cosmetic & Elective Procedures
All cosmetic surgery and procedures performed primarily to improve appearance rather than to restore bodily function are excluded. This includes but is not limited to rhinoplasty for aesthetic purposes, blepharoplasty (eyelid surgery) without documented visual-field impairment, liposuction, abdominoplasty, and hair transplantation. Reconstructive surgery required as a result of accidental injury, mastectomy, or congenital deformity **is** covered when deemed medically necessary by the plan's Utilization Management (UM) committee.

### 1.2 Experimental & Investigational Treatments
HealthGuard does not cover treatments, drugs, or devices classified as experimental, investigational, or unproven by the U.S. Food and Drug Administration (FDA) or the plan's Clinical Review Board. This includes Phase I and Phase II clinical trial medications, gene therapy protocols not yet approved for general use, and off-label drug usage unless supported by peer-reviewed literature appearing in recognized compendia such as the American Hospital Formulary Service Drug Information (AHFS-DI).

### 1.3 Non-Emergency Services Obtained Out-of-Network
Services rendered by out-of-network providers are excluded unless the member has received prior authorization through the HealthGuard Exception Review Process or the services qualify as "Emergency Medical Conditions" under the prudent layperson standard (29 CFR § 2590.715-2719A). Balance billing protections under the No Surprises Act (Public Law 116-260) may apply for certain surprise medical bills.

### 1.4 Custodial & Long-Term Care
Custodial care, defined as assistance with activities of daily living (ADLs) such as bathing, dressing, eating, transferring, and toileting, is not a covered benefit. This exclusion applies to skilled nursing facility stays exceeding the plan's stated maximum of 60 days per benefit period, as well as residential care facilities and assisted living arrangements that do not meet the criteria for Skilled Nursing Facility (SNF) level of care.

## 2. Prescription Drug Exclusions

### 2.1 Non-Formulary Medications
Drugs not listed on the HealthGuard Preferred Drug List (PDL) are excluded from coverage. Members may request a Formulary Exception by submitting clinical documentation to the Pharmacy & Therapeutics (P&T) Committee. The P&T Committee meets quarterly to review and update the formulary based on clinical efficacy, safety profiles, and cost-effectiveness analyses.

### 2.2 Over-the-Counter (OTC) Medications
Over-the-counter medications, vitamins, minerals, herbal supplements, and homeopathic remedies are not covered under the pharmacy benefit. Select preventive OTC items (e.g., aspirin for cardiovascular prophylaxis, folic acid for women of childbearing age) may be covered at $0 cost-sharing when prescribed by a network provider as required under ACA Section 2713.

### 2.3 Fertility Medications & Treatments
Medications and procedures related to assisted reproductive technologies (ART), including in-vitro fertilization (IVF), gamete intrafallopian transfer (GIFT), and zygote intrafallopian transfer (ZIFT), are excluded. Diagnostic testing to evaluate infertility **is** covered as part of the standard medical benefit.

## 3. Behavioral Health Exclusions

### 3.1 Court-Ordered Services
Treatment or evaluations ordered by a court of law, including forensic psychiatric evaluations, competency assessments, and mandated anger management programs, are excluded unless the services also meet the plan's medical necessity criteria as determined by the Behavioral Health UM team.

### 3.2 Wilderness & Adventure Therapy
Outdoor behavioral health programs, wilderness therapy, and adventure-based counseling programs are not covered benefits, regardless of clinical recommendation.

## 4. Dental & Vision Exclusions
Routine dental care (preventive cleanings, fillings, extractions) and routine vision care (eye exams, corrective lenses, contact lens fittings) are excluded from the medical plan. These services may be available through supplemental HealthGuard Dental and HealthGuard Vision riders at additional premium cost. Dental services required to treat accidental injury to natural teeth within 72 hours of the accident **are** covered under the medical plan's emergency benefit.

## 5. Travel & International Services
Medical services obtained outside the United States, its territories, and possessions are not covered except in cases of medical emergencies as defined in Section 1.3. Members traveling internationally are advised to obtain supplemental travel medical insurance. Medically necessary repatriation and air ambulance services from international locations are excluded.

---
*This document is a summary and does not constitute the full plan contract. In the event of a conflict between this document and the Evidence of Coverage (EOC), the EOC governs. Last updated: January 2026.*
"""

RIGHTS_MD = """\
# HealthGuard Insurance — Member Rights & Responsibilities

## 1. Member Rights

As a valued HealthGuard Insurance member, you are entitled to the following rights under your plan and applicable federal and state regulations:

### 1.1 Right to Information
Members have the right to receive clear, accurate, and timely information about their health plan, including the Summary of Benefits and Coverage (SBC), Evidence of Coverage (EOC), provider directories, formulary drug lists, and any plan amendments. Information shall be provided in a culturally and linguistically appropriate manner as required by Section 1557 of the Affordable Care Act (42 U.S.C. § 18116).

### 1.2 Right to Choose a Provider
Members enrolled in HealthGuard PPO and POS plans have the right to select any licensed provider for covered services, subject to applicable in-network and out-of-network cost-sharing differentials. HMO members must select a Primary Care Physician (PCP) from the HealthGuard network and obtain referrals for specialty care as outlined in the plan's referral requirements.

### 1.3 Right to Emergency Care
Members have the right to receive emergency services at any hospital or emergency facility without prior authorization. Emergency services are covered at the in-network benefit level regardless of whether the facility is a participating provider, consistent with the prudent layperson standard and the No Surprises Act protections.

### 1.4 Right to Appeal & Grievance
Members have the right to file an appeal if a claim is denied or a service is determined to be not medically necessary. The appeals process includes:
- **Level 1 — Internal Appeal**: Reviewed by a physician reviewer who was not involved in the initial adverse determination. Decision rendered within 30 calendar days (72 hours for urgent/concurrent care).
- **Level 2 — External Review**: Conducted by an Independent Review Organization (IRO) certified by the state Department of Insurance. The IRO decision is binding on the plan.

Members may also file grievances regarding quality of care, access to services, or administrative issues through the Member Services department.

### 1.5 Right to Privacy & Confidentiality
All protected health information (PHI) is safeguarded in accordance with the Health Insurance Portability and Accountability Act (HIPAA) Privacy Rule (45 CFR Parts 160 and 164). Members have the right to request restrictions on the use and disclosure of their PHI, obtain an accounting of disclosures, request amendments to their medical records, and receive a copy of their designated record set.

### 1.6 Right to Continuity of Care
In the event that a member's provider is terminated from the HealthGuard network, the member has the right to continue an active course of treatment with that provider for a transitional period of up to 90 days, or through the postpartum period for members in their second or third trimester of pregnancy.

## 2. Member Responsibilities

### 2.1 Provide Accurate Information
Members are responsible for providing complete and accurate personal, medical, and insurance information to HealthGuard and their treating providers. This includes reporting changes in address, employment, dependent status, and other insurance coverage within 30 days of the qualifying life event.

### 2.2 Understand Your Benefits
Members are encouraged to review their SBC and EOC documents thoroughly to understand covered services, exclusions, limitations, and cost-sharing obligations (premiums, deductibles, copayments, coinsurance, and out-of-pocket maximums).

### 2.3 Obtain Required Authorizations
For services requiring prior authorization (PA), members and their providers must submit a PA request to HealthGuard's Utilization Management department **before** the service is rendered. Failure to obtain required authorization may result in denial of the claim. A list of services requiring PA is available on the HealthGuard member portal and is updated annually.

### 2.4 Pay Cost-Sharing Amounts Promptly
Members are responsible for paying applicable premiums, deductibles, copayments, and coinsurance in a timely manner. Failure to pay premiums may result in termination of coverage following the grace period specified in the plan contract (typically 31 days for non-subsidized plans).

### 2.5 Use Network Providers When Possible
To minimize out-of-pocket costs, members are encouraged to utilize in-network providers and facilities. Members may verify provider network participation status through the HealthGuard online provider directory or by contacting Member Services.

## 3. Non-Discrimination Statement

HealthGuard Insurance complies with applicable federal civil rights laws and does not discriminate on the basis of race, color, national origin, age, disability, sex, sexual orientation, gender identity, or religion. HealthGuard provides free language assistance services (interpreters, translated documents) and auxiliary aids and services (qualified sign language interpreters, written materials in alternative formats) to people with disabilities or limited English proficiency.

## 4. Contact Information

| Department | Phone | Hours |
|---|---|---|
| Member Services | 1-800-HG-MEMBER (1-800-446-3623) | Mon–Fri, 8 AM – 8 PM ET |
| Nurse Advice Line | 1-800-HG-NURSE (1-800-446-8773) | 24/7/365 |
| Behavioral Health | 1-800-HG-MENTAL (1-800-446-3682) | 24/7/365 |
| Pharmacy Help Desk | 1-800-HG-PHARMA (1-800-447-4276) | Mon–Sat, 8 AM – 10 PM ET |
| Appeals & Grievances | 1-800-HG-APPEAL (1-800-442-7732) | Mon–Fri, 8 AM – 6 PM ET |

---
*This document is provided for informational purposes and does not modify the terms of your Evidence of Coverage. In the event of a conflict, the EOC controls. Last updated: January 2026.*
"""

CLAIMS_MD = """\
# HealthGuard Insurance — Claims Filing & Processing Procedures

## 1. Overview

This document provides comprehensive guidance on filing, tracking, and resolving claims with HealthGuard Insurance. All claim submissions, adjudication timelines, and appeals processes comply with the Employee Retirement Income Security Act (ERISA), applicable state insurance regulations, and Centers for Medicare & Medicaid Services (CMS) guidelines.

## 2. How Claims Are Filed

### 2.1 In-Network Claims (Automatic Submission)
When members receive services from an in-network provider, the provider submits the claim directly to HealthGuard electronically using the ANSI X12 837 transaction set (Professional — 837P, Institutional — 837I). Members are **not** required to file claims for in-network services. The provider will collect any applicable copayment at the time of service; remaining cost-sharing amounts (deductible, coinsurance) will be billed to the member after claims adjudication.

### 2.2 Out-of-Network Claims (Member Submission)
For services received from out-of-network providers, the member may need to submit a claim for reimbursement. To file a claim:
1. **Obtain an itemized bill** from the provider that includes: date of service, CPT/HCPCS procedure codes, ICD-10-CM diagnosis codes, provider name and NPI, and total billed charges.
2. **Complete the HealthGuard Claim Form** (Form HG-1500), available on the member portal or by calling Member Services.
3. **Submit the claim** via one of the following methods:
   - **Online**: Upload through the HealthGuard member portal at portal.healthguard.com
   - **Mail**: HealthGuard Claims Department, P.O. Box 12345, Hartford, CT 06101
   - **Fax**: 1-860-555-0199

### 2.3 Timely Filing Requirements
All claims must be submitted within **180 calendar days** from the date of service. Claims submitted after the timely filing deadline will be denied unless the member can demonstrate good cause for the delay (e.g., the member was incapacitated, coordination of benefits with another payer was pending).

## 3. Claims Adjudication Process

### 3.1 Initial Review
Upon receipt, each claim undergoes the following automated and manual review steps:
1. **Eligibility Verification**: Confirm the member was enrolled and coverage was active on the date of service.
2. **Benefit Determination**: Map the procedure codes to the member's benefit plan to determine covered services, applicable cost-sharing, and any benefit limits.
3. **Medical Necessity Review**: For select services, clinical documentation is reviewed against HealthGuard's Clinical Coverage Guidelines and nationally recognized evidence-based criteria (e.g., InterQual, MCG Health).
4. **Coordination of Benefits (COB)**: If the member has coverage under another plan, HealthGuard applies the National Association of Insurance Commissioners (NAIC) COB rules to determine primary and secondary payer responsibility.
5. **Duplicate Claim Detection**: The system identifies potential duplicate submissions to prevent overpayment.

### 3.2 Adjudication Timelines
| Claim Type | Decision Timeline |
|---|---|
| Clean claims (complete and accurate) | 30 calendar days |
| Claims requiring additional information | 45 calendar days (after receipt of requested info) |
| Urgent/concurrent care claims | 72 hours |
| Pre-service authorization requests | 15 calendar days |

### 3.3 Explanation of Benefits (EOB)
After adjudication, members receive an Explanation of Benefits (EOB) statement that details:
- Date of service and provider name
- Billed charges vs. allowed amount
- Plan discount (contractual adjustment)
- Amount applied to deductible
- Copayment and coinsurance amounts
- Amount paid by HealthGuard
- Member responsibility (amount owed to provider)

The EOB is available electronically on the member portal and, upon request, by mail.

## 4. Common Claim Denial Reasons

### 4.1 Denial Codes & Descriptions
| Code | Reason | Suggested Action |
|---|---|---|
| D001 | Service not covered under plan | Review SBC; file an appeal if you believe the service should be covered |
| D002 | Prior authorization not obtained | Contact UM for retroactive authorization review |
| D003 | Timely filing limit exceeded | Submit proof of good cause for late filing |
| D004 | Duplicate claim submission | No action needed; original claim was processed |
| D005 | Member not eligible on date of service | Verify enrollment dates; contact Member Services |
| D006 | Non-covered provider type | Verify provider credentials and licensure |
| D007 | Benefit maximum reached | Review annual/lifetime benefit limits in EOC |
| D008 | Coordination of Benefits pending | Submit other insurance information via COB questionnaire |

## 5. Appeals Process

### 5.1 Level 1 — Internal Appeal
Members who disagree with a claim denial have the right to file an internal appeal within **180 calendar days** of receiving the adverse benefit determination (EOB with denial). The appeal should include:
- A written statement explaining why the member believes the denial was incorrect
- Any supporting clinical documentation, letters of medical necessity from the treating provider, or relevant medical records
- The claim number and member ID

Submit appeals to: HealthGuard Appeals Department, P.O. Box 67890, Hartford, CT 06102, or via the member portal.

**Decision timeline**: 30 calendar days for post-service claims; 72 hours for urgent care claims.

### 5.2 Level 2 — External Review
If the internal appeal is upheld (denied), members may request an external review by an Independent Review Organization (IRO) within **4 months** of the internal appeal decision. The external review is conducted at no cost to the member. The IRO reviewer is a board-certified physician in the relevant specialty who was not previously involved in the case.

**Decision timeline**: 45 calendar days for standard reviews; 72 hours for expedited reviews involving urgent care.

The IRO's decision is **binding** on HealthGuard.

## 6. Special Claim Scenarios

### 6.1 Surprise Billing Protections
Under the No Surprises Act, members are protected from balance billing for emergency services, air ambulance services from out-of-network providers, and non-emergency services from out-of-network providers at in-network facilities (e.g., an out-of-network anesthesiologist at an in-network hospital). Member cost-sharing for these services is calculated based on the in-network rate.

### 6.2 Subrogation & Third-Party Liability
If a member's medical expenses result from an accident caused by a third party (e.g., auto accident, workers' compensation), HealthGuard retains the right to subrogate and recover payments from the responsible party or their insurer, as permitted under the plan document and applicable law.

### 6.3 Retroactive Eligibility Changes
Claims affected by retroactive eligibility adjustments (e.g., COBRA election, qualifying life event) will be reprocessed automatically once the enrollment record is updated. Members do not need to resubmit claims.

## 7. Contact for Claims Assistance

| Need | Contact |
|---|---|
| Claim status inquiry | Member portal or 1-800-HG-CLAIM (1-800-442-5246) |
| Submit a claim form | portal.healthguard.com or mail to P.O. Box 12345 |
| File an appeal | portal.healthguard.com or mail to P.O. Box 67890 |
| Request an external review | 1-800-HG-APPEAL (1-800-442-7732) |
| Report fraud, waste, or abuse | 1-800-HG-FRAUD (1-800-443-7283), anonymous |

---
*This document is a procedural guide and does not modify the terms of your Evidence of Coverage. In the event of any conflict, the EOC governs. Claim forms and additional resources are available at portal.healthguard.com. Last updated: January 2026.*
"""


def create_text_docs() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    files = {
        "exclusions.md": EXCLUSIONS_MD,
        "rights.md": RIGHTS_MD,
        "claims.md": CLAIMS_MD,
    }
    for name, content in files.items():
        path = DOCS_DIR / name
        path.write_text(content)
        word_count = len(content.split())
        print(f"✅ Text doc created: {path}  (~{word_count} words)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    print("=" * 60)
    print("HealthGuard — Synthetic Data Generation")
    print("=" * 60)

    # Ensure logs dir exists
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # Generate all data
    random.seed(42)  # Reproducibility
    plans = _generate_plans(50)
    create_sqlite_db(plans)

    providers = _generate_providers(500)
    create_csv(providers)

    create_text_docs()

    print("=" * 60)
    print("✅ All synthetic data generated successfully!")
    print(f"   DB: {DB_PATH}")
    print(f"   CSV: {CSV_PATH}")
    print(f"   Docs: {DOCS_DIR}")
    print(f"   Logs dir: {LOGS_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
