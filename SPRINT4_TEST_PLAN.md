# Sprint 4: End-to-End Test Plan

## Overview
This document provides a comprehensive test plan for verifying the complete temporal RAG workflow from file staging through temporal querying.

## Prerequisites

### Backend Setup
```bash
cd /Users/parthpatel/Projects/LightRAG

# Ensure dependencies are installed
pip install -e .

# Set environment variables
export LIGHTRAG_LLM_MODEL=gpt-4o
export LIGHTRAG_EMBEDDING_MODEL=text-embedding-3-large
# ... other required environment variables

# Start the backend server
uvicorn lightrag.api.lightrag_server:app --reload --port 8080
```

### Frontend Setup
```bash
cd lightrag_webui

# Install dependencies
bun install

# Start development server
bun run dev
```

### Test Data Files

Create two test contract files in `test_temporal_ingest/`:

**File 1: `Base_Contract.md`**
```markdown
# Commercial Lease Agreement

**Effective Date:** 2023-01-01

## Service Fee
The monthly service fee is **$1,000** per month.

## Parking Fee
The parking fee is **$100** per space. The tenant is allocated **50 parking spaces**.
Total parking cost: $5,000 per month.

## Office Cleaning
Office cleaning service is provided **twice per week** on Mondays and Thursdays.
```

**File 2: `Amendment_1.md`**
```markdown
# Amendment to Commercial Lease Agreement

**Effective Date:** 2024-01-01

## Amendments

### Service Fee Change
The monthly service fee is hereby amended to **$1,500** per month (increased from $1,000).

### Parking Allocation Change
The tenant's parking allocation is increased to **75 spaces** at **$120** per space.
Total parking cost: $9,000 per month.

### Office Cleaning Enhancement
Office cleaning service is enhanced to **daily service** (Monday through Friday).
```

---

## Test Scenarios

### Test 1: Backend Upload Endpoint with Metadata

**Objective:** Verify backend API accepts and processes metadata correctly.

**Steps:**
1. Use curl or Postman to upload Base_Contract.md:
```bash
curl -X POST "http://localhost:8080/documents/upload" \
  -F "file=@test_temporal_ingest/Base_Contract.md" \
  -F "sequence_index=1" \
  -F "effective_date=2023-01-01" \
  -F "doc_type=base"
```

2. Upload Amendment_1.md:
```bash
curl -X POST "http://localhost:8080/documents/upload" \
  -F "file=@test_temporal_ingest/Amendment_1.md" \
  -F "sequence_index=2" \
  -F "effective_date=2024-01-01" \
  -F "doc_type=amendment"
```

**Expected Results:**
- Both uploads return `status: "success"`
- Each returns a `track_id` for background processing
- Files appear in document list with status "processing" → "completed"

**Validation:**
```bash
# Check document status
curl "http://localhost:8080/documents/statuses?page=1&page_size=10"
```

---

### Test 2: Staging Area UI Workflow

**Objective:** Verify frontend staging area allows file sequencing and metadata input.

**Steps:**
1. Open browser to `http://localhost:5173` (or Vite dev server URL)
2. Navigate to "Documents" tab
3. Click "Staging Area" button (should be next to "Upload Documents")
4. In the staging dialog:
   - Click "Select Files"
   - Choose both `Base_Contract.md` and `Amendment_1.md`
   - Files should appear in the staging list

5. Verify sequence indicators:
   - First file shows "Oldest (v1)" badge
   - Last file shows "Newest (v2)" badge

6. Test Move Up/Down:
   - If Amendment_1 is first, click "Move Down"
   - If Base_Contract is second, click "Move Up"
   - Verify order changes and badges update

7. Set effective dates:
   - Base_Contract: `2023-01-01`
   - Amendment_1: `2024-01-01`

8. Select document types:
   - Base_Contract: "base"
   - Amendment_1: "amendment"

9. Click "Upload All"
10. Verify progress bars appear
11. Verify success notification
12. Verify document list refreshes

**Expected Results:**
- All UI controls work smoothly
- Files upload with correct sequence metadata
- Progress indicators show upload status
- Document list updates after upload completes

---

### Test 3: Temporal Query UI

**Objective:** Verify temporal mode selector and date picker work correctly.

**Steps:**
1. Navigate to "Query" or "Retrieval Testing" tab
2. Locate mode dropdown
3. Verify "Temporal" option is available
4. Select "Temporal" mode
5. Verify date picker appears below mode selector
6. Verify date picker defaults to today's date
7. Change date to `2023-06-01` (before Amendment_1)
8. Enter query: "What is the monthly service fee?"
9. Submit query
10. Note response content
11. Change date to `2024-06-01` (after Amendment_1)
12. Re-run same query
13. Note response content

**Expected Results:**
- Date picker only visible when mode = "Temporal"
- Date picker allows manual input and calendar selection
- Query 1 (2023-06-01) should mention:
  - Service fee: $1,000/month (v1 data)
  - May reference "Base [v1]" or similar version indicator
