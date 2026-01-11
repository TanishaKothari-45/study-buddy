# LangSmith Integration Guide

This project uses [LangSmith](https://smith.langchain.com/) for tracing, monitoring, and debugging LLM calls.

## Setup

1.  **Create an Account**: Sign up at [smith.langchain.com](https://smith.langchain.com/).
2.  **Get API Key**: Go to Settings -> API Keys and generate a new key.
3.  **Configure Environment**: Add the following to your `.env` file:

    ```bash
    # LangSmith Tracing
    LANGCHAIN_TRACING_V2=true
    LANGCHAIN_API_KEY=your-api-key-here
    LANGCHAIN_PROJECT=study-buddy
    ```

## Traced Operations

The following operations are currently instrumented:

| Operation | Provider | File | Description |
| :--- | :--- | :--- | :--- |
| `mains_answer_generation` | Gemini | `routes/mains_answer.py` | Traces the full mains answer generation pipeline |
| `mock_test_generation` | OpenAI | `routes/mock_test.py` | Traces mock test question generation |
| `evaluate_answer_endpoint` | Gemini | `routes/evaluate_answer.py` | Traces answer evaluation (OCR + feedback) |
| `question_parser` | Gemini | `utils/question_parser.py` | Traces extraction of search terms from questions |
| `metadata_enrichment_batch` | OpenAI | `utils/metadata_enricher.py` | Traces batch classification of content chunks |
| `mcp_keyword_extraction` | OpenAI | `mcp_current_affairs/...` | Traces keyword extraction for news search |

## Viewing Traces

1.  Log in to [LangSmith](https://smith.langchain.com/).
2.  Select the `study-buddy` project.
3.  You will see a list of runs. Click on any run to see:
    *   **Inputs**: The prompt sent to the LLM.
    *   **Outputs**: The response received.
    *   **Latency**: How long the call took.
    *   **Token Usage**: Estimated tokens (for OpenAI).
    *   **Errors**: Any exceptions that occurred.

## Disabling Tracing

To disable tracing without removing code, simply set `LANGCHAIN_TRACING_V2=false` in your `.env` file.
