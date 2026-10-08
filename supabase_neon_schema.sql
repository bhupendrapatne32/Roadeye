-- Schema for Supabase or Neon PostgreSQL with PostGIS support

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS postgis;

-- 1. Users / Reporters Table
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(100) UNIQUE NOT NULL,
    reputation_score INTEGER DEFAULT 50,
    reports_count INTEGER DEFAULT 0,
    helpful_votes INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. Hazards Table
CREATE TABLE IF NOT EXISTS hazards (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    reporter_id VARCHAR(100) NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    location GEOMETRY(Point, 4326),
    category VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    description TEXT,
    image_url TEXT,
    confidence_score INTEGER DEFAULT 40,
    status VARCHAR(20) DEFAULT 'ACTIVE',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE,
    confirm_count INTEGER DEFAULT 1,
    reject_count INTEGER DEFAULT 0
);

-- Spatial Index for Fast PostGIS Radius Queries
CREATE INDEX IF NOT EXISTS idx_hazards_spatial ON hazards USING GIST(location);

-- 3. Hazard Verifications Table
CREATE TABLE IF NOT EXISTS hazard_verifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hazard_id UUID REFERENCES hazards(id) ON DELETE CASCADE,
    voter_id VARCHAR(100) NOT NULL,
    is_still_there BOOLEAN NOT NULL,
    voted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(hazard_id, voter_id)
);
