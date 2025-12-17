# Architecture & State Management Summary
**Date:** December 17, 2025
**Topic:** Async Job Queue, State Persistence, and Process Flow

This document summarizes the changes made to move long-running tasks to an asynchronous architecture and ensure UI state persistence across session interruptions.

---

## 1. High-Level Architecture Change
We migrated from synchronous HTTP endpoints (which timed out or blocked generation) to an **Asynchronous Job Queue** architecture.

### Components
*   **Job Queue**: `arq` (backed by **Redis**) handles task scheduling and execution.
*   **Worker**: A dedicated process (`app.worker`) that executes heavy tasks in the background.
*   **Status Store**: **Redis** stores ephemeral job status (`processing`, `completed`, `failed`) and progress updates.
*   **Persistent Store**: **SQLite** (`question_bank.db`) stores job history and results for long-term retrieval via `JobStore`.

### Benefits
*   **Non-blocking**: The API returns a `job_id` immediately.
*   **Reliability**: Jobs continue running even if the user closes the browser.
*   **Persistence**: Frontend monitors job status and resumes checks after page reloads.

---

## 2. State Management Strategy

### A. Backend State (Dual-Layer)
1.  **Hot State (Redis)**:
    *   Used for real-time status polling and progress bars.
    *   Keys: `job_status:{id}`, `job_progress:{id}`, `job_result:{id}`, `cancel:{id}`.
    *   TTL: 1 hour (auto-expires).
2.  **Cold State (SQLite - `JobStore`)**:
    *   Used for history and "My Previous Tests".
    *   Stores: Full questions, user answers, scores, and metadata.
    *   Persists forever (until manually deleted).

### B. Frontend State (Zustand + Persistence)
We replaced local `useState` with **Zustand Stores** wrapped in `persist` middleware (saving to `localStorage`).

| Feature | Store File | Persisted Data |
| :--- | :--- | :--- |
| **Mains Answer** | `mainsAnswerStore.ts` | `jobId`, `status`, `question`, `result`, `error` |
| **Mock Test** | `mockTestStore.ts` | `jobId`, `status`, `testData`, `userAnswers`, `score` |
| **Evaluation** | `evaluateAnswerStore.ts` | `jobId`, `status`, `result`, `files` (metadata only) |

**Behavior:**
1.  **User Starts Job**: `job_id` is saved to Store (and `localStorage`).
2.  **Tab Close/Refresh**: On load, store checks for an active `job_id`.
3.  **Resume**: If a job was `processing`, it immediately resumes polling the backend status endpoint.
4.  **Completion**: Result is saved to Store and persisted.

---

## 3. Process Flows

### Flow 1: Mock Test Generation
1.  **UI**: User selects parameters (Topic: "Volcanism") -> Click "Generate".
2.  **API**: `POST /mock-test/generate-async` -> Enqueues `generate_mock_test_task` to Arq -> Returns `job_id`.
3.  **Worker**:
    *   Retrieves content chunks (Pinecone).
    *   Generates micro-batches of questions (OpenAI/Gemini).
    *   Deduplicates questions (Semantic check).
    *   **Fix Implemented**: Corrected `Document` vs `str` type mismatch during deduplication.
    *   Saves final JSON to Redis & SQLite.
4.  **UI Poll**: Checks `/mock-test/status/{job_id}` every 2s.
5.  **Completion**: Receives questions -> Updates Zustand Store -> Displays Test UI.

### Flow 2: Answer Evaluation
1.  **UI**: User uploads handwriting image.
2.  **API**: `POST /evaluate-answer/` -> Saves temp file -> Enqueues `evaluate_answer_task`.
3.  **Worker**:
    *   Performs OCR (Vision Model).
    *   Retrieves context (RAG).
    *   Evaluates against context.
    *   Saves "Strengths", "Weaknesses", "Model Answer" to Redis.
4.  **UI Poll**: Shows "Analyzing..." -> Displays detailed feedback card on completion.

---

## 4. Key Files Modified

### Backend
*   `app/worker.py`: **[NEW]** The heart of the async system. Defines all tasks.
*   `app/utils/job_tracker.py`: Implements `JobStore` (SQLite) and `Job` dataclass.
*   `app/routes/mock_test.py`: Refactored to expose helper functions (`generate_micro_batches`) for the worker.
*   `app/routes/evaluate_answer.py`: Updated to enqueue tasks instead of blocking.

### Frontend
*   `src/stores/geography/*.ts`: Zustand stores for logic separation.
*   `src/app/mock-test/page.tsx`: Connected to `useMockTestStore`. Added error handling for empty results.
*   `src/app/evaluate/page.tsx`: Connected to `useEvaluateAnswerStore`. Fixed cancel button logic.
*   `src/app/mains-answer/page.tsx`: Connected to `useMainsAnswerStore`.
