CREATE TABLE IF NOT EXISTS checklists (
    key TEXT NOT NULL,
    version TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (key, version)
);;
CREATE TABLE IF NOT EXISTS checklist_heads (
    key TEXT PRIMARY KEY NOT NULL,
    version TEXT NOT NULL,
    FOREIGN KEY (key, version) REFERENCES checklists(key, version)
);;
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY NOT NULL,
    dataset_group_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    language TEXT NOT NULL CHECK (language IN ('RU','KZ','EN')),
    channel TEXT NOT NULL CHECK (channel IN ('agent chat','voice call')),
    message_count INTEGER NOT NULL CHECK (message_count > 0),
    source_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    UNIQUE (dataset_group_id, conversation_id)
);;
CREATE TABLE IF NOT EXISTS evaluations (
    id TEXT PRIMARY KEY NOT NULL,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    checklist_key TEXT NOT NULL,
    checklist_version TEXT NOT NULL,
    origin TEXT NOT NULL,
    scoring_version TEXT NOT NULL,
    answers_json TEXT NOT NULL,
    score_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (checklist_key, checklist_version) REFERENCES checklists(key, version)
);;
CREATE INDEX IF NOT EXISTS idx_conversations_group ON conversations(dataset_group_id, conversation_id);;
CREATE INDEX IF NOT EXISTS idx_evaluations_conversation ON evaluations(conversation_id, created_at, id);;
CREATE INDEX IF NOT EXISTS idx_evaluations_created ON evaluations(created_at, id);;
CREATE TRIGGER IF NOT EXISTS checklists_no_update BEFORE UPDATE ON checklists
BEGIN SELECT RAISE(ABORT, 'immutable_checklist'); END;;
CREATE TRIGGER IF NOT EXISTS checklists_no_delete BEFORE DELETE ON checklists
BEGIN SELECT RAISE(ABORT, 'immutable_checklist'); END;;
CREATE TRIGGER IF NOT EXISTS conversations_no_update BEFORE UPDATE ON conversations
BEGIN SELECT RAISE(ABORT, 'immutable_source'); END;;
CREATE TRIGGER IF NOT EXISTS conversations_no_delete BEFORE DELETE ON conversations
BEGIN SELECT RAISE(ABORT, 'immutable_source'); END;;
CREATE TRIGGER IF NOT EXISTS evaluations_no_update BEFORE UPDATE ON evaluations
BEGIN SELECT RAISE(ABORT, 'immutable_evaluation'); END;;
CREATE TRIGGER IF NOT EXISTS evaluations_no_delete BEFORE DELETE ON evaluations
BEGIN SELECT RAISE(ABORT, 'immutable_evaluation'); END;;
