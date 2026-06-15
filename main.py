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

app = FastAPI(title="FootballDB")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
        
    user = db.query(UserModel).filter(UserModel.username == username).first()
    if user is None:
        raise credentials_exception
    return user

@app.post("/register", response_model=Token)
def register(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(UserModel).filter(UserModel.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    hashed_password = get_password_hash(user.password)
    new_user = UserModel(username=user.username, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    
    access_token = create_access_token(data={"sub": new_user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(UserModel).filter(UserModel.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/teams", response_model=list[TeamResponse])
def get_teams(db: Session = Depends(get_db)):
    return db.query(TeamModel).all()

@app.get("/matches", response_model=list[MatchResponse])
def get_matches(db: Session = Depends(get_db)):
    return db.query(MatchModel).all()

@app.get("/standings/{league_code}")
def get_standings(league_code: str):
    url = f"https://api.football-data.org/v4/competitions/{league_code}/standings"
    headers = {"X-Auth-Token": SPORTS_API_KEY}
    
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise HTTPException(status_code=400, detail=f"Failed to fetch standings for {league_code}")
        
    data = response.json()
    
    try:
        standings_table = data["standings"][0]["table"]
        clean_standings = []
        for row in standings_table:
            clean_standings.append({
                "Rank": row["position"],
                "Club": row["team"]["name"],
                "MP": row["playedGames"],
                "W": row["won"],
                "D": row["draw"],
                "L": row["lost"],
                "GF": row["goalsFor"],
                "GA": row["goalsAgainst"],
                "GD": row["goalDifference"],
                "Pts": row["points"]
            })
        return clean_standings
    except (KeyError, IndexError):
        raise HTTPException(status_code=404, detail="Standings data not available for this league")

@app.post("/teams", response_model=TeamResponse)
def create_team(team: TeamCreate, db: Session = Depends(get_db), current_user: UserModel = Depends(get_current_user)):
    db_team = db.query(TeamModel).filter(or_(TeamModel.name == team.name, TeamModel.code == team.code)).first()
    if db_team:
        raise HTTPException(status_code=400, detail="Team already registered")
    new_team = TeamModel(name=team.name, code=team.code)
    db.add(new_team)
    db.commit()
    db.refresh(new_team)
    return new_team

@app.post("/teams/{team_id}/players", response_model=PlayerResponse)
def create_player(team_id: int, player: PlayerCreate, db: Session = Depends(get_db), current_user: UserModel = Depends(get_current_user)):
    db_team = db.query(TeamModel).filter(TeamModel.id == team_id).first()
    if not db_team:
        raise HTTPException(status_code=404, detail="Team not found")
    new_player = PlayerModel(name=player.name, position=player.position, team_id=team_id)
    db.add(new_player)
    db.commit()
    db.refresh(new_player)
    return new_player

@app.post("/matches", response_model=MatchResponse)
def create_match(match: MatchCreate, db: Session = Depends(get_db), current_user: UserModel = Depends(get_current_user)):
    if match.home_team_id == match.away_team_id:
        raise HTTPException(status_code=400, detail="A team cannot play against itself")
    
    home = db.query(TeamModel).filter(TeamModel.id == match.home_team_id).first()
    away = db.query(TeamModel).filter(TeamModel.id == match.away_team_id).first()
    
    if not home or not away:
        raise HTTPException(status_code=404, detail="One or both teams not found")
        
    new_match = MatchModel(
        home_team_id=match.home_team_id,
        away_team_id=match.away_team_id,
        home_score=match.home_score,
        away_score=match.away_score
    )
    db.add(new_match)
    db.commit()
    db.refresh(new_match)
    return new_match

@app.delete("/matches/{match_id}")
def delete_match(match_id: int, db: Session = Depends(get_db), current_user: UserModel = Depends(get_current_user)):
    match = db.query(MatchModel).filter(MatchModel.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    
    db.delete(match)
    db.commit()
    return {"message": f"Match {match_id} successfully deleted"}

@app.post("/sync/matches")
def sync_external_matches(league_code: str = "WC", db: Session = Depends(get_db), current_user: UserModel = Depends(get_current_user)):
    url = f"https://api.football-data.org/v4/competitions/{league_code}/matches"
    headers = {"X-Auth-Token": SPORTS_API_KEY}
    
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise HTTPException(status_code=400, detail=f"Failed to fetch data for {league_code}. Check your API key or league code.")
        
    data = response.json()
    matches_data = data.get("matches", [])
    
    added_count = 0
    
    for match in matches_data:
        if match.get("status") != "FINISHED":
            continue
            
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
        
        existing_match = db.query(MatchModel).filter(
            MatchModel.home_team_id == home_team.id,
            MatchModel.away_team_id == away_team.id
        ).first()
        
        if not existing_match:
            new_match = MatchModel(
                home_team_id=home_team.id, away_team_id=away_team.id,
                home_score=home_score, away_score=away_score
            )
            db.add(new_match)
            db.commit()
            added_count += 1
            
    return {"message": f"Successfully synced {added_count} finished {league_code} matches!"}


@app.post("/sync/players")
def sync_external_players(league_code: str = "WC", db: Session = Depends(get_db), current_user: UserModel = Depends(get_current_user)):
    url = f"https://api.football-data.org/v4/competitions/{league_code}/teams"
    headers = {"X-Auth-Token": SPORTS_API_KEY}
    
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise HTTPException(status_code=400, detail=f"Failed to fetch teams. Code: {response.status_code}")
        
    data = response.json()
    teams_data = data.get("teams", [])
    added_players = 0
    
    for team_data in teams_data:
        team_name = team_data["name"]
        team_code = team_data.get("tla", team_name[:3].upper())
        
        team = db.query(TeamModel).filter(or_(TeamModel.name == team_name, TeamModel.code == team_code)).first()
        if not team:
            team = TeamModel(name=team_name, code=team_code)
            db.add(team)
            db.commit()
            db.refresh(team)
            
        squad = team_data.get("squad", [])
        for player in squad:
            player_name = player.get("name")
            player_position = player.get("position", "Unknown")
            if not player_name: 
                continue
            
            existing_player = db.query(PlayerModel).filter(
                PlayerModel.name == player_name, PlayerModel.team_id == team.id
            ).first()
            
            if not existing_player:
                new_player = PlayerModel(name=player_name, position=player_position, team_id=team.id)
                db.add(new_player)
                added_players += 1
        
        db.commit() 
        
    return {"message": f"Successfully synced {added_players} players for {league_code}!"}