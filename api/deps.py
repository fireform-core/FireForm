from api.db.database import get_session

def get_db():
    yield from get_session()