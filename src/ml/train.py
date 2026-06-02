import joblib
import json
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.tree import DecisionTreeClassifier, _tree
from sklearn.metrics import roc_auc_score, precision_recall_curve, auc, f1_score, precision_score, recall_score
from xgboost import XGBClassifier
import sys

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from src.utils.logger import logger
from src.utils.config import MODELS_DIR
from src.data.loader import load_and_merge_data
from src.data.preprocessor import fit_transform_data, get_banker_name

def extract_banker_rules(tree, feature_names, numerical_cols, scaler):
    """
    Traverses a fitted Decision Tree to extract banker-friendly, unscaled rules
    leading to High/Medium Default Risk.
    """
    tree_ = tree.tree_
    means = scaler.mean_
    scales = scaler.scale_
    
    rules = []
    
    def recurse(node, depth, current_rule):
        if tree_.feature[node] == _tree.TREE_UNDEFINED:
            values = tree_.value[node][0]
            total = sum(values)
            prob_default = values[1] / total if total > 0 else 0
            
            # If the leaf predicts high risk of default
            if prob_default > 0.12:
                rules.append({
                    "rule": " AND ".join(current_rule),
                    "default_probability": round(prob_default, 3),
                    "risk_band": "High Risk" if prob_default >= 0.28 else "Medium Risk",
                    "sample_size": int(total)
                })
        else:
            tech_name = feature_names[tree_.feature[node]]
            threshold = tree_.threshold[node]
            
            # Translate and unscale threshold
            if tech_name in numerical_cols:
                # Unscale the numerical feature
                num_idx = numerical_cols.index(tech_name)
                unscaled_val = threshold * scales[num_idx] + means[num_idx]
                banker_name = get_banker_name(tech_name)
                
                # Special formatting for age and employment days
                if tech_name == "DAYS_BIRTH":
                    # DAYS_BIRTH is negative: DAYS_BIRTH <= threshold means Age >= -unscaled_val/365.25
                    age_val = round(-unscaled_val / 365.25, 1)
                    left_cond = f"{banker_name} >= {age_val}"
                    right_cond = f"{banker_name} < {age_val}"
                elif tech_name == "DAYS_EMPLOYED":
                    if unscaled_val >= 365243:
                        left_cond = f"{banker_name} is Retired"
                        right_cond = f"{banker_name} is Employed"
                    else:
                        emp_val = round(-unscaled_val / 365.25, 1)
                        left_cond = f"{banker_name} >= {emp_val}"
                        right_cond = f"{banker_name} < {emp_val}"
                else:
                    # General numerical mapping
                    is_currency = any(kw in banker_name for kw in ["Income", "Credit", "Annuity", "Price", "Debt", "Approved"]) and not any(kw in banker_name for kw in ["Days", "Loans", "Applications", "Count", "Refused"])
                    if is_currency:
                        formatted_val = f"${unscaled_val:,.0f}"
                    elif "Days" in banker_name:
                        formatted_val = f"{unscaled_val:.0f} Days"
                    elif any(kw in banker_name for kw in ["Count", "Loans", "Applications", "Refused"]):
                        formatted_val = f"{unscaled_val:.0f}"
                    else:
                        formatted_val = f"{unscaled_val:.2f}"
                        
                    left_cond = f"{banker_name} <= {formatted_val}"
                    right_cond = f"{banker_name} > {formatted_val}"
            else:
                # Categorical column (one-hot encoded) - threshold is always 0.5
                banker_name = get_banker_name(tech_name)
                left_cond = f"{banker_name} is No"
                right_cond = f"{banker_name} is Yes"
                
            # Traversal
            recurse(tree_.children_left[node], depth + 1, current_rule + [left_cond])
            recurse(tree_.children_right[node], depth + 1, current_rule + [right_cond])

    recurse(0, 1, [])
    return sorted(rules, key=lambda x: x["default_probability"], reverse=True)

