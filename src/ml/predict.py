import joblib
import pandas as pd
import numpy as np
import shap
import uuid
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from src.utils.logger import logger
from src.utils.config import MODELS_DIR
from src.utils.helpers import calculate_risk_band
from src.data.preprocessor import get_banker_name

# Global variables for caching model artifacts
_MODEL = None
_PREPROCESSOR_INFO = None
_SHAP_EXPLAINER = None

def load_inference_artifacts():
    """Loads and caches the preprocessing pipeline, XGBoost model, and SHAP explainer."""
    global _MODEL, _PREPROCESSOR_INFO, _SHAP_EXPLAINER
    
    if _MODEL is not None:
        return _MODEL, _PREPROCESSOR_INFO, _SHAP_EXPLAINER
        
    xgb_path = MODELS_DIR / "xgboost_model.joblib"
    prep_path = MODELS_DIR / "preprocessor.joblib"
    
    if not (xgb_path.exists() and prep_path.exists()):
        raise FileNotFoundError("Model or preprocessor artifacts missing. Run train.py first.")
        
    logger.info("Loading inference artifacts...")
    _MODEL = joblib.load(xgb_path)
    _PREPROCESSOR_INFO = joblib.load(prep_path)
    
    logger.info("Initializing SHAP explainer...")
    _SHAP_EXPLAINER = shap.TreeExplainer(_MODEL)
    
    return _MODEL, _PREPROCESSOR_INFO, _SHAP_EXPLAINER

def generate_explanation_narrative(score: float, band: str, increasing: list, reducing: list) -> str:
    """Generates a banker-friendly business explanation narrative for a credit score."""
    if not increasing and not reducing:
        return f"The applicant's credit risk profile is evaluated as {band} (Risk Score: {score*100:.1f}%), aligning closely with standard portfolio baselines."
        
    narrative = f"The credit applicant is classified in the **{band}** band with an assessed default probability of **{score*100:.1f}%**. \n\n"
    
    if increasing:
        top_inc = increasing[0]
        narrative += f"• **Primary Risk Driver**: **{top_inc['feature']}** contributed the largest increase in risk (+{top_inc['val']*100:.1f}% score adjustment). "
        if len(increasing) > 1:
            other_inc = [f"**{item['feature']}** (+{item['val']*100:.1f}%)" for item in increasing[1:3]]
            narrative += f"Secondary risk-increasing factors include: {', '.join(other_inc)}. "
        narrative += "\n"
            
    if reducing:
        top_red = reducing[0]
        narrative += f"• **Primary Mitigating Factor**: **{top_red['feature']}** provided the strongest risk reduction ({top_red['val']*100:.1f}% score adjustment). "
        if len(reducing) > 1:
            other_red = [f"**{item['feature']}** ({item['val']*100:.1f}%)" for item in reducing[1:3]]
            narrative += f"Other mitigating factors include: {', '.join(other_red)}."
        narrative += "\n"
            
    return narrative

