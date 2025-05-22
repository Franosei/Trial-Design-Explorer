# utils/api_client.py
import requests
from config import BASE_API_URL, DEFAULT_PAGE_SIZE

def fetch_trials_by_condition(condition, limit=DEFAULT_PAGE_SIZE):
    try:
        response = requests.get(BASE_API_URL, params={
            "query.term": condition,
            "pageSize": limit
        })
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"API error: {e}")
        return None
