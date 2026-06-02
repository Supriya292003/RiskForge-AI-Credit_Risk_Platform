import joblib
import json
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, precision_recall_curve, auc, confusion_matrix
)
import sys

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from src.utils.logger import logger
from src.utils.config import MODELS_DIR
from src.data.preprocessor import get_banker_name

def evaluate_credit_model():
    """
    Evaluates the trained model on test set, merges with cross-validation metrics,
    maps global feature importances to banker names, and saves evaluation reports.
    """
    logger.info("Starting model evaluation and metrics validation...")
    
    xgb_path = MODELS_DIR / "xgboost_model.joblib"
    x_test_path = MODELS_DIR / "X_test.npy"
    y_test_path = MODELS_DIR / "y_test.npy"
    preprocessor_path = MODELS_DIR / "preprocessor.joblib"
    cv_metrics_path = MODELS_DIR / "cv_metrics.json"
    
    if not (xgb_path.exists() and x_test_path.exists() and y_test_path.exists()):
        raise FileNotFoundError("Model or test set artifacts missing. Run train.py first.")
        
    model = joblib.load(xgb_path)
    X_test = np.load(x_test_path)
    y_test = np.load(y_test_path)
    
    prep_data = joblib.load(preprocessor_path)
    feature_names = prep_data["feature_names"]
    
    # Predict
    y_prob = model.predict_proba(X_test)[:, 1]
    y_pred = model.predict(X_test)
    
    # Holdout Test set metrics
    accuracy = accuracy_score(y_test, y_pred)
    precision = precision_score(y_test, y_pred, zero_division=0)
    recall = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)
    roc_auc = roc_auc_score(y_test, y_prob)
    
    precisions, recalls, _ = precision_recall_curve(y_test, y_prob)
    pr_auc = auc(recalls, precisions)
    tn, fp, fn, tp = confusion_matrix(y_test, y_pred).ravel()
    
    # Load CV metrics if available
    cv_metrics = {}
    if cv_metrics_path.exists():
        try:
            with open(cv_metrics_path, "r") as f:
                cv_metrics = json.load(f)
            cv_metrics_path.unlink()  # Clean up temp CV file
        except Exception as e:
            logger.warning(f"Could not load CV metrics file: {e}")
            
    # Combine Metrics
    metrics = {
        "holdout_test": {
            "accuracy": round(float(accuracy), 4),
            "precision": round(float(precision), 4),
            "recall": round(float(recall), 4),
            "f1_score": round(float(f1), 4),
            "roc_auc": round(float(roc_auc), 4),
            "pr_auc": round(float(pr_auc), 4),
        },
        "cross_validation": cv_metrics,
        "confusion_matrix": {
            "true_negatives": int(tn),
            "false_positives": int(fp),
            "false_negatives": int(fn),
            "true_positives": int(tp)
        }
    }
    
    # Save validation metrics to JSON
    metrics_path = MODELS_DIR / "evaluation_metrics.json"
    logger.info(f"Saving combined validation metrics to {metrics_path}")
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=4)
        
    # ----------------------------------------------------
    # Global Feature Importance (Mapped to Banker names)
    # ----------------------------------------------------
    logger.info("Extracting feature importances...")
    importances = model.feature_importances_
    
    # Map to banker names
    feat_imp_list = []
    for name, imp in zip(feature_names, importances):
        if imp > 0.0001:
            feat_imp_list.append({
                "technical_name": name,
                "feature": get_banker_name(name),
                "importance": round(float(imp), 4)
            })
            
    # Sort descending
    feat_imp_list = sorted(feat_imp_list, key=lambda x: x["importance"], reverse=True)
    
    feat_imp_path = MODELS_DIR / "feature_importance.json"
    logger.info(f"Saving feature importances to {feat_imp_path}")
    with open(feat_imp_path, "w") as f:
        json.dump(feat_imp_list[:15], f, indent=4)
        
    # Clean up temporary test files
    try:
        x_test_path.unlink()
        y_test_path.unlink()
    except Exception as e:
        logger.warning(f"Could not clean up temporary numpy files: {e}")
        
    logger.info("Evaluation and validation completed.")
    return metrics

if __name__ == "__main__":
    evaluate_credit_model()
