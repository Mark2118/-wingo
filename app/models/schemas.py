# -*- coding: utf-8 -*-
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Float, Boolean
from sqlalchemy.sql import func
from app.database import Base
import uuid


def gen_uuid():
    return str(uuid.uuid4())


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    license_key = Column(String(100), unique=True, index=True)
    plan = Column(String(20), default="trial")  # trial / team / enterprise
    max_members = Column(Integer, default=1)
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expired_at = Column(DateTime(timezone=True), nullable=True)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True, index=True)
    email = Column(String(200), unique=True, index=True, nullable=False)
    phone = Column(String(20), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(100), nullable=True)
    avatar = Column(String(500), nullable=True)
    role = Column(String(20), default="member")  # owner / admin / developer / viewer
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False, index=True)
    plan = Column(String(20), nullable=False)
    status = Column(String(20), default="active")  # active / expired / cancelled
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    expired_at = Column(DateTime(timezone=True), nullable=True)
    price = Column(Float, nullable=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False, index=True)
    plan = Column(String(20), nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(String(20), default="pending")  # pending / paid / refunded / failed
    pay_method = Column(String(50), nullable=True)
    pay_time = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Project(Base):
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), default="created")
    stage = Column(String(50), default="")
    requirement = Column(Text, nullable=True)
    prd = Column(Text, nullable=True)
    deploy_url = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Chat(Base):
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
