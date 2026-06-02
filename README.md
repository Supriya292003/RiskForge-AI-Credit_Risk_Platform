# AI-Powered Credit Risk Intelligence Platform

A production-grade credit risk platform built for NeoStats. It predicts the probability of customer default using the Kaggle Home Credit dataset, explains decisions using SHAP values, extracts human-readable policy rules, and provides a natural language conversational SQL chatbot interface.

---

## 1. System Architecture

The application is split into a modular backend API in Python and a highly visual React single-page application (SPA):

```
                                  +-----------------------+
                                  |     React Frontend    |
                                  |     (Vite | Port 3000) |
                                  +-----------------------+
                                              ^
                                              | HTTP REST
                                              v
                                  +-----------------------+
                                  |    FastAPI Backend    |
                                  |      (Port 8000)      |
                                  +-----------------------+
                                              |
      +----------------------+----------------+----------------------+
      |                      |                                       |
      v                      v                                       v
+-----------+          +-----------+                           +-----------+
|    ML     |          |   SHAP    |                           | Talk-to-  |
| Pipeline  |          | Explainer |                           |   Data    |
+-----------+          +-----------+                           +-----------+
      |                      |                                       |
      v                      v                                       v
  [XGBoost]              [SHAP values]                          [Gemini LLM]
      |                                                              | SQL
      +----------------------+----------------+----------------------+
                             |                |
                             v                v
                        +----------+    +-----------+
                        | Models   |    | SQLite DB |
                        | (.joblib)|    | (.db)     |
                        +----------+    +-----------+
```

---

## 2. Quick Setup & Run Instructions

You can run the entire platform locally using either **Docker Compose** or **Python + Node**.

### Prerequisites
- Create a `.env` file in the root folder (see `.env.example`).
- Ensure you input your `GEMINI_API_KEY` for the conversational SQL chatbot.

---

### Option A: Running with Docker Compose (Recommended)
This starts both the backend API and the React frontend automatically in containerized environments.

1. Build and run the services:
   ```bash
   docker-compose up --build
   ```
