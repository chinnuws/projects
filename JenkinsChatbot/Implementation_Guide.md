# Jenkins AI Chatbot

A modern, AI-powered chatbot dashboard to interact with Jenkins. It uses Natural Language Processing (NLP) to understand user intent, trigger jobs, and fetch status, all wrapped in a stunning Glassmorphism UI.

## 🚀 Features

- **Natural Language Understanding**: Uses Azure AI Inference (or OpenAI compatible) to parse intent (Trigger vs Status) and extract parameters.
- **Context-Aware**: Reminders previous context to handle multi-turn conversations (e.g., providing missing parameters).
- **Glassmorphism Dashboard**: A premium, dark-themed UI with blur effects, gradients, and smooth animations.
- **Interactive Forms**: Automatically generates input forms when mandatory parameters are missing.
- **Configurable**: Jobs are defined in `backend/jobs.yaml` for easy maintenance.
- **Mock Mode**: Runs without a real Jenkins server for demonstration purposes.

## 📂 Project Structure

```
source-code/
├── backend/                # FastAPI Backend
│   ├── main.py             # API Entry point
│   ├── ai_service.py       # AI Logic (Azure Integration + Fallback)
│   ├── jenkins_service.py  # Jenkins Integration (Real + Mock)
│   ├── config_loader.py    # YAML Config Loader
│   ├── jobs.yaml           # Job Definitions
│   └── requirements.txt    # Python Dependencies
├── frontend/               # React + Vite Frontend
│   ├── src/
│   │   ├── components/
│   │   │   └── ChatInterface.jsx  # Main Chat Logic & UI
│   │   ├── App.jsx         # Dashboard Layout
│   │   ├── main.jsx        # Entry point
│   │   └── index.css       # Global Styles & Glassmorphism
│   ├── vite.config.js      # Vite Config (Proxy setup)
│   └── package.json        # Frontend Dependencies
└── Implementation_Guide.md # This file
```

## 🛠️ Setup Instructions

### Prerequisites
- Python 3.8+
- Node.js & npm

### 1. Backend Setup

1. Navigate to `backend` directory:
   ```bash
   cd backend
   ```

2. Create and Activate Virtual Environment:
   ```bash
   # Windows
   python -m venv venv
   source venv/Scripts/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Configure Environment (Optional):
   Create a `.env` file or set environment variables:
   - `AZURE_AI_ENDPOINT`: Your Azure AI Endpoint.
   - `AZURE_AI_KEY`: Your Azure AI Key.
   - `JENKINS_URL`: URL of your Jenkins server.
   - `JENKINS_USER`: Jenkins username.
   - `JENKINS_TOKEN`: Jenkins API Token.
   - `MOCK_JENKINS`: Set to `true` (default) to test without real Jenkins.

4. Run the Server:
   ```bash
   uvicorn main:app --reload
   ```
   Server will start at `http://localhost:8000`.

### 2. Frontend Setup

1. Navigate to `frontend` directory:
   ```bash
   cd frontend
   ```
2. Create and Activate Virtual Environment:
   *Note: In Node.js, running `npm install` creates the environment (`node_modules`). No explicit activation command is needed.*
   ```bash
   npm install
   ```
3. Run the Development Server:
   ```bash
   npm run dev
   ```
   Access the dashboard at `http://localhost:5173`.

## 🧠 How It Works

### 1. Intent Recognition
The `ai_service.py` sends user text to Azure AI with a system prompt containing the list of available jobs. The AI returns a JSON object with:
- `intent`: TRIGGER or STATUS
- `job_name`: The identified job.
- `parameters`: Extracted entities.

### 2. Parameter Validation
The Backend (`main.py`) checks if `job_name` requires specific parameters (defined in `jobs.yaml`).
- If **Missing**: Returns `action_required: "PROVIDE_PARAMS"` along with the list of missing fields.
- The Frontend detects this and renders an **Interactive Form** inside the chat bubble.

### 3. Execution
- **Mock Mode**: Simulates a successful trigger and returns a fake Build URL.
- **Real Mode**: Uses `python-jenkins` to trigger the job on the actual Jenkins server.

## 🎨 Value Added Features implemented

1.  **Smart Parameter prompting**: Instead of just text, the bot renders a UI form for missing parameters.
2.  **Robust Fallback**: If Azure AI keys are not provided, a keyword-based fallback system works for basic queries.
3.  **Real-time Feedback**: Status badges for job results (Success/Failure) and loading spinners.
4.  **Documentation Integration**: Direct links to Job Documentation if users are confused.

## 🔮 Future Roadmap (Kubernetes)

As requested, for Kubernetes deployment:
1.  **ConfigMap**: The `jobs.yaml` can be mounted as a ConfigMap at runtime. The `config_loader.py` can be updated to watch for file changes or load from a specific path `/etc/config/jobs.yaml`.
2.  **Secrets**: Jenkins tokens and AI keys should be stored in Kubernetes Secrets and injected as Environment Variables.
3.  **Deployment**: Dockerize both Backend and Frontend (Nginx serving React build).

---
**Enjoy your new Jenkins Assistant!**
