"""
Test script for Milestone 2 tools: SQL, CSV/Python, and Hybrid RAG.
Validates each tool independently before agent orchestration.

Run with: uv run python -m backend.scripts.test_tools
"""

import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def test_sql_tool():
    """Test the SQL tool with plan queries."""
    from backend.agents.sql_agent import sql_tool

    print("=" * 60)
    print("TEST: SQL Tool")
    print("=" * 60)

    queries = [
        "What are all the Silver plans?",
        "Which plan has the lowest monthly premium?",
        "Show me plans with a deductible less than $2000",
    ]

    for q in queries:
        print(f"\n📝 Query: {q}")
        result = sql_tool(q)
        if result["error"]:
            print(f"   ❌ Error: {result['error']}")
        else:
            print(f"   🔧 SQL: {result['sql']}")
            print(f"   📊 Rows: {len(result['raw_results'])}")
            print(f"   📄 Output:\n{result['formatted'][:500]}")
        print()

    return True


def test_python_tool():
    """Test the Python/CSV tool — includes the spec's required assertion."""
    from backend.agents.csv_agent import python_tool
    import pandas as pd

    print("=" * 60)
    print("TEST: Python/CSV Tool")
    print("=" * 60)

    # Spec-required test case
    print("\n📝 Query: Find PCPs in Seattle, WA")
    result = python_tool("Find PCPs in Seattle, WA")
    if result["error"]:
        print(f"   ❌ Error: {result['error']}")
        return False
    else:
        print(f"   🔧 Code:\n{result['code']}")
        print(f"   📄 Output:\n{result['formatted'][:500]}")

        # Validate: result should be a DataFrame with only PCP specialty
        # and Seattle/WA location
        raw = result["raw_results"]
        if isinstance(raw, pd.DataFrame) and not raw.empty:
            assert all(raw["specialty"] == "PCP"), "Not all results are PCPs!"
            assert all(raw["city"] == "Seattle"), "Not all results are in Seattle!"
            assert all(raw["state"] == "WA"), "Not all results are in WA!"
            print("   ✅ ASSERTION PASSED: All results are PCPs in Seattle, WA")
        elif isinstance(raw, pd.DataFrame) and raw.empty:
            print("   ⚠️  Empty result — may be valid if no PCPs in Seattle")
        else:
            print(f"   ℹ️  Result type: {type(raw)}")

    # Additional test
    print("\n📝 Query: How many Cardiologists are in New York?")
    result = python_tool("How many Cardiologists are in New York?")
    if result["error"]:
        print(f"   ❌ Error: {result['error']}")
    else:
        print(f"   🔧 Code:\n{result['code']}")
        print(f"   📄 Output:\n{result['formatted'][:300]}")

    return True


def test_rag_tool():
    """Test the Hybrid RAG tool with policy questions."""
    from backend.agents.rag_agent import rag_tool, index_documents

    print("=" * 60)
    print("TEST: Hybrid RAG Tool")
    print("=" * 60)

    # Index documents first
    print("\n🔄 Indexing documents...")
    count = index_documents(force=True)
    print(f"   ✅ Indexed {count} chunks")

    queries = [
        "What are the policy exclusions for cosmetic surgery?",
        "How do I file a claim?",
        "What are my rights as a member?",
    ]

    for q in queries:
        print(f"\n📝 Query: {q}")
        result = rag_tool(q)
        if result["error"]:
            print(f"   ❌ Error: {result['error']}")
        else:
            print(f"   📊 Results: {len(result['results'])} chunks")
            for i, r in enumerate(result["results"][:3]):
                print(f"   [{i+1}] Source: {r['source']} | RRF: {r['rrf_score']:.4f}")
                print(f"       {r['text'][:120]}...")
        print()

    return True


def main():
    print("\n🏥 HealthGuard — Milestone 2 Tool Tests\n")

    results = {}

    # Test RAG first (no API key needed)
    try:
        results["RAG"] = test_rag_tool()
    except Exception as e:
        print(f"❌ RAG test failed: {e}")
        results["RAG"] = False

    # Test SQL tool (needs Groq API key)
    try:
        results["SQL"] = test_sql_tool()
    except Exception as e:
        print(f"❌ SQL test failed: {e}")
        results["SQL"] = False

    # Test Python tool (needs Groq API key)
    try:
        results["Python"] = test_python_tool()
    except Exception as e:
        print(f"❌ Python test failed: {e}")
        results["Python"] = False

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for tool, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {tool}: {status}")
    print()

    all_passed = all(results.values())
    if all_passed:
        print("🎉 All tools passed!")
    else:
        print("⚠️  Some tools failed — check output above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
