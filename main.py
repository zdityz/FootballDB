import os
import requests
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, ForeignKey, create_engine, or_
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from passlib.context import CryptContext
import jwt
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler

load_dotenv()
SPORTS_API_KEY = os.getenv("SPORTS_API_KEY")

DATABASE_URL = "postgresql://localhost/analytics"
SECRET_KEY = "super_secret_key_change_this_in_production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

class UserModel(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)

class TeamModel(Base):
    __tablename__ = "teams"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    code = Column(String, unique=True, index=True)
    crest_url = Column(String, nullable=True)
    manager = Column(String, nullable=True)
    players = relationship("PlayerModel", back_populates="team")

class PlayerModel(Base):
    __tablename__ = "players"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    position = Column(String)
    team_id = Column(Integer, ForeignKey("teams.id"))
    team = relationship("TeamModel", back_populates="players")

class MatchModel(Base):
    __tablename__ = "matches"
    id = Column(Integer, primary_key=True, index=True)
    home_team_id = Column(Integer, ForeignKey("teams.id"))
    away_team_id = Column(Integer, ForeignKey("teams.id"))
    home_score = Column(Integer)
    away_score = Column(Integer)

Base.metadata.create_all(bind=engine)

class UserCreate(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class PlayerCreate(BaseModel):
    name: str
    position: str

class PlayerResponse(BaseModel):
    id: int
    name: str
    position: str
    team_id: int
    class Config:
        from_attributes = True

class TeamCreate(BaseModel):
    name: str
    code: str

class TeamResponse(BaseModel):
    id: int
    name: str
    code: str
    crest_url: str | None = None
    manager: str | None = None
    players: list[PlayerResponse] = []
    class Config:
        from_attributes = True

class MatchCreate(BaseModel):
    home_team_id: int
    away_team_id: int
    home_score: int
    away_score: int

class MatchResponse(BaseModel):
    id: int
    home_team_id: int
    away_team_id: int
    home_score: int
    away_score: int
    class Config:
        from_attributes = True

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None: raise credentials_exception
    except jwt.PyJWTError: raise credentials_exception
    user = db.query(UserModel).filter(UserModel.username == username).first()
    if user is None: raise credentials_exception
    return user

def process_match_sync(league_code: str, db: Session):
    url = f"https://api.football-data.org/v4/competitions/{league_code}/matches"
    headers = {"X-Auth-Token": SPORTS_API_KEY}
    response = requests.get(url, headers=headers)
    if response.status_code != 200: return 0
    matches_data = response.json().get("matches", [])
    added_count = 0
    for match in matches_data:
        if match.get("status") != "FINISHED": continue
        home_name = match["homeTeam"]["name"]
        home_code = match["homeTeam"].get("tla", home_name[:3].upper())
        away_name = match["awayTeam"]["name"]
        away_code = match["awayTeam"].get("tla", away_name[:3].upper())
        
        home_team = db.query(TeamModel).filter(or_(TeamModel.name == home_name, TeamModel.code == home_code)).first()
        if not home_team:
            home_team = TeamModel(name=home_name, code=home_code)
            db.add(home_team)
            db.commit()
            db.refresh(home_team)
            
        away_team = db.query(TeamModel).filter(or_(TeamModel.name == away_name, TeamModel.code == away_code)).first()
        if not away_team:
            away_team = TeamModel(name=away_name, code=away_code)
            db.add(away_team)
            db.commit()
            db.refresh(away_team)
            
        home_score = match["score"]["fullTime"]["home"]
        away_score = match["score"]["fullTime"]["away"]
        
        existing_match = db.query(MatchModel).filter(MatchModel.home_team_id == home_team.id, MatchModel.away_team_id == away_team.id).first()
        if not existing_match:
            new_match = MatchModel(home_team_id=home_team.id, away_team_id=away_team.id, home_score=home_score, away_score=away_score)
            db.add(new_match)
            db.commit()
            added_count += 1
    return added_count

def automated_nightly_sync():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🤖 Waking up background worker...")
    db = SessionLocal()
    try:
        leagues = ["PL", "PD", "CL"] 
        for league in leagues:
            added = process_match_sync(league, db)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Synced {league}: {added} new matches.")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 💤 Sync complete. Back to sleep.\n")
    finally:
        db.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = BackgroundScheduler()
    scheduler.add_job(automated_nightly_sync, 'cron', hour=0, minute=0)
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(title="FootballDB", lifespan=lifespan)