2. Once spun up, access the visual interface:
   - **Frontend**: [http://localhost:3000](http://localhost:3000)
   - **FastAPI API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

### Option B: Running Locally (Development Mode)

#### 1. Setup Backend
1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Setup database and train the model (if data is missing, synthetic files are automatically generated):
   ```bash
   python src/ml/train.py
   ```
3. Evaluate model:
   ```bash
   python src/ml/evaluate.py
   ```
4. Start FastAPI server:
   ```bash
   python src/main.py
   ```

#### 2. Setup Frontend
1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install Node packages:
   ```bash
   npm install
   ```
3. Start development server:
   ```bash
   npm run dev
   ```
4. Open your browser to [http://localhost:3000](http://localhost:3000).

---

## 3. Machine Learning Model Design

### Model Selection Rationale
We chose **XGBoost (Extreme Gradient Boosting)** because:
- **Tabular Superiority**: Tree-based ensembles consistently outperform deep learning on credit-risk tabular data.
- **Explainability**: Seamless integration with SHAP values via tree-based paths.
- **Handling Missingness**: XGBoost handles missing values (e.g., missing credit scores) out of the box by routing them to default split nodes.

### Class Imbalance Strategy
The dataset exhibits high class imbalance (~8% defaults). To prevent the model from bias towards non-defaulting loans, we applied:
1. **Stratification**: Preserved label distributions in split splits.
2. **Loss Weighting**: Set `scale_pos_weight = 11.18` (computed as `count(repaid) / count(defaulted)`). This scales the gradient of default cases, adjusting model sensitivity.
3. **Engineered Relational Aggregates**: Extracted applicant summaries from supplementary Credit Bureau history (`bureau.csv`) and previous applications (`previous_application.csv`) to introduce historical behavior metrics.

---

## 4. Evaluation Metrics & Performance

The trained model achieved the following performance metrics:
- **Mean 5-Fold Cross-Validation ROC-AUC**: **0.8846** (with standard dev of ±0.0137)
- **Holdout Test Set ROC-AUC Score**: **0.8909** (measures ranking separation power)
- **Holdout Test Set PR-AUC Score**: **0.7713** (measures precision-recall under imbalance)
- **Holdout Test Set Accuracy**: **0.9633** (96.3%)
- **F1 Score**: **0.7500** (75.0%)

### Global Feature Importance
The top five predictive factors driving defaults are:
1. **`EXT_SOURCE_3`** (External Bureau rating score)
2. **`EXT_SOURCE_2`** (Internal Bureau score)
3. **`AMT_ANNUITY`** (Monthly repayment obligation size)
4. **`DAYS_BIRTH`** (Applicant age - younger profiles show higher risk)
5. **`BUREAU_MAX_OVERDUE_DAYS`** (Active credit history delinquency duration)

---

## 5. Explainable AI (SHAP) & Rules

### SHAP Contributions
For any scored applicant, the platform calculates exact SHAP attribution scores using `shap.TreeExplainer`. The UI renders these as a horizontal waterfall chart:
- **Positive SHAP (Red)**: Factors increasing default probability (e.g., low external ratings, high annuity-to-income ratio).
- **Negative SHAP (Green)**: Factors mitigating risk (e.g., long employment history, zero active overdue records).

### Derived Policy Rules
We fit a shallow `DecisionTreeClassifier` (depth 3) to extract business-readable policies.
Example extracted policy:
```
IF EXT_SOURCE_3 <= 0.35 AND AMT_CREDIT > 200,000 THEN High Risk (Default Rate: ~48%)
```
These are displayed in the **Credit Policy Rules** tab for auditor reviews.

---

## 6. Talk-to-Data Chatbot (NL-to-SQL)

### Prompt Optimization
Our prompt templates in `src/talk_to_data/prompt_templates.py` detail the relational tables schema, instruct the LLM (Gemini 3.5 Flash) to generate SELECT-only queries, and structure output inside markdown blocks.

### Fallback & Hallucination Controls
To prevent SQL injection or destructive commands (e.g., DROP, DELETE):
1. **Keyword Restriction**: Reject queries containing modifications before database execution.
2. **Self-Correction Retry Loop**: If a query fails syntax checks, the error log is passed back to Gemini to auto-correct the code.
3. **Offline Heuristic Mode**: If the API times out (504 gateway deadline) or the key is inactive, the chatbot switches to offline parsing, executing matching queries on the SQLite database and outputting valid analytics.

---

## 7. Known Limitations & Improvements
- **Online SHAP Computation**: While extremely detailed, computing SHAP values on massive datasets online can introduce latency. Pre-computing backgrounds can optimize response speeds.
- **SQL Parsing Coverage**: Complexity increases for nested SQL aggregations. Adding a semantic schema index will improve chatbot answers for highly complex multi-table queries.

---

## 8. Major Software Design Decisions

1. **Decoupled Architecture (React + FastAPI)**: Rather than using standard Python dashboard templates (like Streamlit), we separated the frontend and backend. This decouples CPU-heavy model evaluations and data queries from visual rendering, providing sub-millisecond tab switching and loading spinner state overlays.
2. **Relational SQLite Foundation**: Synthetic Kaggle datasets are stored in SQLite (`credit_risk.db`) with index structures rather than memory buffers. This supports native SQL operations, allowing the Chatbot to resolve complex analytical filters (like GROUP BYs and JOINs) against real tables.
3. **Chatbot Security Sanitization**: To protect the backend database, we implemented a dual-layered security guard. First, the query runner verifies the SQL starts with `SELECT` or `WITH`. Second, it rejects any query containing modification keywords (`DROP`, `DELETE`, `INSERT`, `UPDATE`), preventing injection exploits.
4. **Custom Theme Styling Design**: Built using custom HSL CSS variables and React hooks. The visual layers automatically adapt to dark and light modes by altering global variables on the body wrapper, avoiding visual lag or layout rebuilding.

