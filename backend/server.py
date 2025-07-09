from fastapi import FastAPI, APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
from datetime import datetime, timedelta
import jwt
from passlib.context import CryptContext
from passlib.hash import bcrypt

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Security
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()
SECRET_KEY = "guardiao_secret_key_2025"
ALGORITHM = "HS256"

# Create the main app without a prefix
app = FastAPI(title="GUARDIÃO API")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# User Models
class User(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: str
    name: str
    role: str  # Síndico, Segurança, Administrador
    password_hash: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True

class UserCreate(BaseModel):
    email: str
    name: str
    role: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    role: str
    created_at: datetime
    is_active: bool

# Visit Models
class Visit(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    visitor_name: str
    visitor_document: str
    destination: str  # Apartamento/Casa número
    purpose: str
    entry_time: datetime = Field(default_factory=datetime.utcnow)
    exit_time: Optional[datetime] = None
    status: str = "pending"  # pending, approved, denied, completed
    approved_by: Optional[str] = None
    notes: Optional[str] = None
    created_by: str

class VisitCreate(BaseModel):
    visitor_name: str
    visitor_document: str
    destination: str
    purpose: str
    notes: Optional[str] = None

class VisitUpdate(BaseModel):
    status: str
    notes: Optional[str] = None

class VisitResponse(BaseModel):
    id: str
    visitor_name: str
    visitor_document: str
    destination: str
    purpose: str
    entry_time: datetime
    exit_time: Optional[datetime]
    status: str
    approved_by: Optional[str]
    notes: Optional[str]
    created_by: str

# Authentication Models
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

# Utility Functions
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=24)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
    
    user = await db.users.find_one({"id": user_id})
    if user is None:
        raise credentials_exception
    return User(**user)

# Initialize default users
async def init_default_users():
    # Check if users already exist
    existing_users = await db.users.count_documents({})
    if existing_users == 0:
        default_users = [
            {
                "id": str(uuid.uuid4()),
                "email": "admin@guardiao.com",
                "name": "Administrador",
                "role": "Administrador",
                "password_hash": get_password_hash("admin123"),
                "created_at": datetime.utcnow(),
                "is_active": True
            },
            {
                "id": str(uuid.uuid4()),
                "email": "seguranca@guardiao.com",
                "name": "Segurança",
                "role": "Segurança",
                "password_hash": get_password_hash("seg123"),
                "created_at": datetime.utcnow(),
                "is_active": True
            },
            {
                "id": str(uuid.uuid4()),
                "email": "sindico@guardiao.com",
                "name": "Síndico",
                "role": "Síndico",
                "password_hash": get_password_hash("sind123"),
                "created_at": datetime.utcnow(),
                "is_active": True
            }
        ]
        await db.users.insert_many(default_users)
        print("Default users created successfully!")

# Authentication Routes
@api_router.post("/auth/login", response_model=Token)
async def login(user_credentials: UserLogin):
    user = await db.users.find_one({"email": user_credentials.email})
    if not user or not verify_password(user_credentials.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário desativado"
        )
    
    access_token = create_access_token(data={"sub": user["id"]})
    user_response = UserResponse(**user)
    
    return Token(access_token=access_token, user=user_response)

@api_router.post("/auth/register", response_model=UserResponse)
async def register(user_data: UserCreate, current_user: User = Depends(get_current_user)):
    # Only administrators can create new users
    if current_user.role != "Administrador":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado. Apenas administradores podem criar usuários."
        )
    
    # Check if user already exists
    existing_user = await db.users.find_one({"email": user_data.email})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuário já existe com este email"
        )
    
    # Create new user
    user_dict = user_data.dict()
    user_dict["password_hash"] = get_password_hash(user_dict.pop("password"))
    user_obj = User(**user_dict)
    
    await db.users.insert_one(user_obj.dict())
    return UserResponse(**user_obj.dict())

@api_router.get("/auth/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    return UserResponse(**current_user.dict())

# Visit Routes
@api_router.post("/visits", response_model=VisitResponse)
async def create_visit(visit_data: VisitCreate, current_user: User = Depends(get_current_user)):
    visit_dict = visit_data.dict()
    visit_dict["created_by"] = current_user.id
    visit_obj = Visit(**visit_dict)
    
    await db.visits.insert_one(visit_obj.dict())
    return VisitResponse(**visit_obj.dict())

@api_router.get("/visits", response_model=List[VisitResponse])
async def get_visits(current_user: User = Depends(get_current_user)):
    visits = await db.visits.find().sort("entry_time", -1).to_list(1000)
    return [VisitResponse(**visit) for visit in visits]

@api_router.get("/visits/{visit_id}", response_model=VisitResponse)
async def get_visit(visit_id: str, current_user: User = Depends(get_current_user)):
    visit = await db.visits.find_one({"id": visit_id})
    if not visit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Visita não encontrada"
        )
    return VisitResponse(**visit)

@api_router.put("/visits/{visit_id}", response_model=VisitResponse)
async def update_visit(visit_id: str, visit_update: VisitUpdate, current_user: User = Depends(get_current_user)):
    visit = await db.visits.find_one({"id": visit_id})
    if not visit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Visita não encontrada"
        )
    
    update_data = visit_update.dict(exclude_unset=True)
    
    if visit_update.status in ["approved", "denied"]:
        update_data["approved_by"] = current_user.id
    
    if visit_update.status == "completed":
        update_data["exit_time"] = datetime.utcnow()
    
    await db.visits.update_one(
        {"id": visit_id},
        {"$set": update_data}
    )
    
    updated_visit = await db.visits.find_one({"id": visit_id})
    return VisitResponse(**updated_visit)

@api_router.delete("/visits/{visit_id}")
async def delete_visit(visit_id: str, current_user: User = Depends(get_current_user)):
    if current_user.role not in ["Administrador", "Síndico"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado. Apenas administradores e síndicos podem deletar visitas."
        )
    
    result = await db.visits.delete_one({"id": visit_id})
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Visita não encontrada"
        )
    
    return {"message": "Visita deletada com sucesso"}

# Dashboard Statistics
@api_router.get("/dashboard/stats")
async def get_dashboard_stats(current_user: User = Depends(get_current_user)):
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Total visits today
    visits_today = await db.visits.count_documents({
        "entry_time": {"$gte": today}
    })
    
    # Pending visits
    pending_visits = await db.visits.count_documents({
        "status": "pending"
    })
    
    # Total visitors inside (approved but not completed)
    visitors_inside = await db.visits.count_documents({
        "status": "approved",
        "exit_time": None
    })
    
    # Recent visits (last 10)
    recent_visits = await db.visits.find().sort("entry_time", -1).limit(10).to_list(10)
    
    return {
        "visits_today": visits_today,
        "pending_visits": pending_visits,
        "visitors_inside": visitors_inside,
        "recent_visits": [VisitResponse(**visit) for visit in recent_visits]
    }

# Health check
@api_router.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow()}

# Initialize on startup
@app.on_event("startup")
async def startup_event():
    await init_default_users()
    print("GUARDIÃO API initialized successfully!")

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()