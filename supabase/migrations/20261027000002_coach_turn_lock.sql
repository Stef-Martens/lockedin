-- Set while the coach is answering in a chat, so two answers can't interleave in one conversation.
alter table coach_conversations add column turn_started_at timestamptz;
