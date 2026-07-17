import os
import sys
import asyncio
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.sql import func, text
from pgvector.sqlalchemy import Vector
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- 1. CONFIGURATION ---
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is required for production architecture.")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

print("Using PostgreSQL database from DATABASE_URL")

# Async Configuration - The Gold Standard!
import re
ASYNC_DATABASE_URL = re.sub(r"^postgres(ql)?(\+[a-zA-Z0-9_-]+)?://", "postgresql+asyncpg://", DATABASE_URL)

# 1. API Pool (used by FastAPI)
async_engine = create_async_engine(ASYNC_DATABASE_URL, pool_recycle=3600)
AsyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=async_engine, class_=AsyncSession)

Base = declarative_base()

# --- 2. THE MODELS ---
class ProcessedSite(Base):
    __tablename__ = "processed_sites"

    id = Column(Integer, primary_key=True, index=True)
    url_hash = Column(String(32), unique=True, index=True, nullable=False)
    url = Column(Text, nullable=False)
    policy_text = Column(Text, nullable=True) # Will store raw markdown
    internal_links = Column(JSON, nullable=True, default=list) # Stores discovered child URLs
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    chunks = relationship("PolicyChunk", back_populates="site", cascade="all, delete")

class PolicyChunk(Base):
    __tablename__ = "policy_chunks"

    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(Integer, ForeignKey("processed_sites.id", ondelete="CASCADE"), index=True)
    chunk_text = Column(Text, nullable=False)
    parent_text = Column(Text, nullable=False) # Important for full context!
    # Using 1024 for Cohere embed-english-v3.0
    embedding = Column(Vector(1024))
    
    site = relationship("ProcessedSite", back_populates="chunks")

# --- 3. DATABASE SETUP ---
async def get_async_db():
    async with AsyncSessionLocal() as db:
        yield db

# --- 4. INITIALIZATION ---
async def init_db():
    print("Initializing database tables with pgvector extension (Async)...")
    async with async_engine.begin() as conn:
        # 1. WHAT IS VECTOR? 
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))
        

        # 3. WHERE ARE THE TABLES CREATED?
        # run_sync bridges the gap between async execution and SQLAlchemy's sync metadata builder
        await conn.run_sync(Base.metadata.create_all)
        

        # 5. WHAT IS HNSW? (Hierarchical Navigable Small World)
        await conn.execute(text('CREATE INDEX IF NOT EXISTS chunk_embedding_idx ON policy_chunks USING hnsw (embedding vector_cosine_ops)'))
        
        # 6. WHAT IS TEXT_PATTERN_OPS?
        # Optimizes prefix matching (LIKE 'https://site.com%') for isolated RAG context.
        await conn.execute(text('CREATE INDEX IF NOT EXISTS idx_processed_site_url_prefix ON processed_sites (url text_pattern_ops)'))
        
    print("Database ready.")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(init_db())
