ALTER TABLE user_quiz_attempts
    ADD COLUMN IF NOT EXISTS attempt_no INTEGER NOT NULL DEFAULT 1;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'user_quiz_attempts'::regclass
          AND conname = 'user_quiz_attempts_user_id_quiz_date_key'
    ) THEN
        ALTER TABLE user_quiz_attempts DROP CONSTRAINT user_quiz_attempts_user_id_quiz_date_key;
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_user_quiz_attempts_user_date_no
ON user_quiz_attempts(user_id, quiz_date, attempt_no);
