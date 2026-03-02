# backend/routes/user.py
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, EmailStr
from typing import Optional
import jwt
import bcrypt
import os
from datetime import datetime, timedelta
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

from supabase_client import get_supabase_client
from local_auth import user_exists, create_user, get_user_by_email

# Secret key for JWT token encoding
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "safarsmart-fallback-secret-change-in-production")
ALGORITHM = "HS256"

router = APIRouter()  # Create the router for user-related routes

# User credentials schema for login
class UserCredentials(BaseModel):
    email: EmailStr
    password: str

# User registration schema
class UserRegistration(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None

# User profile schema
class UserProfile(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None

# User profile update schema
class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = None

# Function to create JWT token
def create_jwt_token(email: str):
    expiration = datetime.utcnow() + timedelta(hours=24)  # Token expires in 24 hours
    payload = {
        "sub": email,  # 'sub' represents the user
        "exp": expiration  # Set expiration time
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)  # Generate JWT token
    return token

# Function to verify JWT token
def verify_token(authorization: str = Header(None)) -> str:
    """Extract and verify JWT token from Authorization header."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")
    
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Invalid authentication scheme")
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid authorization header format")
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        return email
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# Hash password
def hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

# Verify password
def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hash."""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

# Route for user registration
@router.post("/register")
async def register(user_data: UserRegistration):
    """Register a new user with email and password."""
    password_hash = hash_password(user_data.password)

    # --- Try Supabase first ---
    supabase = get_supabase_client()
    if supabase:
        try:
            existing = supabase.table("users").select("email").eq("email", user_data.email).execute()
            if existing.data:
                raise HTTPException(status_code=400, detail="Email already registered")
            result = supabase.table("users").insert({
                "email": user_data.email,
                "password_hash": password_hash,
                "full_name": user_data.full_name
            }).execute()
            if not result.data:
                raise HTTPException(status_code=500, detail="Failed to create user")
            user = result.data[0]
            token = create_jwt_token(user_data.email)
            return {
                "message": "Registration successful",
                "user": {"email": user["email"], "full_name": user.get("full_name")},
                "token": token
            }
        except HTTPException:
            raise
        except Exception:
            pass  # Supabase failed — fall through to local auth

    # --- Local SQLite fallback ---
    try:
        if user_exists(user_data.email):
            raise HTTPException(status_code=400, detail="Email already registered")
        user = create_user(user_data.email, password_hash, user_data.full_name)
        token = create_jwt_token(user_data.email)
        return {
            "message": "Registration successful",
            "user": {"email": user["email"], "full_name": user.get("full_name")},
            "token": token
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to register user: {str(e)}")

# Route for user login
@router.post("/login")
async def login(credentials: UserCredentials):
    """Login with email and password."""
    # --- Try Supabase first ---
    supabase = get_supabase_client()
    if supabase:
        try:
            result = supabase.table("users").select("*").eq("email", credentials.email).execute()
            if result.data:
                user = result.data[0]
                if not verify_password(credentials.password, user["password_hash"]):
                    raise HTTPException(status_code=400, detail="Invalid credentials")
                token = create_jwt_token(credentials.email)
                return {
                    "message": "Login successful",
                    "user": {"email": user["email"], "full_name": user.get("full_name")},
                    "token": token
                }
        except HTTPException:
            raise
        except Exception:
            pass  # Supabase failed — fall through to local auth

    # --- Local SQLite fallback ---
    try:
        user = get_user_by_email(credentials.email)
        if not user:
            raise HTTPException(status_code=400, detail="Invalid credentials")
        if not verify_password(credentials.password, user["password_hash"]):
            raise HTTPException(status_code=400, detail="Invalid credentials")
        token = create_jwt_token(credentials.email)
        return {
            "message": "Login successful",
            "user": {"email": user["email"], "full_name": user.get("full_name")},
            "token": token
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

# Route to get user profile
@router.get("/profile", response_model=UserProfile)
async def get_profile(email: str = Depends(verify_token)):
    """Get current user's profile."""
    supabase = get_supabase_client()
    if not supabase:
        raise HTTPException(status_code=500, detail="Database connection not available")
    
    try:
        result = supabase.table("users").select("email, full_name").eq("email", email).execute()
        
        if not result.data or len(result.data) == 0:
            raise HTTPException(status_code=404, detail="User not found")
        
        user = result.data[0]
        return UserProfile(
            email=user["email"],
            full_name=user.get("full_name")
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get profile: {str(e)}")

# Route to update user profile
@router.put("/profile", response_model=UserProfile)
async def update_profile(
    profile_update: UserProfileUpdate,
    email: str = Depends(verify_token)
):
    """Update current user's profile."""
    supabase = get_supabase_client()
    if not supabase:
        raise HTTPException(status_code=500, detail="Database connection not available")
    
    try:
        update_data = {}
        if profile_update.full_name is not None:
            update_data["full_name"] = profile_update.full_name
        
        if not update_data:
            # No changes, just return current profile
            result = supabase.table("users").select("email, full_name").eq("email", email).execute()
            if result.data:
                user = result.data[0]
                return UserProfile(
                    email=user["email"],
                    full_name=user.get("full_name")
                )
            raise HTTPException(status_code=404, detail="User not found")
        
        # Update user
        result = supabase.table("users").update(update_data).eq("email", email).execute()
        
        if not result.data or len(result.data) == 0:
            raise HTTPException(status_code=404, detail="User not found")
        
        user = result.data[0]
        return UserProfile(
            email=user["email"],
            full_name=user.get("full_name")
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update profile: {str(e)}")
