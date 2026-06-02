import sqlite3
import pandas as pd
import re
from pathlib import Path
import sys

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from src.utils.logger import logger
from src.utils.config import DATABASE_PATH

def validate_sql_query(query: str) -> bool:
    """
    Validates that a SQL query is SELECT-only and does not contain destructive operations.
    """
    # Clean whitespace and convert to upper case
    clean_query = re.sub(r'\s+', ' ', query).strip().upper()
    
    # Must start with SELECT
    if not clean_query.startswith("SELECT") and not clean_query.startswith("WITH"):
        logger.warning(f"SQL validation failed: Query does not start with SELECT or WITH. Query: {query}")
        return False
        
    # Check for forbidden keywords (SQL injection/modification)
    forbidden_keywords = [
        r"\bINSERT\b", r"\bUPDATE\b", r"\bDELETE\b", r"\bDROP\b", 
        r"\bALTER\b", r"\bCREATE\b", r"\bREPLACE\b", r"\bTRUNCATE\b", 
        r"\bRENAME\b", r"\bPRAGMA\b", r"\bATTACH\b", r"\bDETACH\b"
    ]
    
    for keyword in forbidden_keywords:
        if re.search(keyword, clean_query):
            logger.warning(f"SQL validation failed: Forbidden keyword '{keyword}' detected in query: {query}")
            return False
            
    return True

def run_sqlite_query(query: str) -> tuple[pd.DataFrame, str | None]:
    """
    Executes a SELECT SQL query against the SQLite credit risk database.
    Returns: (results_df, error_message)
    """
    if not DATABASE_PATH.exists():
        return pd.DataFrame(), f"Database file not found at {DATABASE_PATH}. Run loader.py first."
        
    # Validate the query
    if not validate_sql_query(query):
        return pd.DataFrame(), "Access Denied: Only read-only SELECT queries are allowed."
        
    conn = None
    try:
        logger.info(f"Running SQL query: {query}")
        conn = sqlite3.connect(DATABASE_PATH)
        df = pd.read_sql_query(query, conn)
        return df, None
    except Exception as e:
        error_msg = str(e)
        logger.error(f"SQL Execution Error: {error_msg}")
        return pd.DataFrame(), error_msg
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    # Test execution
    test_query = "SELECT COUNT(*) AS total_clients, SUM(TARGET) as default_clients FROM application_train;"
    df, err = run_sqlite_query(test_query)
    if err:
        print(f"Error: {err}")
    else:
        print(df)
        
    # Test forbidden query
    bad_query = "DROP TABLE application_train;"
    df_bad, err_bad = run_sqlite_query(bad_query)
    print(f"Forbidden test result: {err_bad}")
