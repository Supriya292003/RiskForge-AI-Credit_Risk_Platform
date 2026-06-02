# Data Directory

This directory is used to store the dataset files required for the RiskForge AI Credit Risk platform.

## Dataset Information
The platform uses the **Home Credit Default Risk** dataset from Kaggle.
You can download the dataset from: [Kaggle - Home Credit Default Risk](https://www.kaggle.com/c/home-credit-default-risk/data)

### Required CSV Files
To run the preprocessing, model training, and database population scripts, place the following downloaded CSV files in this directory:
- `application_train.csv`
- `bureau.csv`
- `previous_application.csv`

## Git Ignore Rule
These large CSV files (ranging from 160MB to over 400MB) are ignored by Git via `.gitignore` to avoid exceeding GitHub's file size limits (100MB per file).
