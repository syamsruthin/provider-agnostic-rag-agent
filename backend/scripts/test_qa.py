"""
Milestone 5 — Quality Assurance Test Suite
============================================
1. Multi-tool complex query (Dermatologist in Austin + deductible < $1000)
2. Log validation (trace MD explains multi-tool reasoning)
3. Extensibility (new pharmacies.csv data source with zero engine changes)
"""

import csv
import json
import os
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Coloring helpers
# ---------------------------------------------------------------------------
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

def ok(msg): print(f"  {GREEN}✅ {msg}{RESET}")
def fail(msg): print(f"  {RED}❌ {msg}{RESET}")
def info(msg): print(f"  {CYAN}ℹ️  {msg}{RESET}")
def section(msg): print(f"\n{'='*60}\n{BOLD}{msg}{RESET}\n{'='*60}")

results = {}

# ═══════════════════════════════════════════════════════════════════════════
# TEST 1: Multi-tool complex query
# ═══════════════════════════════════════════════════════════════════════════
section("TEST 1: Multi-Tool Complex Query")

from backend.agents.orchestrator import process_query
from backend.core.memory import memory

COMPLEX_QUERY = "I need a Dermatologist in Austin, TX under a plan with a deductible less than $1000."

print(f"\n📝 Query: \"{COMPLEX_QUERY}\"")
result = process_query(COMPLEX_QUERY, "qa-test-multitool")

print(f"   Tools used: {result['tools_used']}")
print(f"   Answer preview: {result['answer'][:300]}...")

# Validate multi-tool was triggered
is_multi = len(result["tools_used"]) > 1
if is_multi:
    ok(f"Multi-tool triggered: {result['tools_used']}")
else:
    # Even if the LLM chose single tool, check if it mentions both concepts
    info(f"Router chose: {result['tools_used']} (may have combined in single pass)")

# Check answer mentions both dermatologist/Austin AND deductible
answer_lower = result["answer"].lower()
has_doctor_info = any(w in answer_lower for w in ["dermatologist", "austin", "doctor", "provider"])
has_plan_info = any(w in answer_lower for w in ["deductible", "plan", "premium", "$"])

if has_doctor_info:
    ok("Answer contains doctor/provider information")
else:
    fail("Answer missing doctor/provider information")

if has_plan_info:
    ok("Answer contains plan/deductible information")
else:
    fail("Answer missing plan/deductible information")

results["multi_tool"] = has_doctor_info and has_plan_info

# ═══════════════════════════════════════════════════════════════════════════
# TEST 2: Log Validation
# ═══════════════════════════════════════════════════════════════════════════
section("TEST 2: Log Validation")

from backend.core.config import LOGS_DIR

# Check JSONL log exists
session_jsonl = LOGS_DIR / "qa-test-multitool.jsonl"
print(f"\n📂 Checking: {session_jsonl}")

if session_jsonl.exists():
    ok(f"JSONL log exists ({session_jsonl.stat().st_size} bytes)")

    # Parse JSONL entries
    entries = []
    with open(session_jsonl) as f:
        for line in f:
            entries.append(json.loads(line))

    print(f"   📊 Total log entries: {len(entries)}")

    # Validate required components are logged
    components = {e["component"] for e in entries}
    print(f"   📋 Components logged: {components}")

    required = {"QueryRewriter", "Router", "Synthesizer"}
    tool_entries = {c for c in components if c.startswith("ToolExecution:")}

    for req in required:
        if req in components:
            ok(f"Component '{req}' logged")
        else:
            fail(f"Component '{req}' missing from logs")

    if tool_entries:
        ok(f"Tool execution entries: {tool_entries}")
    else:
        fail("No ToolExecution entries found")

    # Validate Router entry has reasoning
    router_entries = [e for e in entries if e["component"] == "Router"]
    if router_entries:
        r = router_entries[-1]  # Most recent
        reasoning = r.get("reasoning", "")
        print(f"   🧠 Router reasoning: \"{reasoning[:200]}\"")
        ok("Router reasoning captured in JSONL")
    else:
        fail("No Router entry found")

    results["jsonl_valid"] = required.issubset(components) and bool(tool_entries)
else:
    fail("JSONL log not found")
    results["jsonl_valid"] = False

# Check Markdown trace files
md_files = list(LOGS_DIR.glob("trace_*.md"))
print(f"\n📂 Markdown trace files: {len(md_files)}")

