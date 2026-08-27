# 📊 QuantifyX
### *The Ultimate NEPSE Research Platform & Agentic AI Wealth Advisor*

> [!IMPORTANT]
> **"From speculative trading to intelligent wealth engineering — purpose-built for NEPSE."**

**QuantifyX** is a next-generation financial intelligence ecosystem designed exclusively for the **Nepalese Stock Market (NEPSE)**. By combining high-performance **backtesting infrastructure** with **Agentic AI**, QuantifyX empowers investors to make disciplined, data-driven decisions with institutional-grade rigor.

---

### 🛡️ Disclaimer
> [!WARNING]
> **Financial Risk Disclosure:** QuantifyX is a tool designed for research and educational purposes only. It does not constitute formal financial, legal, or tax advice. The NEPSE market involves significant risk, and past performance is not indicative of future results. Users are solely responsible for their investment decisions and should conduct their own due diligence or consult with a certified financial planner.

> [!CAUTION]
> **Known data limitation:** prices in the `nepseintel` table are **not adjusted
> for corporate actions** (bonus issues, splits, rights). Any return measured
> across one is wrong, and the artificial price gap can read as a volatility
> regime change that never happened. Check a symbol's corporate action history
> before trusting a long window. Delisted symbols *are* retained, so the data
> does not suffer from survivorship bias.

---

## 🌟 Core Pillars

### 📈 1. NEPSE Backtesting Engine
*Stop guessing. Start validating.* Test your strategies against historical NEPSE data **before committing capital**.

* **Eight strategies:** Bollinger Band, MA Crossover, Mean Reversion, Bollinger+RSI, Volume Breakout, MACD Cross, RSI Mean Reversion and ATR Breakout — all sharing one execution model.
* **Honest execution:** Entries fill at the next bar's open. Fee and slippage are charged together on entry and again on exit, so a cost setting cannot flatter a result.
* **Reported metrics:** Return %, Buy & Hold Return %, Max Drawdown %, Win Rate %, Total Trades and Sharpe Ratio.
* **Out-of-sample selection:** Auto Strategy chooses on an earlier slice of history and reports on the later slice it never saw.
* **Regime detection:** A rule-based classifier (`/regime`) and a BIC-selected Hidden Markov model (`/hmm`) decoded forward-only, so no label uses a bar that had not happened yet.

### 🤖 2. Agentic AI Portfolio Architect — *planned, not in this release*

> [!NOTE]
> Nothing in this section ships today. The `/Ai` route is a placeholder, and the
> prototype agent module was removed because it could not be imported. The
> capabilities below are the roadmap, not the current build.

* **Holistic Financial Snapshot:** Unified view of your income, investments, liabilities, and assets.
* **Liability Liquidation Intelligence:** Detects “toxic debt” and constructs **Snowball** or **Avalanche** repayment strategies.
* **Smart Capital Rebalancing:** Actionable insights for reallocating capital from low-yield assets to high-growth opportunities.
* **Vision-Driven Planning:** Define goals like *"Financial Independence in 10 Years"* and receive a dynamic, adaptive roadmap.

---

## 🚀 Platform Workflow

| Phase | Action | Outcome |
| :--- | :--- | :--- |
| **01. Research** | Choose a NEPSE script (e.g., **NTC**, **GBIME**) and apply a strategy. | Precise visual clarity of every historical **entry and exit point**. |
| **02. Classify** | Detect the current market regime, by rule or by HMM. | A shortlist of strategies suited to **this** kind of market. |
| **03. Validate** | Turn on Auto Strategy. | The strategy is picked on earlier data and scored on **data it never saw**. |
| **04. Advisory** *(planned)* | Upload your balance sheet for a **Financial Health Checkup**. | Not in this release — see the roadmap note above. |

> [!TIP]
> **AI Insight Example** *(illustrative — the advisor is not built yet):*
> *"You are servicing a 14% personal loan while holding assets yielding only 5%. Liquidating **Portfolio X** to settle **Loan Y** will increase your monthly investment capacity by **Rs. 15,000**."*

---

## 🛠️ Technology Stack

| Layer | Technologies |
| :--- | :--- |
| **Interface** | `React` • `Vite` • `lightweight-charts` |
| **API** | `FastAPI` • `Pydantic` • `Uvicorn` |
| **Quant Engine** | `Pandas` • `NumPy` • `backtesting.py` • `ta` |
| **Regime Detection** | `hmmlearn` • `scikit-learn` |
| **Data Persistence** | `PostgreSQL` • `NeonDb` |

> [!NOTE]
> The AI advisor stack (LangChain, LangGraph, Groq) is not listed because it is
> not installed. Those pins were removed along with the unfinished agent module;
> they added roughly a gigabyte to the image and no live endpoint imported them.

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
```

Create `backend/.env` with your Postgres connection string — the app refuses to
start without it:

```bash
DATABASE_URL=postgresql://user:password@host/dbname
```

Then run the API:

```bash
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
python -m pytest               # 168 tests, ~2 min
```

```bash
cd frontend/front
npm test                       # 11 tests
npm run lint
```

Both suites run on every push and pull request — see
[`.github/workflows/ci.yml`](.github/workflows/ci.yml). The backend suite never
touches the database; it builds its own frames or uses a fake session.

---

## 🚢 Deployment

### Environment variables

| Service | Variable | Required | Purpose |
| :--- | :--- | :--- | :--- |
| Backend | `DATABASE_URL` | **Yes** | Postgres connection string. The app refuses to start without it. |
| Backend | `ALLOWED_ORIGINS` | **Yes** in prod | Comma-separated frontend origins for CORS. `*` will not work, because the API sends credentials. |
| Backend | `LOG_LEVEL` | No | Defaults to `INFO`. Every request is logged with its duration. |
| Backend | `RATE_LIMIT_ENABLED` | No | Set to `0` to disable rate limiting. On by default. |
| Backend | `RATE_LIMIT_REDIS_URL` | No | Share rate-limit counters across workers. Defaults to in-process, which means one allowance *per worker*. |
| Backend | `TRUST_PROXY_HEADERS` | No | Set to `1` only behind a proxy that overwrites `X-Forwarded-For`. Otherwise a client can spoof it and mint itself a fresh allowance per request. |
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
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn main:app --host 0.0.0.0 --port $PORT` |

Set `DATABASE_URL` and `ALLOWED_ORIGINS` in the host's environment. Most hosts
inject `$PORT`; if yours does not, substitute a fixed port.

> [!NOTE]
> The dependency set is large (~340 MB unzipped, mostly `scipy`, `pandas` and
> `scikit-learn`). This rules out size-limited serverless platforms such as
> Vercel's Python runtime, and needs a host with enough memory to import the
> scientific stack at startup.

> [!TIP]
> Rate limiting stores its counters in-process, so each uvicorn worker gets its
> own allowance. Run a single worker, or set `RATE_LIMIT_REDIS_URL` so they share
> one. `/hmm` is the endpoint worth protecting — an uncached symbol costs seconds
> of CPU.

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


