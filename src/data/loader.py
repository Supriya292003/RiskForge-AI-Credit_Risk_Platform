import sqlite3
import pandas as pd
from pathlib import Path
import sys

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from src.utils.logger import logger
from src.utils.config import DATA_DIR, DATABASE_PATH

def build_relational_database(df_train, df_bureau, df_prev):
    """
    Creates and populates the SQLite database with the raw relational tables.
    """
    logger.info(f"Connecting to SQLite database at {DATABASE_PATH}")
    conn = sqlite3.connect(DATABASE_PATH)
    
    # Save the raw tables into SQLite
    logger.info("Writing application_train table to SQLite...")
    df_train.to_sql("application_train", conn, if_exists="replace", index=False)
    
    logger.info("Writing bureau table to SQLite...")
    df_bureau.to_sql("bureau", conn, if_exists="replace", index=False)
    
    logger.info("Writing previous_application table to SQLite...")
    df_prev.to_sql("previous_application", conn, if_exists="replace", index=False)
    
    conn.commit()
    conn.close()
    logger.info("SQLite database tables created successfully.")

def load_and_merge_data():
    """
    Loads raw CSVs, performs feature aggregation on bureau and previous application tables,
    joins them with application_train, and creates the SQLite database.
    """
    train_path = DATA_DIR / "application_train.csv"
    bureau_path = DATA_DIR / "bureau.csv"
    prev_path = DATA_DIR / "previous_application.csv"
    
    if not train_path.exists():
        raise FileNotFoundError(f"Missing base dataset application_train.csv at {train_path}. Please run generate_mock_data.py first.")
        
    logger.info(f"Loading raw datasets from {DATA_DIR}...")
    df_train = pd.read_csv(train_path)
    df_bureau = pd.read_csv(bureau_path) if bureau_path.exists() else pd.DataFrame()
    df_prev = pd.read_csv(prev_path) if prev_path.exists() else pd.DataFrame()

    # Create the relational database in SQLite
    build_relational_database(df_train, df_bureau, df_prev)

    # ----------------------------------------------------
    # Feature Engineering / Aggregation for ML Training
    # ----------------------------------------------------
    logger.info("Performing feature engineering and aggregations...")
    
    # Aggregate bureau.csv
    if not df_bureau.empty:
        logger.info("Aggregating bureau.csv features...")
        bureau_agg = df_bureau.groupby("SK_ID_CURR").agg({
            "SK_ID_BUREAU": "count",
            "CREDIT_ACTIVE": lambda x: (x == "Active").sum(),
            "CREDIT_DAY_OVERDUE": "max",
            "AMT_CREDIT_SUM": "sum",
            "AMT_CREDIT_SUM_DEBT": "sum",
            "AMT_CREDIT_SUM_OVERDUE": "sum"
        }).rename(columns={
            "SK_ID_BUREAU": "BUREAU_LOAN_COUNT",
            "CREDIT_ACTIVE": "BUREAU_ACTIVE_LOANS",
            "CREDIT_DAY_OVERDUE": "BUREAU_MAX_OVERDUE_DAYS",
            "AMT_CREDIT_SUM": "BUREAU_TOTAL_CREDIT_SUM",
            "AMT_CREDIT_SUM_DEBT": "BUREAU_TOTAL_DEBT",
            "AMT_CREDIT_SUM_OVERDUE": "BUREAU_TOTAL_OVERDUE"
        }).reset_index()
    else:
        bureau_agg = pd.DataFrame(columns=["SK_ID_CURR", "BUREAU_LOAN_COUNT", "BUREAU_ACTIVE_LOANS", 
                                           "BUREAU_MAX_OVERDUE_DAYS", "BUREAU_TOTAL_CREDIT_SUM", 
                                           "BUREAU_TOTAL_DEBT", "BUREAU_TOTAL_OVERDUE"])

    # Aggregate previous_application.csv
    if not df_prev.empty:
        logger.info("Aggregating previous_application.csv features...")
        prev_agg = df_prev.groupby("SK_ID_CURR").agg({
            "SK_ID_PREV": "count",
            "NAME_CONTRACT_STATUS": lambda x: (x == "Refused").sum(),
            "AMT_APPLICATION": "mean",
            "AMT_CREDIT": "sum"
        }).rename(columns={
            "SK_ID_PREV": "PREV_APP_COUNT",
            "NAME_CONTRACT_STATUS": "PREV_REFUSED_COUNT",
            "AMT_APPLICATION": "PREV_AVG_APP_AMT",
            "AMT_CREDIT": "PREV_TOTAL_CREDIT"
        }).reset_index()
    else:
        prev_agg = pd.DataFrame(columns=["SK_ID_CURR", "PREV_APP_COUNT", "PREV_REFUSED_COUNT", 
                                         "PREV_AVG_APP_AMT", "PREV_TOTAL_CREDIT"])

    # Merge aggregates to application_train
    logger.info("Merging aggregated features into main dataframe...")
    df_merged = df_train.merge(bureau_agg, on="SK_ID_CURR", how="left")
    df_merged = df_merged.merge(prev_agg, on="SK_ID_CURR", how="left")

    # Fill NaNs in engineered features with 0 (since absence of record means 0 previous loans/debt)
    engineered_cols = [
        "BUREAU_LOAN_COUNT", "BUREAU_ACTIVE_LOANS", "BUREAU_MAX_OVERDUE_DAYS",
        "BUREAU_TOTAL_CREDIT_SUM", "BUREAU_TOTAL_DEBT", "BUREAU_TOTAL_OVERDUE",
        "PREV_APP_COUNT", "PREV_REFUSED_COUNT", "PREV_AVG_APP_AMT", "PREV_TOTAL_CREDIT"
    ]
    df_merged[engineered_cols] = df_merged[engineered_cols].fillna(0)

    # Save the combined dataset to SQLite too (highly useful for simple SQL queries on joined data)
    conn = sqlite3.connect(DATABASE_PATH)
    logger.info("Writing joined_client_data table to SQLite...")
    df_merged.to_sql("joined_client_data", conn, if_exists="replace", index=False)
    conn.close()

    logger.info(f"Data loading and aggregation completed successfully. Shape: {df_merged.shape}")
    return df_merged

if __name__ == "__main__":
    df = load_and_merge_data()
    print(df.head(2))
