# Chef Gemini — Recipe Assistant

An intelligent, full-stack culinary assistant built with the **Google Agent Development Kit (ADK)** and powered by **Gemini 2.5 Flash**. Chef Gemini helps users create delicious meals with ingredients on hand, manage favorite recipes, generate food photography and video demonstrations, estimate nutritional content, find nearby grocery stores, and deliver structured A2UI visual cards.

![Chef Gemini Demo](demo.gif)

---

## 🌟 Implemented Capabilities & Cloud Services

Chef Gemini's agent logic in `app/` and deployment manifest `agents-cli-manifest.yaml` implement the following capabilities:

### 🧠 Agent Core & Memory
- **Gemini 2.5 Flash Engine**: Powered by `gemini-2.5-flash` via `google-adk`.
- **Cross-Session Memory Bank**: Automatically preloads dietary preferences and allergy constraints (`PreloadMemoryTool`) and updates session memories back to the **Vertex AI Memory Service** (`generate_memories_callback`).
- **Sandbox Code Execution**: Utilizes `AgentEngineSandboxCodeExecutor` for safe Python code execution within Vertex AI Agent Engine.

### 🎨 Visual & Media Generation
- **Vertex AI Imagen (Image Generation)**: Synthesizes high-quality food photography using `gemini-3.1-flash-lite-image` in the global region (`generate_recipe_image`).
- **Vertex AI Omni (Video Generation)**: Generates short cooking technique videos using `gemini-omni-flash-preview` via Vertex AI Interactions API (`generate_recipe_video`).
- **Google Cloud Storage (GCS)**: Streams generated image and video byte artifacts directly to a public Cloud Storage bucket.

### 🗄️ Database & Search Integration
- **Google Cloud Firestore**: Persists, queries, lists, and deletes recipe documents in a dedicated Firestore `recipes` collection (`save_recipe_to_firestore`, `list_recipes_from_firestore`, `get_recipe_from_firestore`, `delete_recipe_from_firestore`).
- **TheMealDB API**: Connects to the public TheMealDB search API to retrieve real online recipes (`search_online_recipes_api`).
- **Google Maps & Places APIs**: Converts addresses into geographic coordinates (`geocode_address`) and finds nearby grocery stores and supermarkets (`find_nearby_places`).

### 🥗 Nutrition & UI Rendering
- **Nutritional Analysis Engine**: Computes calorie estimates, macronutrients (protein, carbs, fat), and dietary badges (`Low Carb`, `High Protein`, `Vegetarian-Friendly`) for lists of ingredients (`calculate_recipe_nutrition`).
- **A2UI Structured Component Rendering**: Emits lightweight structured visual UI cards (A2UI schema v0.8) via `A2uiSchemaManager` and `a2ui_callback`.
- **FastAPI Proxy & Web Chat Interface**: A minimal FastAPI backend (`frontend/main.py`) translating browser chat requests to the deployed A2A agent using Application Default Credentials.

---

## 📂 Project Structure

```
recipe-assistant/
├── app/                        # Core agent implementation
│   ├── agent.py                # Main agent definitions, tools, and callbacks
│   ├── a2ui_utils.py           # A2UI response formatting callback
│   └── fast_api_app.py         # Agent Engine web server setup
├── frontend/                   # Web frontend proxy & static chat UI
│   ├── main.py                 # FastAPI proxy forwarding chat requests over A2A
│   ├── static/
│   │   └── index.html          # Custom styled chat UI with prompt chips
│   └── requirements.txt        # Frontend dependencies
├── tests/                      # Unit and integration test suite
├── agents-cli-manifest.yaml    # Agent Platform deployment manifest
├── deployment_metadata.json    # Agent Engine resource IDs and configuration
├── pyproject.toml              # Python dependencies managed by uv
└── demo.gif                    # Animated screen recording of the agent
```

---

## 🛠️ Setup & Local Execution Instructions

### Prerequisites
- **Python 3.14+** or virtual environment manager (`uv`)
- **google-agents-cli**: Installed via `uv tool install google-agents-cli`
- **Google Cloud SDK (`gcloud`)**: Authenticated with Application Default Credentials

### 1. Install Dependencies
```bash
uv sync
```

### 2. Run Agent Playground (Local ADK Server)
To run and test the agent with auto-reload:
```bash
uv run adk web app --reload_agents
```

### 3. Run Frontend Web App Locally
Navigate to the `frontend/` directory, set environment variables, and start the proxy server:
```bash
cd frontend
pip install -r requirements.txt

export AGENT_ENGINE_RESOURCE_NAME="projects/<PROJECT_ID>/locations/us-east1/reasoningEngines/<ENGINE_ID>"
export AGENT_DIRECTORY="app"

python main.py
```
*(The frontend server starts on port `8080`)*

### 4. Run Automated Test Suite
To verify agent tools, memory callbacks, and server endpoints:
```bash
uv run pytest tests/unit tests/integration
```

---

## 🚀 Deployment & Publishing

### Deploy to Agent Runtime
```bash
agents-cli deploy
```

### Deploy Frontend to Cloud Run
```bash
gcloud run deploy recipe-assistant-frontend \
  --source ./frontend \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars AGENT_ENGINE_RESOURCE_NAME="<RESOURCE_NAME>",AGENT_DIRECTORY="app"
```