def train_credit_risk_model():
    """
    Trains the XGBoost model using 5-Fold Stratified Cross-Validation
    to calculate realistic performance metrics, then fits final model.
    """
    logger.info("Initializing model training process with 5-Fold Cross-Validation...")
    
    # 1. Load and pre-process data
    df = load_and_merge_data()
    X_trans, y, feature_names = fit_transform_data(df, save_pipeline=True)
    y = y.values
    
    # Load preprocessing scaler for rule unscaling
    prep_path = MODELS_DIR / "preprocessor.joblib"
    prep_data = joblib.load(prep_path)
    preprocessor = prep_data["preprocessor"]
    scaler = preprocessor.named_transformers_["num"].named_steps["scaler"]
    numerical_cols = prep_data["numerical_cols"]
    
    # 2. 5-Fold Stratified Cross-Validation
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_auc_scores = []
    cv_pr_auc_scores = []
    cv_f1_scores = []
    cv_precision_scores = []
    cv_recall_scores = []
    
    logger.info("Running 5-Fold Stratified Cross-Validation...")
    for fold, (train_idx, val_idx) in enumerate(cv.split(X_trans, y), 1):
        X_tr, X_val = X_trans[train_idx], X_trans[val_idx]
        y_tr, y_val = y[train_idx], y[val_idx]
        
        # Calculate balance weight for this fold
        pos_w = sum(y_tr == 0) / sum(y_tr == 1)
        
        fold_model = XGBClassifier(
            n_estimators=150,
            max_depth=4,
            learning_rate=0.08,
            scale_pos_weight=pos_w,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            eval_metric="logloss"
        )
        fold_model.fit(X_tr, y_tr, verbose=False)
        
        # Predict on validation fold
        y_val_prob = fold_model.predict_proba(X_val)[:, 1]
        y_val_pred = fold_model.predict(X_val)
        
        # Calculate metrics
        auc_score = roc_auc_score(y_val, y_val_prob)
        precisions, recalls, _ = precision_recall_curve(y_val, y_val_prob)
        pr_auc = auc(recalls, precisions)
        
        cv_auc_scores.append(auc_score)
        cv_pr_auc_scores.append(pr_auc)
        cv_f1_scores.append(f1_score(y_val, y_val_pred, zero_division=0))
        cv_precision_scores.append(precision_score(y_val, y_val_pred, zero_division=0))
        cv_recall_scores.append(recall_score(y_val, y_val_pred, zero_division=0))
        
        logger.info(f"Fold {fold} - ROC-AUC: {auc_score:.4f} | PR-AUC: {pr_auc:.4f}")
        
    cv_metrics = {
        "cv_roc_auc_mean": round(float(np.mean(cv_auc_scores)), 4),
        "cv_roc_auc_std": round(float(np.std(cv_auc_scores)), 4),
        "cv_pr_auc_mean": round(float(np.mean(cv_pr_auc_scores)), 4),
        "cv_pr_auc_std": round(float(np.std(cv_pr_auc_scores)), 4),
        "cv_f1_mean": round(float(np.mean(cv_f1_scores)), 4),
        "cv_precision_mean": round(float(np.mean(cv_precision_scores)), 4),
        "cv_recall_mean": round(float(np.mean(cv_recall_scores)), 4),
    }
    
    logger.info(f"Cross-Validation complete. Mean ROC-AUC: {cv_metrics['cv_roc_auc_mean']:.4f} ± {cv_metrics['cv_roc_auc_std']:.4f}")
    
    # Save CV metrics temporarily so evaluate.py can combine them
    with open(MODELS_DIR / "cv_metrics.json", "w") as f:
        json.dump(cv_metrics, f, indent=4)
        
    # 3. Fit final production model on full dataset
    # We will hold out 20% for test set reporting, train on 80%
    X_train, X_test, y_train, y_test = train_test_split(
        X_trans, y, test_size=0.2, stratify=y, random_state=42
    )
    
    final_pos_w = sum(y_train == 0) / sum(y_train == 1)
    logger.info("Training final production XGBoost model on train split...")
    final_model = XGBClassifier(
        n_estimators=150,
        max_depth=4,
        learning_rate=0.08,
        scale_pos_weight=final_pos_w,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        eval_metric="logloss"
    )
    final_model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)
    
    # Save the trained model
    xgb_path = MODELS_DIR / "xgboost_model.joblib"
    logger.info(f"Saving final model to {xgb_path}")
    joblib.dump(final_model, xgb_path)
    
    # 4. Fit shallow Decision Tree and extract Banker-Friendly unscaled rules
    logger.info("Fitting shallow Decision Tree on unscaled features to extract policy rules...")
    dt_model = DecisionTreeClassifier(max_depth=3, class_weight="balanced", random_state=42)
    dt_model.fit(X_train, y_train)
    
    banker_rules = extract_banker_rules(dt_model, feature_names, numerical_cols, scaler)
    
    rules_path = MODELS_DIR / "business_rules.json"
    logger.info(f"Saving derived banker rules to {rules_path}")
    with open(rules_path, "w") as f:
        json.dump(banker_rules, f, indent=4)
        
    # Export Rules as CSV (Requested improvement)
    rules_csv_path = MODELS_DIR / "business_rules.csv"
    logger.info(f"Exporting rules as CSV to {rules_csv_path}")
    rules_df = pd.DataFrame(banker_rules)
    rules_df.to_csv(rules_csv_path, index=False)
    
    # Save train/test split data for evaluate.py
    np.save(MODELS_DIR / "X_test.npy", X_test)
    np.save(MODELS_DIR / "y_test.npy", y_test)
    
    logger.info("Model training pipeline complete.")
    
    return final_model

if __name__ == "__main__":
    train_credit_risk_model()
