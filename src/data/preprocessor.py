import joblib
import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
import sys

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from src.utils.logger import logger
from src.utils.config import MODELS_DIR

# ----------------------------------------------------
# Banker-friendly feature name translations
# ----------------------------------------------------
FEATURE_NAME_MAP = {
    "EXT_SOURCE_1": "External Credit Score 1",
    "EXT_SOURCE_2": "External Credit Score 2",
    "EXT_SOURCE_3": "External Credit Score 3",
    "AMT_INCOME_TOTAL": "Annual Income",
    "AMT_CREDIT": "Requested Credit Amount",
    "AMT_ANNUITY": "Loan Monthly Annuity",
    "AMT_GOODS_PRICE": "Goods Price",
    "DAYS_BIRTH": "Age (Years)",
    "DAYS_EMPLOYED": "Employment Duration (Years)",
    "BUREAU_LOAN_COUNT": "Total Historical Credit Bureau Loans",
    "BUREAU_ACTIVE_LOANS": "Active Bureau Loans",
    "BUREAU_MAX_OVERDUE_DAYS": "Credit Bureau Max Overdue Days",
    "BUREAU_TOTAL_CREDIT_SUM": "Total Bureau Debt Sum",
    "BUREAU_TOTAL_DEBT": "Bureau Active Debt Sum",
    "BUREAU_TOTAL_OVERDUE": "Bureau Overdue Amount",
    "PREV_APP_COUNT": "Previous Loan Applications",
    "PREV_REFUSED_COUNT": "Refused Previous Applications",
    "PREV_AVG_APP_AMT": "Average Previous Approved Amount",
    "PREV_TOTAL_CREDIT": "Total Previous Approved Credit",
    "REGION_RATING_CLIENT": "Client Region Rating"
}

# Categorical column definitions for reference in naming
CATEGORICAL_COLS = [
    "NAME_CONTRACT_TYPE",
    "CODE_GENDER",
    "FLAG_OWN_CAR",
    "FLAG_OWN_REALTY",
    "NAME_INCOME_TYPE",
    "NAME_EDUCATION_TYPE",
    "NAME_FAMILY_STATUS",
    "NAME_HOUSING_TYPE",
    "OCCUPATION_TYPE"
]

def get_banker_name(tech_name: str) -> str:
    """
    Translates a machine learning column name to a banker-friendly description.
    Also handles one-hot encoded variables (e.g. CODE_GENDER_M -> Gender (Male)).
    """
    if tech_name in FEATURE_NAME_MAP:
        return FEATURE_NAME_MAP[tech_name]
        
    # Check one-hot encodings
    for cat_col in CATEGORICAL_COLS:
        if tech_name.startswith(cat_col + "_"):
            val = tech_name[len(cat_col) + 1:]
            pretty_col = cat_col.replace("NAME_", "").replace("FLAG_", "").replace("_TYPE", "").replace("_STATUS", "").title()
            pretty_col = pretty_col.replace("Code_", "").replace("Own_", "Owns ")
            if pretty_col == "Realty":
                pretty_col = "Owns Real Estate"
            elif pretty_col == "Education":
                pretty_col = "Education Level"
            elif pretty_col == "Contract":
                pretty_col = "Contract Type"
            elif pretty_col == "Housing":
                pretty_col = "Housing Type"
            elif pretty_col == "Income":
                pretty_col = "Income Type"
            elif pretty_col == "Occupation":
                pretty_col = "Occupation Type"
            elif pretty_col == "Family":
                pretty_col = "Family Status"
            return f"{pretty_col} ({val})"
            
    # Default fallback formatting
    return tech_name.replace("AMT_", "Amount ").replace("CNT_", "Count ").replace("DAYS_", "").replace("_TOTAL", "").replace("_", " ").title()

# Define columns lists
CATEGORICAL_COLS = [
    "NAME_CONTRACT_TYPE",
    "CODE_GENDER",
    "FLAG_OWN_CAR",
    "FLAG_OWN_REALTY",
    "NAME_INCOME_TYPE",
    "NAME_EDUCATION_TYPE",
    "NAME_FAMILY_STATUS",
    "NAME_HOUSING_TYPE",
    "OCCUPATION_TYPE"
]