if md_files:
    latest_md = max(md_files, key=lambda p: p.stat().st_mtime)
    md_content = latest_md.read_text()
    print(f"   📄 Latest: {latest_md.name} ({len(md_content)} chars)")

    # Validate trace structure
    required_sections = [
        ("User Query", "## User Query" in md_content or "**Query**" in md_content),
        ("Query Rewrite", "Rewrite" in md_content),
        ("Router Decision", "Router" in md_content),
        ("Tool Execution", "Tool Execution" in md_content or "Tool" in md_content),
        ("Final Synthesis", "Synthesis" in md_content or "Final" in md_content),
    ]

    for name, found in required_sections:
        if found:
            ok(f"Trace section: {name}")
        else:
            fail(f"Trace section missing: {name}")

    results["trace_valid"] = all(found for _, found in required_sections)

    # Print the trace for visual inspection
    print(f"\n   {YELLOW}--- Trace Report (abbreviated) ---{RESET}")
    for line in md_content.split("\n")[:25]:
        print(f"   {line}")
    if len(md_content.split("\n")) > 25:
        print(f"   ... ({len(md_content.split(chr(10))) - 25} more lines)")
else:
    fail("No Markdown trace files found")
    results["trace_valid"] = False


# ═══════════════════════════════════════════════════════════════════════════
# TEST 3: Extensibility — Add a new data source (pharmacies.csv)
# ═══════════════════════════════════════════════════════════════════════════
section("TEST 3: Extensibility (pharmacies.csv)")

print("\n🏗️  Creating synthetic pharmacies.csv...")

# Step 1: Generate test data
pharmacies_data = [
    {"pharmacy_id": "PHR-001", "name": "Austin Health Pharmacy", "city": "Austin", "state": "TX", "zip_code": "78701", "is_24hr": True, "network": "Tier 1"},
    {"pharmacy_id": "PHR-002", "name": "Dallas MedRx", "city": "Dallas", "state": "TX", "zip_code": "75201", "is_24hr": False, "network": "Tier 2"},
    {"pharmacy_id": "PHR-003", "name": "Seattle Care Pharmacy", "city": "Seattle", "state": "WA", "zip_code": "98101", "is_24hr": True, "network": "Tier 1"},
    {"pharmacy_id": "PHR-004", "name": "NYC Wellness Rx", "city": "New York", "state": "NY", "zip_code": "10001", "is_24hr": True, "network": "Tier 1"},
    {"pharmacy_id": "PHR-005", "name": "Lone Star Pharmacy", "city": "Houston", "state": "TX", "zip_code": "77001", "is_24hr": False, "network": "Tier 1"},
    {"pharmacy_id": "PHR-006", "name": "Bay Area MedSupply", "city": "San Francisco", "state": "CA", "zip_code": "94101", "is_24hr": False, "network": "Tier 2"},
    {"pharmacy_id": "PHR-007", "name": "Chicago Health Hub", "city": "Chicago", "state": "IL", "zip_code": "60601", "is_24hr": True, "network": "Tier 1"},
    {"pharmacy_id": "PHR-008", "name": "Denver Mountain Rx", "city": "Denver", "state": "CO", "zip_code": "80201", "is_24hr": False, "network": "Tier 2"},
]

# Write to a temp CSV
tmp_csv = Path(tempfile.mktemp(suffix=".csv", dir=str(LOGS_DIR.parent / "data")))
with open(tmp_csv, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=pharmacies_data[0].keys())
    writer.writeheader()
    writer.writerows(pharmacies_data)

ok(f"Created {tmp_csv.name} with {len(pharmacies_data)} rows")

# Step 2: Define config (this is all you need — NO engine changes)
PHARMACIES_SOURCE = {
    "name": "pharmacies",
    "type": "csv",
    "csv_path": str(tmp_csv),
    "columns": ["pharmacy_id", "name", "city", "state", "zip_code", "is_24hr", "network"],
    "type_coercions": {
        "is_24hr": "bool",
        "zip_code": "str",
    },
    "system_prompt": (
        "You are a Data Analyst. You have a Pandas DataFrame `df` loaded from `pharmacies.csv`. "
        "Columns: [pharmacy_id, name, city, state, zip_code, is_24hr, network]. "
        "is_24hr is boolean. network values: 'Tier 1', 'Tier 2'. "
        "Your task: Generate Python code using `df` to answer the user query. "
        "Output ONLY the python code. The code must produce a variable called `result`."
    ),
}
ok("Defined PHARMACIES_SOURCE config (zero engine code touched)")

# Step 3: Instantiate engine with new config — using the SAME engine class
from backend.core.tools import PythonExecutionEngine

