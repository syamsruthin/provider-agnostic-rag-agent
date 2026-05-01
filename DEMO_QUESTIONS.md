# HealthGuard Demo Questions

## 🔵 SQL_TOOL — Plan & Cost Queries
1. Which plan has the lowest monthly premium?
2. Show me all Gold plans
3. Which plans have a deductible less than $2000?
4. What is the average specialist copay across all plans?
5. Compare the emergency room copay for Platinum plans

## 🟢 CSV_TOOL — Doctor & Provider Queries
6. Find me a Dermatologist in Austin, TX
7. How many Cardiologists are in New York?
8. List all doctors accepting new patients in Seattle, WA
9. Find a primary care physician in California
   > *Triggers rewrite: "primary care" → PCP, "California" → CA*
10. Show me Tier 1 Pediatricians in Chicago

## 🟡 RAG_TOOL — Policy & Document Queries
11. What are the policy exclusions for cosmetic surgery?
12. How do I file an out-of-network claim?
13. What are my rights as a member?
14. Is bariatric surgery covered under the plan?
15. What is the appeals process for a denied claim?

## 🟣 MULTI_TOOL — Cross-Source Complex Queries ⭐
16. I need a Dermatologist in Austin, TX under a plan with a deductible less than $1000
    > *The showstopper — triggers SQL_TOOL + CSV_TOOL simultaneously*
17. Find me a heart doctor in Texas with a plan that has low copays
    > *Triggers rewrite: "heart doctor" → Cardiologist, "Texas" → TX*
18. I want a Pediatrician in Florida and need to know about claim filing procedures
    > *CSV_TOOL + RAG_TOOL*

## 🔄 Conversation Memory Demo
Ask these **in sequence** to show memory persistence:
19. What Silver plans are available?
20. Which of those has the lowest deductible?
    > *Uses conversation history to understand "those" = Silver plans*

## ⚡ Query Rewriter Showcase
These highlight the de-aliasing in the trace sidebar:
- Find me a skin doctor in Washington → *"Dermatologist in WA"*
- I need a bone doctor in Massachusetts → *"Orthopedic Surgeon in MA"*
- Eye doctor in New Jersey → *"Ophthalmologist in NJ"*

---

## Suggested Demo Flow
1. Start with **#1** (SQL) — simple, fast, impressive
2. Then **#6** (CSV) — shows doctor search
3. Then **#11** (RAG) — shows policy knowledge
4. Hit **#16** (MULTI) — the showstopper, point to trace sidebar
5. Show **#9** (rewrite) — point out "primary care → PCP" in trace
6. Finish with **#19 → #20** (memory) — shows conversation continuity