NUMERICAL_COLS = [
    "CNT_CHILDREN",
    "AMT_INCOME_TOTAL",
    "AMT_CREDIT",
    "AMT_ANNUITY",
    "AMT_GOODS_PRICE",
    "DAYS_BIRTH",
    "DAYS_EMPLOYED",
    "EXT_SOURCE_1",
    "EXT_SOURCE_2",
    "EXT_SOURCE_3",
    "REGION_RATING_CLIENT",
    # Engineered features
    "BUREAU_LOAN_COUNT",
    "BUREAU_ACTIVE_LOANS",
    "BUREAU_MAX_OVERDUE_DAYS",
    "BUREAU_TOTAL_CREDIT_SUM",
    "BUREAU_TOTAL_DEBT",
    "BUREAU_TOTAL_OVERDUE",
    "PREV_APP_COUNT",
    "PREV_REFUSED_COUNT",
    "PREV_AVG_APP_AMT",
    "PREV_TOTAL_CREDIT"
]

def create_preprocessing_pipeline():
    """
    Creates the Pipeline and ColumnTransformer for preprocessing.
    """
    # Numeric transformer: median imputation + scaling
    numeric_transformer = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler())
    ])

    # Categorical transformer: mode imputation + one-hot encoding
    categorical_transformer = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="constant", fill_value="Unknown")),
        ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False))
    ])

    # Column transformer
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_transformer, NUMERICAL_COLS),
            ("cat", categorical_transformer, CATEGORICAL_COLS)
        ],
        remainder="drop"
    )

    return preprocessor

def fit_transform_data(df, save_pipeline=True):
    """
    Fits and saves the preprocessing pipeline, returning the transformed features and target.
    """
    logger.info("Fitting and transforming data with preprocessing pipeline...")
    
    # Separate features and target
    X = df.drop(columns=["TARGET", "SK_ID_CURR"], errors="ignore").copy()
    y = df["TARGET"] if "TARGET" in df.columns else None

    # Normalize Y/N flags to Yes/No dynamically
    for col in ["FLAG_OWN_CAR", "FLAG_OWN_REALTY"]:
        if col in X.columns:
            X[col] = X[col].map({"Y": "Yes", "N": "No", "Yes": "Yes", "No": "No"}).fillna("No")

    # Check if we have columns we expect
    missing_num = [c for c in NUMERICAL_COLS if c not in X.columns]
    missing_cat = [c for c in CATEGORICAL_COLS if c not in X.columns]
    if missing_num or missing_cat:
        logger.warning(f"Columns missing from training dataframe. Numerical: {missing_num}, Categorical: {missing_cat}")

    preprocessor = create_preprocessing_pipeline()
    X_transformed = preprocessor.fit_transform(X)
    
    # Get feature names after transformation
    num_feature_names = NUMERICAL_COLS
    cat_encoder = preprocessor.named_transformers_["cat"].named_steps["onehot"]
    cat_feature_names = cat_encoder.get_feature_names_out(CATEGORICAL_COLS).tolist()
    feature_names = num_feature_names + cat_feature_names

    if save_pipeline:
        pipeline_path = MODELS_DIR / "preprocessor.joblib"
        # Save both preprocessor and final features list for model validation
        logger.info(f"Saving preprocessor to {pipeline_path}")
        joblib.dump({
            "preprocessor": preprocessor,
            "feature_names": feature_names,
            "numerical_cols": NUMERICAL_COLS,
            "categorical_cols": CATEGORICAL_COLS
        }, pipeline_path)

    logger.info("Preprocessing complete.")
    return X_transformed, y, feature_names

def load_preprocessor():
    """Loads the preprocessor pipeline and feature names."""
    pipeline_path = MODELS_DIR / "preprocessor.joblib"
    if not pipeline_path.exists():
        raise FileNotFoundError(f"Preprocessor pipeline not found at {pipeline_path}. Run train.py first.")
    
    artifacts = joblib.load(pipeline_path)
    return artifacts["preprocessor"], artifacts["feature_names"]

if __name__ == "__main__":
    from src.data.loader import load_and_merge_data
    df = load_and_merge_data()
    X_trans, y, feat_names = fit_transform_data(df)
    print(f"Transformed features shape: {X_trans.shape}")
    print(f"First 5 feature names: {feat_names[:5]}")