def predict_risk(input_data: dict) -> dict:
    """
    Predicts the credit default probability for a single applicant and returns
    the score, risk band, SHAP explanations, and model governance audit details.
    """
    model, prep_info, explainer = load_inference_artifacts()
    preprocessor = prep_info["preprocessor"]
    feature_names = prep_info["feature_names"]
    numerical_cols = prep_info["numerical_cols"]
    categorical_cols = prep_info["categorical_cols"]
    
    # 1. Model Governance: Hash inputs & create unique prediction ID
    sorted_input_str = json.dumps(input_data, sort_keys=True)
    input_hash = hashlib.sha256(sorted_input_str.encode('utf-8')).hexdigest()
    prediction_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()
    
    # 2. Map input form values
    processed_data = input_data.copy()
    # Normalize Y/N flags to Yes/No dynamically
    for col in ["FLAG_OWN_CAR", "FLAG_OWN_REALTY"]:
        if col in processed_data:
            val = processed_data[col]
            if val in ["Y", "Yes"]:
                processed_data[col] = "Yes"
            elif val in ["N", "No"]:
                processed_data[col] = "No"
            
    # Process numeric fields from age/employment years to days
    if "age_years" in processed_data:
        processed_data["DAYS_BIRTH"] = -int(float(processed_data["age_years"]) * 365.25)
        del processed_data["age_years"]
        
    if "employment_years" in processed_data:
        emp_years = float(processed_data["employment_years"])
        if processed_data.get("NAME_INCOME_TYPE") == "Pensioner" or emp_years < 0:
            processed_data["DAYS_EMPLOYED"] = 365243
        else:
            processed_data["DAYS_EMPLOYED"] = -int(emp_years * 365.25)
        del processed_data["employment_years"]

    # Convert to DataFrame
    df_raw = pd.DataFrame([processed_data])
    
    # Align schemas
    all_schema_cols = numerical_cols + categorical_cols
    for col in all_schema_cols:
        if col not in df_raw.columns:
            df_raw[col] = np.nan
            
    X_raw = df_raw[all_schema_cols]
    X_transformed = preprocessor.transform(X_raw)
    
    # 3. Predict Score
    prob = float(model.predict_proba(X_transformed)[0, 1])
    risk_band = calculate_risk_band(prob)
    
    # 4. Compute SHAP Values
    shap_values = explainer.shap_values(X_transformed)
    if isinstance(shap_values, list):
        instance_shap = shap_values[1][0]
    elif len(shap_values.shape) == 3:
        instance_shap = shap_values[0, :, 1]
    else:
        instance_shap = shap_values[0]
        
    # Map and translate SHAP values to banker names
    shap_increasing = []
    shap_reducing = []
    
    for name, val in zip(feature_names, instance_shap):
        if abs(val) > 0.001:
            item = {
                "technical_name": name,
                "feature": get_banker_name(name),
                "val": round(float(val), 4)
            }
            if val >= 0:
                shap_increasing.append(item)
            else:
                shap_reducing.append(item)
                
    # Sort contributions
    shap_increasing = sorted(shap_increasing, key=lambda x: x["val"], reverse=True)
    shap_reducing = sorted(shap_reducing, key=lambda x: x["val"]) # Strongest negative first
    
    base_value = float(explainer.expected_value)
    
    # 5. Generate Explanation narrative
    narrative = generate_explanation_narrative(prob, risk_band, shap_increasing, shap_reducing)
    
    # Compile results
    result = {
        "prediction_id": prediction_id,
        "timestamp": timestamp,
        "model_version": "v1.0.0",
        "input_hash": input_hash,
        "risk_score": round(prob, 4),
        "risk_band": risk_band,
        "base_value": round(base_value, 4),
        "risk_increasing_factors": shap_increasing[:10],
        "risk_reducing_factors": shap_reducing[:10],
        "explanation_narrative": narrative,
        "governance_audit": {
            "preprocessor_fingerprint": "fit-preprocessor-joblib-v1",
            "model_architecture": "XGBoost Classifier",
            "decision_thresholds": "Low: <30%, Medium: 30-70%, High: >=70%"
        }
    }
    
    return result

if __name__ == "__main__":
    sample_customer = {
        "NAME_CONTRACT_TYPE": "Cash loans",
        "CODE_GENDER": "M",
        "FLAG_OWN_CAR": "No",
        "FLAG_OWN_REALTY": "Yes",
        "CNT_CHILDREN": 0,
        "AMT_INCOME_TOTAL": 65000.0,
        "AMT_CREDIT": 450000.0,
        "AMT_ANNUITY": 20000.0,
        "AMT_GOODS_PRICE": 400000.0,
        "NAME_INCOME_TYPE": "Working",
        "NAME_EDUCATION_TYPE": "Secondary / secondary special",
        "NAME_FAMILY_STATUS": "Single / not married",
        "NAME_HOUSING_TYPE": "House / apartment",
        "age_years": 29,
        "employment_years": 2.5,
        "OCCUPATION_TYPE": "Laborers",
        "EXT_SOURCE_1": 0.2,
        "EXT_SOURCE_2": 0.3,
        "EXT_SOURCE_3": 0.15,
        "REGION_RATING_CLIENT": 3,
        "BUREAU_LOAN_COUNT": 5,
        "BUREAU_ACTIVE_LOANS": 2,
        "BUREAU_MAX_OVERDUE_DAYS": 30,
        "BUREAU_TOTAL_DEBT": 65000.0,
        "PREV_REFUSED_COUNT": 2
    }
    
    res = predict_risk(sample_customer)
    print(f"Prediction ID: {res['prediction_id']}")
    print(f"Timestamp: {res['timestamp']}")
    print(f"Risk: {res['risk_score']} ({res['risk_band']})")
    print(f"Narrative: {res['explanation_narrative']}")