- Query 2 (2024-06-01) should mention:
  - Service fee: $1,500/month (v2 data)
  - May reference "Amendment [v2]" or similar version indicator

---

### Test 4: Version Filtering Accuracy

**Objective:** Verify temporal filtering returns chronologically correct versions.

**Test Cases:**

#### 4.1: Query Before Any Documents
- Date: `2022-12-31` (before Base effective date)
- Query: "What is the parking fee?"
- Expected: Response indicates no information found OR only general knowledge

#### 4.2: Query During Base Period
- Date: `2023-06-01`
- Query: "What is the parking fee?"
- Expected: 50 spaces × $100 = $5,000/month (v1 data)

#### 4.3: Boundary Condition - Exact Amendment Date
- Date: `2024-01-01` (exact Amendment effective date)
- Query: "What is the parking fee?"
- Expected: 75 spaces × $120 = $9,000/month (v2 data)
- Reason: `effective_date <= reference_date` includes the boundary

#### 4.4: Query After Amendment
- Date: `2025-01-01`
- Query: "What is the office cleaning schedule?"
- Expected: Daily service (v2 data), not twice per week (v1)

#### 4.5: Comparison Query
- Date: `2025-01-01`
- Query: "How did the service fee change over time?"
- Expected: Response should reference both $1,000 (original) and $1,500 (current)

**Validation Method:**
For each test case:
1. Set reference date in UI
2. Submit query
3. Read response carefully
4. Verify numbers/details match expected version
5. Check for version indicators like "[v1]" or "[v2]" in context

---

### Test 5: Regular Upload Still Works

**Objective:** Ensure backward compatibility - regular upload without metadata still functions.

**Steps:**
1. Click "Upload Documents" (NOT "Staging Area")
2. Select a test file (e.g., another markdown file)
3. Upload normally
4. Verify upload succeeds
5. Query for content from that file
6. Verify retrieval works

**Expected Results:**
- Upload succeeds without metadata fields
- Document processes normally
- No versioning applied (sequence_index defaults to 0)
- Queries work in all modes including temporal
- No errors or breaking changes

---

### Test 6: Non-Temporal Modes Still Work

**Objective:** Verify other query modes unaffected by temporal additions.

**Steps:**
1. Upload test documents via staging area (with metadata)
2. Switch to each mode and test:
   - Mode: "Local" - Query: "service fee"
   - Mode: "Global" - Query: "what are the lease terms?"
   - Mode: "Hybrid" - Query: "parking allocation"
   - Mode: "Naive" - Query: "cleaning service"

**Expected Results:**
- All modes return responses
- No errors or unusual behavior
- Temporal filtering NOT applied (reference_date ignored)
- Results may include information from multiple versions

---

### Test 7: Stream Response with Temporal Mode

**Objective:** Verify streaming works with temporal mode.

**Steps:**
1. Enable "Stream Response" toggle in query settings
2. Select mode: "Temporal"
3. Set reference date: `2024-06-01`
4. Submit query: "Summarize the lease agreement"
5. Observe streaming behavior

**Expected Results:**
- Response streams token by token
- Content reflects correct temporal version (v2)
- No errors during streaming
- Thinking process displays if available

---

### Test 8: Error Handling

**Objective:** Verify graceful error handling for edge cases.

#### 8.1: Invalid Date Format
- Set reference_date to invalid format (e.g., "2024-13-45")
- Submit query
- Expected: Error message or validation warning

#### 8.2: Future Date
- Set reference_date far in future (e.g., "2099-12-31")
- Submit query
- Expected: Returns latest version (v2)

#### 8.3: Empty Staging Area Upload
- Open staging area
- Click "Upload All" without adding files
- Expected: Warning or disabled button

#### 8.4: Missing Metadata Fields
- Upload via API with partial metadata (only sequence_index, no effective_date)
- Expected: Uses default values, no crash

---

## Integration Test: Complete Workflow

### Full End-to-End Scenario

**Story:** User needs to track contract evolution and query historical states.

**Steps:**

1. **Preparation**
   - Clear existing documents: `/documents` DELETE endpoint
   - Prepare test files: Base and Amendment

2. **Document Upload**
   - Open staging area
   - Add Base_Contract.md and Amendment_1.md
   - Ensure Base is first (v1), Amendment is second (v2)
   - Set dates: 2023-01-01 and 2024-01-01
   - Set types: base and amendment
   - Upload all

3. **Verify Processing**
   - Wait for status to change to "completed" (may take 30-60 seconds)
   - Check document list shows both files

4. **Historical Query (v1)**
   - Switch to Query tab
   - Mode: Temporal
   - Date: 2023-06-01
   - Query: "What are the monthly costs for service fee and parking?"
   - Expected answer: Service $1,000 + Parking $5,000 = $6,000 total

5. **Current Query (v2)**
   - Keep mode: Temporal
   - Change date: 2024-06-01
   - Same query: "What are the monthly costs for service fee and parking?"
   - Expected answer: Service $1,500 + Parking $9,000 = $10,500 total

