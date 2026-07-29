# 📊 QuantifyX
### *The Ultimate NEPSE Research Platform & Agentic AI Wealth Advisor*

> [!IMPORTANT]
> **"From speculative trading to intelligent wealth engineering — purpose-built for NEPSE."**

**QuantifyX** is a next-generation financial intelligence ecosystem designed exclusively for the **Nepalese Stock Market (NEPSE)**. By combining high-performance **backtesting infrastructure** with **Agentic AI**, QuantifyX empowers investors to make disciplined, data-driven decisions with institutional-grade rigor.

---

### 🛡️ Disclaimer
> [!WARNING]
> **Financial Risk Disclosure:** QuantifyX is a tool designed for research and educational purposes only. It does not constitute formal financial, legal, or tax advice. The NEPSE market involves significant risk, and past performance is not indicative of future results. Users are solely responsible for their investment decisions and should conduct their own due diligence or consult with a certified financial planner.

---

## 🌟 Core Pillars

### 📈 1. NEPSE Backtesting Engine
*Stop guessing. Start validating.* Test your strategies against historical NEPSE data **before committing capital**.

* **Precision Strategies:** Simulate Moving Average Crossovers, RSI Divergence, and custom multi-indicator systems.
* **Institutional-Grade Metrics:** Instantly evaluate $CAGR$, $Maximum Drawdown$, $Win/Loss Ratio$, and the $Sharpe Ratio$.
* **Optimization Engine:** Automatically discover optimal indicator parameters using **Parameter Sweeping** to find the "market's pulse."

### 🤖 2. Agentic AI Portfolio Architect
*AI that manages more than charts — it manages your financial life.*

* **Holistic Financial Snapshot:** Unified view of your income, investments, liabilities, and assets.
* **Liability Liquidation Intelligence:** Detects “toxic debt” and constructs **Snowball** or **Avalanche** repayment strategies.
* **Smart Capital Rebalancing:** Actionable insights for reallocating capital from low-yield assets to high-growth opportunities.
* **Vision-Driven Planning:** Define goals like *"Financial Independence in 10 Years"* and receive a dynamic, adaptive roadmap.

---

## 🚀 Platform Workflow

| Phase | Action | Outcome |
| :--- | :--- | :--- |
| **01. Research** | Choose a NEPSE script (e.g., **NTC**, **GBIME**) and apply a strategy. | Precise visual clarity of every historical **entry and exit point**. |
| **02. Optimize** | System recommends micro-adjustments (e.g., RSI $14 \rightarrow 11$). | Strategies aligned with unique **local volatility patterns**. |
| **03. Advisory** | Upload your balance sheet for a **Financial Health Checkup**. | Actionable intelligence on debt and asset allocation. |

> [!TIP]
> **AI Insight Example:**
> *"You are servicing a 14% personal loan while holding assets yielding only 5%. Liquidating **Portfolio X** to settle **Loan Y** will increase your monthly investment capacity by **Rs. 15,000**."*

---

## 🛠️ Technology Stack

| Layer | Technologies |
| :--- | :--- |
| **Interface** | `React` |
| **AI & Intelligence** | `FastAPI` • `LangChain` • `CrewAI`• `Langgraph` |
| **Quant Engine** | `Pandas` • `NumPy` • `TA-Lib` |
| **Data Persistence** | `PostgreSQL` • `NeonDb` |

---

## 💻 Getting Started

### 📦 Local Development

QuantifyX is two services: a FastAPI backend and a Vite/React frontend. Both
must be running.

```bash
# Clone the repository
git clone https://github.com/Poshan-Karki/QuantifyX.git
cd QuantifyX
```

**1. Backend** (needs Python 3.11 and a PostgreSQL instance):

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux

pip install -r requirements-dev.txt

cp .env.example .env           # then fill in DATABASE_URL
uvicorn main:app --reload      # serves on http://localhost:8000
```

**2. Frontend** (needs Node 20+), in a second terminal:

```bash
cd frontend/front
npm install
npm run dev                    # serves on http://localhost:5173
```

The frontend defaults to `http://localhost:8000` for the API, so no
configuration is needed for local work.

### 🧪 Tests

```bash
cd backend
python -m pytest               # 37 tests
```

---

## 🚢 Deployment

### Environment variables

| Service | Variable | Required | Purpose |
| :--- | :--- | :--- | :--- |
| Backend | `DATABASE_URL` | **Yes** | Postgres connection string. The app refuses to start without it. |
| Backend | `ALLOWED_ORIGINS` | **Yes** in prod | Comma-separated frontend origins for CORS. `*` will not work, because the API sends credentials. |
| Backend | `groq_api_key` | No | Reserved for the unreleased AI advisor. |
| Frontend | `VITE_API_URL` | **Yes** in prod | Public URL of the backend, no trailing slash. |

> [!IMPORTANT]
> `VITE_API_URL` is inlined by Vite at **build time**, not read at runtime.
> It must be set on whichever host runs `npm run build`; changing it later
> requires a rebuild, not a restart.

The two services deploy separately. **Deploy the backend first** — the frontend
build needs its public URL.

### 1. Backend

Any host that runs Python 3.11 and an ASGI server.

| Setting | Value |
| :--- | :--- |
| Root directory | `backend` |
| Build command | `pip install -r requirement.txt` |
| Start command | `uvicorn main:app --host 0.0.0.0 --port $PORT` |

Set `DATABASE_URL` and `ALLOWED_ORIGINS` in the host's environment. Most hosts
inject `$PORT`; if yours does not, substitute a fixed port.

> [!NOTE]
> The dependency set is large (~340 MB unzipped, mostly `scipy`, `pandas` and
> `scikit-learn`). This rules out size-limited serverless platforms such as
> Vercel's Python runtime, and needs a host with enough memory to import the
> scientific stack at startup.

### 2. Frontend

Static build, deployable to any static host or CDN.

| Setting | Value |
| :--- | :--- |
| Root directory | `frontend/front` |
| Build command | `npm run build` |
| Output directory | `dist` |

Set `VITE_API_URL` to the backend URL from step 1, then deploy.

Because the app uses client-side routing, the host must rewrite unknown paths
to `index.html`, or visiting `/Backtest` directly will 404.
`frontend/front/vercel.json` configures this for Vercel; other hosts have an
equivalent SPA-fallback or rewrite setting.

### 3. Close the CORS loop

Set the backend's `ALLOWED_ORIGINS` to the deployed frontend origin and
redeploy the backend.

> [!TIP]
> Preview/branch deployments usually get their own generated URLs, which will
> fail CORS against an exact-match `ALLOWED_ORIGINS` list. Add those origins
> explicitly if you need previews to reach the API.


