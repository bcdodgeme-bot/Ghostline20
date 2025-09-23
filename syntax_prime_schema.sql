-- ============================================================================
-- SYNTAX PRIME V2 - MINIMAL SCHEMA FOR INITIAL SETUP
-- Start with core tables, add complexity later
-- ============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ============================================================================
-- USERS
-- ============================================================================

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(50) UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(100),
    timezone VARCHAR(50) DEFAULT 'UTC',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,
    sync_version BIGINT DEFAULT 0
);

-- ============================================================================
-- KNOWLEDGE BASE
-- ============================================================================

-- Projects to organize knowledge
CREATE TABLE knowledge_projects (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    display_name VARCHAR(200),
    description TEXT,
    category VARCHAR(50),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Knowledge sources
CREATE TABLE knowledge_sources (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    source_type VARCHAR(30) NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Core knowledge entries (your JSONL data)
CREATE TABLE knowledge_entries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Original structure from JSONL
    source_id INTEGER REFERENCES knowledge_sources(id),
    title VARCHAR(500),
    project_id INTEGER REFERENCES knowledge_projects(id),
    conversation_id VARCHAR(100),
    create_time NUMERIC,
    content TEXT NOT NULL,
    content_type VARCHAR(50) DEFAULT 'unknown',
    sha1 VARCHAR(40) UNIQUE,
    
    -- Enhanced metadata
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    summary TEXT,
    key_topics JSONB DEFAULT '[]',
    word_count INTEGER,
    
    -- Usage tracking
    access_count INTEGER DEFAULT 0,
    last_accessed TIMESTAMP WITH TIME ZONE,
    relevance_score DECIMAL(5,2) DEFAULT 5.0,
    
    -- Processing
    processed BOOLEAN DEFAULT FALSE,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Full text search
    search_vector tsvector
);

-- ============================================================================
-- CONVERSATIONS (NEW SYNTAX PRIME CONVERSATIONS)
-- ============================================================================

CREATE TABLE conversation_threads (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(200),
    summary TEXT,
    
    -- Context
    primary_project_id INTEGER REFERENCES knowledge_projects(id),
    platform VARCHAR(20) NOT NULL CHECK (platform IN ('web', 'ios', 'android', 'slack', 'email', 'api')),
    
    -- State
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'archived', 'completed', 'deleted')),
    
    -- Stats
    message_count INTEGER DEFAULT 0,
    user_satisfaction_rating INTEGER CHECK (user_satisfaction_rating >= 1 AND user_satisfaction_rating <= 5),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_message_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE conversation_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    thread_id UUID NOT NULL REFERENCES conversation_threads(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Message content
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    content_type VARCHAR(20) DEFAULT 'text',
    
    -- AI metadata
    response_time_ms INTEGER,
    model_used VARCHAR(50),
    knowledge_sources_used JSONB DEFAULT '[]',
    
    -- Learning data
    extracted_preferences JSONB DEFAULT '{}',
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================================
-- FEEDBACK SYSTEM
-- ============================================================================

CREATE TABLE user_feedback (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    message_id UUID NOT NULL REFERENCES conversation_messages(id) ON DELETE CASCADE,
    thread_id UUID NOT NULL REFERENCES conversation_threads(id) ON DELETE CASCADE,
    
    -- Simple feedback types: Good Answer, Bad Answer, Good Personality
    feedback_type VARCHAR(30) NOT NULL CHECK (feedback_type IN ('good_answer', 'bad_answer', 'good_personality', 'bad_personality')),
    
    -- Optional detailed feedback
    feedback_text TEXT,
    
    -- Processing
    processed_for_learning BOOLEAN DEFAULT FALSE,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed_at TIMESTAMP WITH TIME ZONE
);

-- ============================================================================
-- RSS MARKETING FEED (SEPARATE TABLE)
-- ============================================================================

CREATE TABLE rss_feed_entries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    
    -- RSS Entry data
    title VARCHAR(500),
    description TEXT,
    link VARCHAR(1000),
    pub_date TIMESTAMP WITH TIME ZONE,
    guid VARCHAR(500) UNIQUE, -- RSS GUID for deduplication
    
    -- Content
    full_content TEXT,
    summary TEXT,
    
    -- Categorization
    category VARCHAR(100),
    tags JSONB DEFAULT '[]',
    
    -- Marketing specific
    campaign_type VARCHAR(50), -- 'email', 'social', 'blog', etc.
    target_audience VARCHAR(100),
    
    -- Processing
    processed BOOLEAN DEFAULT FALSE,
    sentiment_score DECIMAL(3,2),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================================
-- BASIC INDEXES
-- ============================================================================

-- Knowledge base
CREATE INDEX idx_knowledge_entries_sha1 ON knowledge_entries(sha1);
CREATE INDEX idx_knowledge_entries_project ON knowledge_entries(project_id);
CREATE INDEX idx_knowledge_entries_search ON knowledge_entries USING gin(to_tsvector('english', title || ' ' || content));

-- Conversations
CREATE INDEX idx_conversation_threads_user ON conversation_threads(user_id, updated_at DESC);
CREATE INDEX idx_conversation_messages_thread ON conversation_messages(thread_id, created_at);

-- Feedback
CREATE INDEX idx_feedback_user_time ON user_feedback(user_id, created_at DESC);
CREATE INDEX idx_feedback_unprocessed ON user_feedback(processed_for_learning, created_at) WHERE processed_for_learning = FALSE;

-- RSS Feed
CREATE INDEX idx_rss_entries_guid ON rss_feed_entries(guid);
CREATE INDEX idx_rss_entries_date ON rss_feed_entries(pub_date DESC);

-- ============================================================================
-- INITIAL DATA
-- ============================================================================

-- Insert your known projects
INSERT INTO knowledge_projects (name, display_name, category) VALUES
('AMCF', 'American Muslim Community Foundation', 'client_work'),
('Business', 'Business Knowledge', 'domain_knowledge'),
('Health', 'Health & Wellness', 'domain_knowledge'),
('Personal Development', 'Personal Development', 'personal'),
('General', 'General Knowledge', 'personal'),
('Kitchen', 'Cooking & Food', 'personal'),
('Personal Operating Manual', 'Personal Operating Manual', 'personal');

-- Insert your known sources
INSERT INTO knowledge_sources (name, source_type) VALUES
('ChatGPT Conversation', 'conversation'),
('Raw Data - raw_business', 'raw_data'),
('Raw Data - raw_health', 'raw_data'),
('Raw Data - raw_personal', 'raw_data'),
('Raw Data - raw_personal_dev', 'raw_data'),
('article', 'article');

-- ============================================================================
-- UTILITY FUNCTIONS
-- ============================================================================

-- Update search vector automatically
CREATE OR REPLACE FUNCTION update_knowledge_search_vector()
RETURNS TRIGGER AS $$
BEGIN
    NEW.search_vector := to_tsvector('english', 
        COALESCE(NEW.title, '') || ' ' || COALESCE(NEW.content, '')
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Update conversation stats
CREATE OR REPLACE FUNCTION update_conversation_stats()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE conversation_threads SET 
        message_count = message_count + 1,
        last_message_at = NEW.created_at,
        updated_at = NEW.created_at
    WHERE id = NEW.thread_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers
CREATE TRIGGER trigger_knowledge_search_vector
    BEFORE INSERT OR UPDATE ON knowledge_entries
    FOR EACH ROW EXECUTE FUNCTION update_knowledge_search_vector();

CREATE TRIGGER trigger_conversation_stats
    AFTER INSERT ON conversation_messages
    FOR EACH ROW EXECUTE FUNCTION update_conversation_stats();
