from fastapi import APIRouter
from src.incident_similarity import IncidentSimilarity

router = APIRouter()

similarity_engine = IncidentSimilarity()


@router.get("/similar-incidents")
def get_similar_incidents(query: str, top_k: int = 3):
    results = similarity_engine.search(query, top_k)
    return {
        "query": query,
        "results": results
    }