@app.post("/register", response_model=Token)
def register(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(UserModel).filter(UserModel.username == user.username).first()
    if db_user: raise HTTPException(status_code=400, detail="Username already registered")
    new_user = UserModel(username=user.username, hashed_password=get_password_hash(user.password))
    db.add(new_user)
    db.commit()
    return {"access_token": create_access_token(data={"sub": new_user.username}), "token_type": "bearer"}

@app.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(UserModel).filter(UserModel.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    return {"access_token": create_access_token(data={"sub": user.username}), "token_type": "bearer"}

@app.get("/teams", response_model=list[TeamResponse])
def get_teams(db: Session = Depends(get_db)):
    return db.query(TeamModel).all()

@app.get("/matches", response_model=list[MatchResponse])
def get_matches(db: Session = Depends(get_db)):
    return db.query(MatchModel).all()

@app.get("/standings/{league_code}")
def get_standings(league_code: str):
    url = f"https://api.football-data.org/v4/competitions/{league_code}/standings"
    res = requests.get(url, headers={"X-Auth-Token": SPORTS_API_KEY})
    if res.status_code != 200: raise HTTPException(status_code=400, detail="Failed to fetch standings")
    try:
        standings_table = res.json()["standings"][0]["table"]
        clean_standings = []
        for row in standings_table:
            clean_standings.append({
                "Rank": row["position"], "Club": row["team"]["name"], "MP": row["playedGames"],
                "W": row["won"], "D": row["draw"], "L": row["lost"],
                "GF": row["goalsFor"], "GA": row["goalsAgainst"], "GD": row["goalDifference"], "Pts": row["points"]
            })
        return clean_standings
    except: raise HTTPException(status_code=404, detail="Data not available")

@app.delete("/matches/{match_id}")
def delete_match(match_id: int, db: Session = Depends(get_db), current_user: UserModel = Depends(get_current_user)):
    match = db.query(MatchModel).filter(MatchModel.id == match_id).first()
    if not match: raise HTTPException(status_code=404, detail="Match not found")
    db.delete(match)
    db.commit()
    return {"message": "Deleted"}

@app.post("/sync/matches")
def sync_external_matches(league_code: str = "WC", db: Session = Depends(get_db), current_user: UserModel = Depends(get_current_user)):
    added_count = process_match_sync(league_code, db)
    return {"message": f"Successfully synced {added_count} finished {league_code} matches!"}

@app.post("/sync/players")
def sync_external_players(league_code: str = "WC", db: Session = Depends(get_db), current_user: UserModel = Depends(get_current_user)):
    url = f"https://api.football-data.org/v4/competitions/{league_code}/teams"
    res = requests.get(url, headers={"X-Auth-Token": SPORTS_API_KEY})
    if res.status_code != 200: raise HTTPException(status_code=400, detail="Failed to fetch teams")
    teams_data = res.json().get("teams", [])
    added_players = 0
    for team_data in teams_data:
        team_name, team_code = team_data["name"], team_data.get("tla", team_data["name"][:3].upper())
        
        crest_url = team_data.get("crest")
        coach_data = team_data.get("coach")
        manager_name = coach_data.get("name") if coach_data else "Unknown"
        
        team = db.query(TeamModel).filter(or_(TeamModel.name == team_name, TeamModel.code == team_code)).first()
        if not team:
            team = TeamModel(name=team_name, code=team_code, crest_url=crest_url, manager=manager_name)
            db.add(team)
            db.commit()
            db.refresh(team)
        else:
            team.crest_url = crest_url
            team.manager = manager_name
            db.commit()

        for player in team_data.get("squad", []):
            if not player.get("name"): continue
            if not db.query(PlayerModel).filter(PlayerModel.name == player["name"], PlayerModel.team_id == team.id).first():
                db.add(PlayerModel(name=player["name"], position=player.get("position", "Unknown"), team_id=team.id))
                added_players += 1
        db.commit() 
    return {"message": f"Successfully synced {added_players} players and club profiles for {league_code}!"}

@app.get("/live")
def get_live_matches():
    url = "https://api.football-data.org/v4/matches"
    headers = {"X-Auth-Token": SPORTS_API_KEY}
    
    res = requests.get(url, headers=headers)
    if res.status_code != 200: 
        raise HTTPException(status_code=400, detail="Failed to fetch live matches")
        
    matches = res.json().get("matches", [])
    live_games = [m for m in matches if m["status"] in ["IN_PLAY", "PAUSED"]]
    
    clean_live = []
    for m in live_games:
        score_data = m.get("score", {}).get("fullTime", {})
        home_score = score_data.get("home") if score_data.get("home") is not None else 0
        away_score = score_data.get("away") if score_data.get("away") is not None else 0
        
        clean_live.append({
            "league": m["competition"]["name"],
            "home_team": m["homeTeam"]["name"],
            "away_team": m["awayTeam"]["name"],
            "home_score": home_score,
            "away_score": away_score,
            "status": m["status"]
        })
        
    return clean_live