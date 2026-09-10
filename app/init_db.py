from app.database import Base, engine
from app.memory.model import Memory

def main():
    Base.metadata.create_all(bind=engine)
    print("Database I.R.I.S. inizializzato.")


if __name__ == "__main__":
    main()