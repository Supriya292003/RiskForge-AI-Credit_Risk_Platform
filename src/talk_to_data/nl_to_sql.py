import os
import re
import google.generativeai as genai
import pandas as pd
from pathlib import Path
import sys

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from src.utils.logger import logger
from src.utils.config import GEMINI_API_KEY
from src.talk_to_data.prompt_templates import SQL_GENERATION_PROMPT, RESPONSE_SUMMARIZATION_PROMPT
from src.talk_to_data.query_runner import run_sqlite_query

def extract_sql_from_text(text: str) -> str:
    """
    Extracts the SQL query string from inside markdown code blocks.
    """
    # Look for ```sql ... ```
    sql_match = re.search(r"```sql(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if sql_match:
        return sql_match.group(1).strip()
    
    # Fallback to general code blocks ``` ... ```
    generic_match = re.search(r"```(.*?)```", text, re.DOTALL)
    if generic_match:
        return generic_match.group(1).strip()
        
    return text.strip()

class SQLAgent:
    """
    Agent that converts Natural Language to SQL, executes it against SQLite,
    and returns a summarized business response using Gemini.
    """
    def __init__(self):
        if not GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY not found in environment. SQL Chatbot will run in offline mock mode.")
            self.offline_mode = True
        else:
            genai.configure(api_key=GEMINI_API_KEY)
            # Use gemini-1.5-flash as it is fast, cheap, and excellent for code/text generation
            self.model = genai.GenerativeModel('gemini-3.5-flash')
            self.offline_mode = False
            logger.info("SQL Agent initialized successfully using Gemini API.")

    def generate_sql(self, question: str, previous_error: str = None, failed_sql: str = None) -> str:
        """
        Sends user question and schema info to Gemini, returning the generated SQL query.
        Implements self-correction prompt if a previous query failed.
        """
        if self.offline_mode:
            # Simple keyword matching for offline fallback mode
            clean_q = question.lower()
            if "how many customers defaulted" in clean_q or "count" in clean_q and "default" in clean_q:
                return "SELECT COUNT(*) AS total_defaults FROM application_train WHERE TARGET = 1;"
            elif "average income" in clean_q:
                return "SELECT AVG(AMT_INCOME_TOTAL) AS average_income FROM application_train WHERE TARGET = 1;"
            elif "occupation" in clean_q:
                return "SELECT OCCUPATION_TYPE, COUNT(*) AS count, SUM(TARGET) AS defaults FROM application_train WHERE OCCUPATION_TYPE IS NOT NULL GROUP BY OCCUPATION_TYPE ORDER BY defaults DESC LIMIT 5;"
            else:
                return "SELECT * FROM application_train LIMIT 5;"

        prompt = SQL_GENERATION_PROMPT.format(question=question)
        
        if previous_error and failed_sql:
            # Self-correction prompt override
            prompt += f"\n\nCRITICAL: The previous SQL query you generated was:\n```sql\n{failed_sql}\n```\nAnd it failed with the following SQLite error: '{previous_error}'\nPlease correct the SQL query to fix this error. Ensure valid SQLite syntax."

        response = self.model.generate_content(prompt, request_options={"timeout": 15.0})
        sql_query = extract_sql_from_text(response.text)
        
        # Clean trailing semicolon inside code block if any
        sql_query = sql_query.strip().rstrip(";")
        return sql_query + ";"

    def summarize_results(self, question: str, sql_query: str, df_results: pd.DataFrame) -> str:
        """
        Uses Gemini to write a natural language business summary of the database results.
        """
        if self.offline_mode:
            try:
                table_str = df_results.to_markdown(index=False)
            except Exception:
                table_str = df_results.to_string(index=False)
            return f"**[OFFLINE MODE]** Verified query execution: `{sql_query}`. Returned {len(df_results)} rows. Data sample:\n{table_str}"

        # Convert dataframe to a markdown table or string representation
        try:
            results_str = df_results.to_markdown(index=False) if not df_results.empty else "No records found."
        except Exception:
            results_str = df_results.to_string(index=False) if not df_results.empty else "No records found."
        
        prompt = RESPONSE_SUMMARIZATION_PROMPT.format(
            question=question,
            sql_query=sql_query,
            sql_results=results_str
        )
        
        response = self.model.generate_content(prompt, request_options={"timeout": 15.0})
        return response.text.strip()

    def ask(self, question: str) -> dict:
        """
        Main entrypoint: Takes an NL question, generates the SQL, runs it,
        performs self-correction if syntax fails, and returns the response.
        """
        logger.info(f"Processing question: '{question}'")
        
        # Save original offline mode state
        original_offline_mode = self.offline_mode
        
        max_retries = 2
        retry_count = 0
        error_msg = None
        sql_query = None
        df_results = pd.DataFrame()
        
        try:
            while retry_count <= max_retries:
                try:
                    sql_query = self.generate_sql(question, previous_error=error_msg, failed_sql=sql_query)
                except Exception as api_err:
                    logger.warning(f"Gemini SQL generation error: {api_err}. Falling back to offline mock generation.")
                    self.offline_mode = True
                    sql_query = self.generate_sql(question)
                    
                # Execute
                df_results, error_msg = run_sqlite_query(sql_query)
                
                if error_msg is None:
                    # Success!
                    logger.info("SQL query executed successfully.")
                    break
                    
                logger.warning(f"Query failed: {sql_query}. Error: {error_msg}. Retrying self-correction...")
                retry_count += 1
                
            if error_msg:
                # Failed after all retries
                self.offline_mode = original_offline_mode
                return {
                    "question": question,
                    "sql_query": sql_query,
                    "error": error_msg,
                    "success": False,
                    "response": f"Sorry, I generated a SQL query but encountered an error: `{error_msg}`"
                }
                
            # Success, now summarize
            try:
                summary_response = self.summarize_results(question, sql_query, df_results)
            except Exception as summary_err:
                logger.warning(f"Gemini response summarization error: {summary_err}. Falling back to offline summary.")
                self.offline_mode = True
                summary_response = self.summarize_results(question, sql_query, df_results)
                
            # Restore original state
            self.offline_mode = original_offline_mode
            
            return {
                "question": question,
                "sql_query": sql_query,
                "success": True,
                "results_count": len(df_results),
                "results_table": df_results.to_dict(orient="records"),
                "response": summary_response
            }
        except Exception as e:
            logger.error(f"Fatal error in SQL Agent ask(): {e}")
            self.offline_mode = original_offline_mode
            return {
                "question": question,
                "sql_query": "SELECT COUNT(*) FROM application_train;",
                "success": False,
                "response": f"An unexpected error occurred in the SQL chatbot: {e}"
            }

if __name__ == "__main__":
    agent = SQLAgent()
    
    # Test questions
    test_q = "How many customers defaulted?"
    result = agent.ask(test_q)
    print(f"Q: {test_q}")
    print(f"SQL: {result['sql_query']}")
    print(f"A: {result['response']}\n")
    
    test_q_2 = "What is the average income of high risk applicants?"
    result_2 = agent.ask(test_q_2)
    print(f"Q: {test_q_2}")
    print(f"SQL: {result_2['sql_query']}")
    print(f"A: {result_2['response']}")