6. **Evolution Tracking**
   - Keep date: 2024-06-01
   - Query: "How have the monthly costs changed?"
   - Expected: Should reference increase from $6,000 to $10,500

7. **Non-Temporal Comparison**
   - Switch mode: Hybrid (not temporal)
   - Query: "What are all the parking fee rates mentioned?"
   - Expected: May mention both $100/space and $120/space

**Success Criteria:**
- All queries return appropriate responses
- Temporal mode shows version-specific data
- Non-temporal mode may show combined data
- No errors or crashes
- Version indicators visible in responses

---

## Performance Tests

### Test 9: Large Document Set

**Objective:** Verify performance with multiple versioned documents.

**Steps:**
1. Create 10 versions of a contract (v1 through v10)
2. Upload all via staging area with sequential dates
3. Query with temporal mode at various reference dates
4. Measure response times

**Expected Results:**
- Upload completes successfully
- Queries return in reasonable time (<5 seconds)
- Correct versions returned for each date
- No memory leaks or slowdowns

---

## Automated Test Script (Optional)

For repeatable testing, consider this Python script:

```python
import requests
import time

BASE_URL = "http://localhost:8080"

def test_temporal_upload_and_query():
    # Upload Base Contract
    with open("test_temporal_ingest/Base_Contract.md", "rb") as f:
        response = requests.post(
            f"{BASE_URL}/documents/upload",
            files={"file": f},
            data={
                "sequence_index": 1,
                "effective_date": "2023-01-01",
                "doc_type": "base"
            }
        )
        assert response.status_code == 200
        print(f"Base upload: {response.json()}")
    
    # Upload Amendment
    with open("test_temporal_ingest/Amendment_1.md", "rb") as f:
        response = requests.post(
            f"{BASE_URL}/documents/upload",
            files={"file": f},
            data={
                "sequence_index": 2,
                "effective_date": "2024-01-01",
                "doc_type": "amendment"
            }
        )
        assert response.status_code == 200
        print(f"Amendment upload: {response.json()}")
    
    # Wait for processing
    print("Waiting for document processing...")
    time.sleep(30)
    
    # Query v1 (2023-06-01)
    response = requests.post(
        f"{BASE_URL}/query",
        json={
            "query": "What is the monthly service fee?",
            "mode": "temporal",
            "reference_date": "2023-06-01"
        }
    )
    assert response.status_code == 200
    v1_response = response.json()["response"]
    print(f"\nv1 Response: {v1_response}")
    assert "$1,000" in v1_response or "1000" in v1_response
    
    # Query v2 (2024-06-01)
    response = requests.post(
        f"{BASE_URL}/query",
        json={
            "query": "What is the monthly service fee?",
            "mode": "temporal",
            "reference_date": "2024-06-01"
        }
    )
    assert response.status_code == 200
    v2_response = response.json()["response"]
    print(f"\nv2 Response: {v2_response}")
    assert "$1,500" in v2_response or "1500" in v2_response
    
    print("\n✅ All tests passed!")

if __name__ == "__main__":
    test_temporal_upload_and_query()
```

Run with: `python test_sprint4_integration.py`

---

## Checklist

Before marking Sprint 4 complete, verify:

- [ ] Backend `/upload` endpoint accepts metadata (curl test)
- [ ] Staging area dialog opens and closes
- [ ] File selection works
- [ ] Move Up/Down buttons reorder files
- [ ] Version badges update correctly
- [ ] Effective date inputs work
- [ ] Document type selectors work
- [ ] Upload progress shows
- [ ] Temporal mode appears in dropdown
- [ ] Date picker appears conditionally
- [ ] Temporal queries with past date return v1 data
- [ ] Temporal queries with current date return v2 data
- [ ] Non-temporal modes still work
- [ ] Regular upload (without staging) still works
- [ ] No console errors in browser
- [ ] No Python errors in backend logs
- [ ] Documentation updated (PROGRESS.md)
- [ ] Test files created and validated

---

## Known Issues & Limitations

Document any issues found during testing:

1. **Issue:** [Description]
   - **Impact:** [User-facing impact]
   - **Workaround:** [Temporary solution]
   - **Status:** [Open/Fixed/Deferred]

2. **Limitation:** Version information in responses depends on LLM output
   - **Impact:** Version tags like "[v1]" may not always appear in response text
   - **Mitigation:** Temporal filtering ensures correct context is provided to LLM
   - **Status:** Acceptable - working as designed

---

## Success Criteria Summary

Sprint 4 is considered complete when:

1. ✅ All backend endpoints accept and process metadata
2. ✅ Staging area UI is functional and user-friendly
3. ✅ Temporal query mode returns chronologically accurate results
4. ✅ All existing functionality remains intact (no regressions)
5. ✅ Documentation is complete and accurate
6. ✅ At least one full end-to-end test passes successfully

---

**Test Execution Date:** _________________  
**Tester:** _________________  
**Results:** _________________  
**Issues Found:** _________________  
**Overall Status:** ☐ PASS  ☐ FAIL  ☐ PARTIAL