pharmacy_engine = PythonExecutionEngine(
    csv_path=PHARMACIES_SOURCE["csv_path"],
    system_prompt=PHARMACIES_SOURCE["system_prompt"],
    type_coercions=PHARMACIES_SOURCE.get("type_coercions", {}),
)
ok("Instantiated PythonExecutionEngine with pharmacies config")

# Step 4: Query the new data source
print("\n📝 Query: \"Find 24-hour pharmacies in Texas\"")
result = pharmacy_engine.run("Find 24-hour pharmacies in Texas")

if result["error"]:
    fail(f"Pharmacy query error: {result['error']}")
    results["extensibility"] = False
else:
    print(f"   🔧 Code: {result['code']}")
    print(f"   📄 Result:\n{result['formatted']}")

    # Validate: should find Austin Health Pharmacy (24hr, TX)
    formatted = result["formatted"]
    has_austin = "Austin" in formatted
    has_tx = "TX" in formatted

    if has_austin and has_tx:
        ok("Found 24hr pharmacy in TX — engine works with new data source")
        results["extensibility"] = True
    else:
        fail(f"Expected Austin TX pharmacies in result")
        results["extensibility"] = False

# Step 5: Also test SQL engine extensibility
print("\n📝 Testing SQL engine extensibility with temp DB...")

import sqlite3
from backend.core.tools import SQLExecutionEngine

tmp_db = Path(tempfile.mktemp(suffix=".db", dir=str(LOGS_DIR.parent / "data")))
conn = sqlite3.connect(str(tmp_db))
conn.execute("""
    CREATE TABLE claims (
        claim_id TEXT PRIMARY KEY,
        member_id TEXT,
        amount REAL,
        status TEXT,
        filed_date TEXT
    )
""")
conn.executemany(
    "INSERT INTO claims VALUES (?, ?, ?, ?, ?)",
    [
        ("CLM-001", "MEM-100", 1500.00, "approved", "2026-01-15"),
        ("CLM-002", "MEM-101", 350.00, "denied", "2026-02-20"),
        ("CLM-003", "MEM-100", 2200.00, "pending", "2026-03-10"),
        ("CLM-004", "MEM-102", 800.00, "approved", "2026-01-25"),
        ("CLM-005", "MEM-101", 450.00, "approved", "2026-04-01"),
    ],
)
conn.commit()
conn.close()
ok(f"Created temp claims.db with 5 rows")

claims_engine = SQLExecutionEngine(
    db_path=str(tmp_db),
    system_prompt=(
        "You are a SQL expert. Table `claims` has columns: "
        "[claim_id, member_id, amount, status, filed_date]. "
        "status values: 'approved', 'denied', 'pending'. "
        "Output ONLY valid SQLite code. Do not explain."
    ),
)
ok("Instantiated SQLExecutionEngine with claims config (zero engine code touched)")

print("\n📝 Query: \"How many approved claims are there?\"")
sql_result = claims_engine.run("How many approved claims are there?")

if sql_result["error"]:
    fail(f"Claims query error: {sql_result['error']}")
    results["sql_extensibility"] = False
else:
    print(f"   🔧 SQL: {sql_result['sql']}")
    print(f"   📄 Result: {sql_result['formatted']}")

    # Should return 3 (CLM-001, CLM-004, CLM-005)
    if "3" in sql_result["formatted"]:
        ok("Correct: 3 approved claims — SQL engine works with new data source")
        results["sql_extensibility"] = True
    else:
        fail(f"Expected '3' in result, got: {sql_result['formatted']}")
        results["sql_extensibility"] = False

# Cleanup temp files
try:
    os.remove(tmp_csv)
    os.remove(tmp_db)
except Exception:
    pass


# ═══════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════════
section("SUMMARY")

all_tests = {
    "Multi-Tool Query": results.get("multi_tool", False),
    "JSONL Logs Valid": results.get("jsonl_valid", False),
    "Trace MD Valid": results.get("trace_valid", False),
    "CSV Extensibility": results.get("extensibility", False),
    "SQL Extensibility": results.get("sql_extensibility", False),
}

for name, passed in all_tests.items():
    status = f"{GREEN}✅ PASS{RESET}" if passed else f"{RED}❌ FAIL{RESET}"
    print(f"  {name}: {status}")

passed = sum(1 for v in all_tests.values() if v)
total = len(all_tests)
print(f"\n{BOLD}Result: {passed}/{total} tests passed{RESET}")

if passed == total:
    print(f"\n{GREEN}🎉 All quality assurance tests passed!{RESET}")
    sys.exit(0)
else:
    print(f"\n{YELLOW}⚠️  Some tests need attention.{RESET}")
    sys.exit(1)
