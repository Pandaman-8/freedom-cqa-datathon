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

-- T06 is additive: existing T05 tables, snapshots and triggers are unchanged.
-- Evaluations without a review row have revision 0; the first appeal creates it.
CREATE TABLE IF NOT EXISTS evaluation_reviews (
    evaluation_id TEXT PRIMARY KEY NOT NULL REFERENCES evaluations(id),
    revision INTEGER NOT NULL CHECK (typeof(revision)='integer' AND revision >= 0)
);;
CREATE TABLE IF NOT EXISTS appeals (
    id TEXT PRIMARY KEY NOT NULL,
    evaluation_id TEXT NOT NULL REFERENCES evaluations(id),
    criterion_id TEXT NOT NULL,
    comment TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('open','resolved')),
    decision TEXT,
    reason TEXT,
    replacement_json TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    created_revision INTEGER NOT NULL CHECK (typeof(created_revision)='integer' AND created_revision > 0),
    resolved_revision INTEGER,
    UNIQUE (evaluation_id, created_revision),
    UNIQUE (evaluation_id, resolved_revision),
    CHECK (
        (status='open' AND decision IS NULL AND reason IS NULL AND replacement_json IS NULL
            AND resolved_at IS NULL AND resolved_revision IS NULL)
        OR
        (status='resolved' AND decision IS NOT NULL AND decision IN ('confirm','change')
            AND reason IS NOT NULL AND resolved_at IS NOT NULL
            AND resolved_revision IS NOT NULL AND typeof(resolved_revision)='integer' AND resolved_revision > created_revision
            AND ((decision='confirm' AND replacement_json IS NULL) OR (decision='change' AND replacement_json IS NOT NULL)))
    )
);;
CREATE UNIQUE INDEX IF NOT EXISTS idx_appeals_one_open ON appeals(evaluation_id, criterion_id) WHERE status='open';;
CREATE TRIGGER IF NOT EXISTS appeals_preserve_history BEFORE UPDATE ON appeals
WHEN OLD.status <> 'open' OR NEW.status <> 'resolved'
    OR NEW.id IS NOT OLD.id OR NEW.evaluation_id IS NOT OLD.evaluation_id
    OR NEW.criterion_id IS NOT OLD.criterion_id OR NEW.comment IS NOT OLD.comment
    OR NEW.created_at IS NOT OLD.created_at OR NEW.created_revision IS NOT OLD.created_revision
BEGIN SELECT RAISE(ABORT, 'immutable_appeal_history'); END;;
CREATE TRIGGER IF NOT EXISTS appeals_no_delete BEFORE DELETE ON appeals
BEGIN SELECT RAISE(ABORT, 'immutable_appeal_history'); END;;
CREATE TRIGGER IF NOT EXISTS evaluation_reviews_monotonic BEFORE UPDATE ON evaluation_reviews
WHEN NEW.evaluation_id IS NOT OLD.evaluation_id OR NEW.revision <> OLD.revision + 1
BEGIN SELECT RAISE(ABORT, 'invalid_review_revision'); END;;
CREATE TRIGGER IF NOT EXISTS evaluation_reviews_no_delete BEFORE DELETE ON evaluation_reviews
BEGIN SELECT RAISE(ABORT, 'immutable_review_revision'); END;;
