# Future Development Roadmap

This document outlines upcoming features and improvements planned for HayMagnet.

### 1. Dynamic API & Model Configuration UI
Currently, API keys and model selections are hardcoded or loaded from `.env` files. We plan to build a settings interface directly into the Streamlit dashboard:
- Allow users to securely input their API keys (Gemini, Groq, Hugging Face) from the UI.
- Allow users to select their preferred LLM models for the Lead Investigator and DB Expert agents from dropdowns, decoupling the system from static code configurations.

### 2. Automated Validation & Connection Testing
To prevent runtime failures during an investigation, the UI will include a background validation script:
- Instantly verify if the provided API keys are valid.
- Test the selected model endpoints for availability and rate-limit status *before* the user clicks "Unleash Agents".

### 3. Robust UI Exception Handling
If an API key is invalid or a model goes offline mid-investigation, the dashboard should handle it gracefully:
- Catch specific API/Connection exceptions.
- Render clear, actionable error messages (e.g., "Groq API Key Invalid" or "Gemini Model Overloaded") in the Streamlit UI rather than crashing the backend server.
- Provide a clear fallback or retry button to the user.
