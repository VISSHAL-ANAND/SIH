"""
Database Architecture & Connection Management
==============================================
PostgreSQL / PostGIS database engine configuration using SQLAlchemy and GeoAlchemy2.
Includes graceful fallback to in-memory spatial storage if PostGIS service is offline.
"""

import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

logger = logging.getLogger("maritime_db")

# Default PostgreSQL/PostGIS connection string
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://postgres:postgres@localhost:5432/sih_maritime_db"
)

# Declarative Base for models
Base = declarative_base()
IS_POSTGIS = False

def _create_db_engine():
    global IS_POSTGIS
    try:
        eng = create_engine(
            DATABASE_URL, 
            pool_pre_ping=True, 
            pool_size=5, 
            max_overflow=10,
            connect_args={"connect_timeout": 2}
        )
        with eng.connect() as conn:
            pass
        IS_POSTGIS = True
        logger.info("[Database] Connected to PostgreSQL / PostGIS database successfully.")
        return eng
    except Exception as e:
        IS_POSTGIS = False
        logger.info(f"[Database] PostgreSQL connection offline ({e}). Operating in Spatial Fallback mode.")
        FALLBACK_URL = "sqlite:///:memory:"
        return create_engine(FALLBACK_URL, connect_args={"check_same_thread": False})

engine = _create_db_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Dependency for obtaining DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initializes database tables."""
    try:
        if IS_POSTGIS:
            Base.metadata.create_all(bind=engine)
            logger.info("[Database] PostGIS tables initialized successfully.")
        else:
            # Create SQLite tables safely without GeoAlchemy2 Spatialite triggers
            with engine.begin() as conn:
                conn.exec_driver_sql("""
                    CREATE TABLE IF NOT EXISTS ais_tracks (
                        id VARCHAR(36) PRIMARY KEY,
                        mmsi VARCHAR(20) NOT NULL,
                        vessel_name VARCHAR(100),
                        flag VARCHAR(50),
                        timestamp DATETIME NOT NULL,
                        sog FLOAT,
                        geom TEXT
                    )
                """)
                conn.exec_driver_sql("""
                    CREATE TABLE IF NOT EXISTS dark_vessel_incidents (
                        id VARCHAR(36) PRIMARY KEY,
                        incident_uuid VARCHAR(100) UNIQUE NOT NULL,
                        slick_area_sq_m FLOAT NOT NULL DEFAULT 0.0,
                        origin_lat FLOAT NOT NULL,
                        origin_lon FLOAT NOT NULL,
                        threat_score FLOAT NOT NULL DEFAULT 0.95,
                        created_at DATETIME NOT NULL,
                        details JSON
                    )
                """)
            logger.info("[Database] Fallback spatial tables initialized successfully.")
    except Exception as e:
        logger.warning(f"[Database] Table initialization notice: {e}")
