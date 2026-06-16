from main import engine, Base

Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)
print("Database successfully wiped and rebuilt with new columns")