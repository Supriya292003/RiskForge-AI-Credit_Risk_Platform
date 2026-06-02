import os
import sys
import numpy as np
import pandas as pd
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from src.utils.logger import logger
from src.utils.config import DATA_DIR

def generate_mock_datasets(num_clients=3000, overwrite=False):
    """
    Generates synthetic datasets mimicking the Home Credit Default Risk schema.
    Only runs if data/application_train.csv is missing or overwrite=True.
    """
    train_path = DATA_DIR / "application_train.csv"
    bureau_path = DATA_DIR / "bureau.csv"
    prev_path = DATA_DIR / "previous_application.csv"
    
    if train_path.exists() and not overwrite:
        logger.info("Found existing datasets in data/ folder. Skipping mock data generation.")
        return

    logger.info("Generating realistic mock datasets...")
    np.random.seed(42)

    # ----------------------------------------------------
    # 1. Generate application_train.csv
    # ----------------------------------------------------
    logger.info(f"Generating {num_clients} client profiles in application_train.csv")
    client_ids = np.arange(100001, 100001 + num_clients)
    
    # Demographic & basic features
    genders = np.random.choice(["F", "M"], size=num_clients, p=[0.65, 0.35])
    own_car = np.random.choice(["No", "Yes"], size=num_clients, p=[0.68, 0.32])
    own_realty = np.random.choice(["Yes", "No"], size=num_clients, p=[0.70, 0.30])
    cnt_children = np.random.choice([0, 1, 2, 3, 4], size=num_clients, p=[0.70, 0.18, 0.09, 0.02, 0.01])
    
    # Financials (log-normal distribution for incomes and loans)
    income_total = np.random.lognormal(mean=11.8, sigma=0.5, size=num_clients).round(2)
    # Ensure income is at least 20k
    income_total = np.maximum(income_total, 20000.0)
    
    credit_amount = (income_total * np.random.uniform(1.5, 5.0, size=num_clients)).round(2)
    annuity = (credit_amount * np.random.uniform(0.04, 0.08, size=num_clients)).round(2)
    goods_price = (credit_amount * np.random.uniform(0.85, 1.0, size=num_clients)).round(2)
    
    income_type = np.random.choice(
        ["Working", "Commercial associate", "State servant", "Pensioner"],
        size=num_clients,
        p=[0.53, 0.23, 0.08, 0.16]
    )
    
    education_type = np.random.choice(
        ["Secondary / secondary special", "Higher education", "Incomplete higher", "Lower secondary"],
        size=num_clients,
        p=[0.72, 0.23, 0.04, 0.01]
    )
    
    family_status = np.random.choice(
        ["Married", "Single / not married", "Civil marriage", "Separated", "Widow"],
        size=num_clients,
        p=[0.64, 0.15, 0.10, 0.07, 0.04]
    )
    
    housing_type = np.random.choice(
        ["House / apartment", "With parents", "Municipal apartment", "Rented apartment", "Office apartment"],
        size=num_clients,
        p=[0.88, 0.05, 0.04, 0.02, 0.01]
    )
    
    # Age (in days, negative)
    age_years = np.random.uniform(21, 68, size=num_clients)
    days_birth = (-age_years * 365.25).astype(int)
    
    # Employment (in days, negative). For pensioners, DAYS_EMPLOYED = 365243 (Kaggle dataset specific)
    days_employed = []
    for inc_t, db in zip(income_type, days_birth):
        if inc_t == "Pensioner":
            days_employed.append(365243)
        else:
            max_work_years = min(age_years[len(days_employed)] - 18, 45)
            work_years = np.random.beta(a=2, b=5) * max_work_years
            days_employed.append(int(-work_years * 365.25))
    days_employed = np.array(days_employed)
    
    occupation_types = ["Laborers", "Sales staff", "Core staff", "Managers", "Drivers", 
                        "High skill technical staff", "Accountants", "Medicine staff", 
                        "Security staff", "Cooking staff"]
    occupation_p = [0.35, 0.18, 0.15, 0.11, 0.08, 0.05, 0.04, 0.02, 0.01, 0.01]
    occupation = []
    for inc_t in income_type:
        if inc_t == "Pensioner":
            occupation.append(np.nan)
        else:
            occupation.append(np.random.choice(occupation_types, p=occupation_p))
    occupation = np.array(occupation, dtype=object)

    # Normalized External Source scores (0 to 1, higher is better credit score)
    ext_source_1 = np.random.beta(a=5, b=5, size=num_clients)
    ext_source_2 = np.random.beta(a=6, b=5, size=num_clients)
    ext_source_3 = np.random.beta(a=5, b=6, size=num_clients)
    
    # Introduce missingness (realistic)
    ext_source_1[np.random.choice([True, False], size=num_clients, p=[0.55, 0.45])] = np.nan
    ext_source_3[np.random.choice([True, False], size=num_clients, p=[0.20, 0.80])] = np.nan
    
    # Construct predictive target probability (logistic function)
    # Higher risk drivers: Young age, low income, high debt ratio (annuity/income), low EXT_SOURCE scores, male
    score = (
        -1.5 
        + 0.00003 * days_birth  # Younger (-days_birth is smaller) means higher risk
        - 1.6 * ext_source_2
        - 1.0 * np.nan_to_num(ext_source_3, nan=0.5)
        - 0.6 * np.nan_to_num(ext_source_1, nan=0.5)
        + 0.5 * (annuity / income_total)
        + 0.15 * (genders == "M")
    )
    
    # Map score to target probability
    prob = 1 / (1 + np.exp(-score))
    
    # Introduce realistic noise to the probability before thresholding
    # This creates overlap between classes, producing a realistic ROC-AUC (0.72 - 0.76)
    noise = np.random.normal(0, 0.22, size=num_clients)
    noisy_prob = prob + noise
    
    # Cutoff at 92.0 percentile to maintain an exact ~8.0% default rate
    target = (noisy_prob > np.percentile(noisy_prob, 92.0)).astype(int)


    df_train = pd.DataFrame({
        "SK_ID_CURR": client_ids,
        "TARGET": target,
        "NAME_CONTRACT_TYPE": np.random.choice(["Cash loans", "Revolving loans"], size=num_clients, p=[0.90, 0.10]),
        "CODE_GENDER": genders,
        "FLAG_OWN_CAR": own_car,
        "FLAG_OWN_REALTY": own_realty,
        "CNT_CHILDREN": cnt_children,
        "AMT_INCOME_TOTAL": income_total,
        "AMT_CREDIT": credit_amount,
        "AMT_ANNUITY": annuity,
        "AMT_GOODS_PRICE": goods_price,
        "NAME_INCOME_TYPE": income_type,
        "NAME_EDUCATION_TYPE": education_type,
        "NAME_FAMILY_STATUS": family_status,
        "NAME_HOUSING_TYPE": housing_type,
        "DAYS_BIRTH": days_birth,
        "DAYS_EMPLOYED": days_employed,
        "OCCUPATION_TYPE": occupation,
        "EXT_SOURCE_1": ext_source_1,
        "EXT_SOURCE_2": ext_source_2,
        "EXT_SOURCE_3": ext_source_3,
        "REGION_RATING_CLIENT": np.random.choice([1, 2, 3], size=num_clients, p=[0.10, 0.75, 0.15]),
    })

    # Save application_train
    df_train.to_csv(train_path, index=False)
    logger.info(f"Saved application_train.csv to {train_path} (Target rate: {df_train['TARGET'].mean()*100:.2f}%)")

    # ----------------------------------------------------
    # 2. Generate bureau.csv
    # ----------------------------------------------------
    logger.info("Generating credit history records in bureau.csv")
    bureau_records = []
    bureau_id = 5000001
    
    # Give 80% of clients some bureau records
    bureau_clients = np.random.choice(client_ids, size=int(num_clients * 0.8), replace=False)
    for cid in bureau_clients:
        num_records = np.random.randint(1, 6)
        is_default_client = df_train.loc[df_train["SK_ID_CURR"] == cid, "TARGET"].values[0] == 1
        
        for _ in range(num_records):
            days_credit = -np.random.randint(30, 2000)
            active = np.random.choice(["Closed", "Active"], p=[0.7, 0.3])
            
            # Default clients are more likely to have overdue credits
            if is_default_client:
                overdue = np.random.choice([0.0, 5000.0, 15000.0], p=[0.6, 0.3, 0.1])
                day_overdue = int(overdue / 100)
            else:
                overdue = 0.0
                day_overdue = 0
                
            credit_sum = round(np.random.lognormal(mean=11.0, sigma=0.8), 2)
            credit_debt = (credit_sum * np.random.uniform(0.0, 0.8)) if active == "Active" else 0.0
            
            bureau_records.append({
                "SK_ID_CURR": cid,
                "SK_ID_BUREAU": bureau_id,
                "CREDIT_ACTIVE": active,
                "DAYS_CREDIT": days_credit,
                "CREDIT_DAY_OVERDUE": day_overdue,
                "AMT_CREDIT_SUM": credit_sum,
                "AMT_CREDIT_SUM_DEBT": round(credit_debt, 2),
                "AMT_CREDIT_SUM_OVERDUE": overdue,
                "CREDIT_TYPE": np.random.choice(["Consumer credit", "Credit card", "Car loan"], p=[0.75, 0.20, 0.05])
            })
            bureau_id += 1
            
    df_bureau = pd.DataFrame(bureau_records)
    df_bureau.to_csv(bureau_path, index=False)
    logger.info(f"Saved {len(df_bureau)} records in bureau.csv to {bureau_path}")

    # ----------------------------------------------------
    # 3. Generate previous_application.csv
    # ----------------------------------------------------
    logger.info("Generating previous application records in previous_application.csv")
    prev_records = []
    prev_id = 2000001
    
    # Give 75% of clients some previous applications
    prev_clients = np.random.choice(client_ids, size=int(num_clients * 0.75), replace=False)
    for cid in prev_clients:
        num_apps = np.random.randint(1, 4)
        is_default_client = df_train.loc[df_train["SK_ID_CURR"] == cid, "TARGET"].values[0] == 1
        
        for _ in range(num_apps):
            # Default clients are more likely to have Refused previous applications
            if is_default_client:
                status = np.random.choice(["Approved", "Refused", "Canceled"], p=[0.5, 0.4, 0.1])
            else:
                status = np.random.choice(["Approved", "Refused", "Canceled"], p=[0.8, 0.1, 0.1])
                
            app_amt = round(np.random.lognormal(mean=11.3, sigma=0.6), 2)
            cred_amt = app_amt if status == "Approved" else 0.0
            annuity_prev = round(cred_amt * np.random.uniform(0.05, 0.1), 2) if status == "Approved" else 0.0
            
            prev_records.append({
                "SK_ID_CURR": cid,
                "SK_ID_PREV": prev_id,
                "NAME_CONTRACT_TYPE": np.random.choice(["Consumer loans", "Cash loans"], p=[0.7, 0.3]),
                "AMT_APPLICATION": app_amt,
                "AMT_CREDIT": cred_amt,
                "AMT_ANNUITY": annuity_prev,
                "NAME_CONTRACT_STATUS": status,
                "DAYS_DECISION": -np.random.randint(15, 1500),
                "CODE_REJECT_REASON": "LIMIT" if status == "Refused" else "XAP"
            })
            prev_id += 1
            
    df_prev = pd.DataFrame(prev_records)
    df_prev.to_csv(prev_path, index=False)
    logger.info(f"Saved {len(df_prev)} records in previous_application.csv to {prev_path}")
    logger.info("Mock data generation successfully completed!")

if __name__ == "__main__":
    generate_mock_datasets(overwrite=True)
