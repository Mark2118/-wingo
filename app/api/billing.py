# -*- coding: utf-8 -*-
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.api.auth import get_current_user, require_role
from app.models.schemas import Team, Subscription, Order

router = APIRouter(prefix="/api/billing", tags=["billing"])

PLANS = {
    "trial": {"name": "体验版", "price": 0, "max_members": 1, "max_projects": 5},
    "team": {"name": "团队版", "price": 5000, "max_members": 10, "max_projects": -1},
    "enterprise": {"name": "企业版", "price": 30000, "max_members": -1, "max_projects": -1},
}


@router.get("/plans")
def list_plans():
    return {"plans": PLANS}


@router.post("/subscribe")
def subscribe(plan: str, user=Depends(require_role(["owner", "admin"])), db: Session = Depends(get_db)):
    if plan not in PLANS:
        return {"error": "Invalid plan"}
    team = db.query(Team).filter(Team.id == user.team_id).first()
    if not team:
        return {"error": "Team not found"}

    order = Order(team_id=team.id, plan=plan, amount=PLANS[plan]["price"], status="pending")
    db.add(order)
    db.flush()

    sub = Subscription(team_id=team.id, plan=plan, price=PLANS[plan]["price"], order_id=order.id)
    db.add(sub)
    db.commit()

    return {"order_id": order.id, "plan": plan, "amount": PLANS[plan]["price"], "pay_url": f"/api/billing/pay/{order.id}"}


@router.get("/subscription")
def get_subscription(user=Depends(get_current_user), db: Session = Depends(get_db)):
    team = db.query(Team).filter(Team.id == user.team_id).first()
    sub = db.query(Subscription).filter(Subscription.team_id == user.team_id).order_by(Subscription.id.desc()).first()
    return {"team": {"id": team.id, "name": team.name, "plan": team.plan}, "subscription": {"plan": sub.plan, "status": sub.status, "expired_at": sub.expired_at} if sub else None}


@router.get("/orders")
def list_orders(user=Depends(get_current_user), db: Session = Depends(get_db)):
    orders = db.query(Order).filter(Order.team_id == user.team_id).order_by(Order.id.desc()).all()
    return {"orders": [{"id": o.id, "plan": o.plan, "amount": o.amount, "status": o.status, "created_at": o.created_at} for o in orders]}


@router.post("/pay/{order_id}")
def pay_order(order_id: int, user=Depends(require_role(["owner", "admin"])), db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id, Order.team_id == user.team_id).first()
    if not order:
        return {"error": "Order not found"}

    order.status = "paid"
    order.pay_time = "now"
    db.commit()

    team = db.query(Team).filter(Team.id == user.team_id).first()
    team.plan = order.plan
    db.commit()

    return {"success": True, "order_id": order_id, "status": "paid"}
