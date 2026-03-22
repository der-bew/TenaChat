"""
Authentication and authorization endpoints for the app
version: 1.0.0
author: Derbew Felasman
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from fastapi.security import OAuth2PasswordBearer
from app.db.supabase_client import supabase

router = APIRouter()


class SignupRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/signup")
def signup(request: SignupRequest):
    res = supabase.auth.sign_up({"email": request.email, "password": request.password})
    if res.user is None:
        raise HTTPException(status_code=400, detail="Signup failed")
    return {"message": "User created"}


@router.post("/login")
def login(request: LoginRequest):
    res = supabase.auth.sign_in_with_password(
        {"email": request.email, "password": request.password}
    )
    if res.session is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"access_token": res.session.access_token}


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)


def get_current_user(token: str = Depends(oauth2_scheme)):
    """Get authenticated user ID (requires token)."""
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    auth_response = supabase.auth.get_user(token)
    if not auth_response or auth_response.user is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    return auth_response.user.id


def get_current_user_or_anonymous(token: str = Depends(oauth2_scheme)):
    """Get current user if authenticated, or None for anonymous users."""
    if token:
        auth_response = supabase.auth.get_user(token)
        if auth_response and auth_response.user:
            return auth_response.user.id
    return None
