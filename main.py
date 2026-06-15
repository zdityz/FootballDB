from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, ForeignKey, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from passlib.context import CryptContext
import jwt
from datetime import datetime, timedelta, timezone

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

app = FastAPI(title="Match Analytics Hub")

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

@app.post("/teams", response_model=TeamResponse)
def create_team(team: TeamCreate, db: Session = Depends(get_db), current_user: UserModel = Depends(get_current_user)):
    db_team = db.query(TeamModel).filter(TeamModel.name == team.name).first()
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