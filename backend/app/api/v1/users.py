from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.db.session import get_db
from app.models.customer import Customer
from app.models.user import User
from app.schemas.auth import CustomerOut, UserOut

router = APIRouter(prefix="/api/v1", tags=["users"])


@router.get("/users/me", response_model=UserOut)
def get_me(current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
    user = db.get(User, current_user.id)
    return UserOut(
        id=user.id,
        customer_id=user.customer_id,
        email=user.email,
        full_name=user.full_name,
        role=current_user.role,
        is_active=user.is_active,
    )


@router.get("/customers/me", response_model=CustomerOut)
def get_my_customer(current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)) -> Customer:
    return db.get(Customer, current_user.customer_id)
