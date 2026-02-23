#!/usr/bin/env python3
"""
Import Claude Data Export into Syntax Prime V2
==============================================
Imports:
  1. Claude Projects → knowledge_projects (new entries)
  2. Project Docs → knowledge_entries (searchable)
  3. Conversations → conversation_threads (platform=claude.ai)
  4. Messages → conversation_messages (full history)
  5. Memories → knowledge_entries (Claude's memory snapshots)

Usage:
  python import_claude_export.py [--dry-run] [--data-dir PATH]

Requires: psycopg2
"""

import json
import hashlib
import os
import sys
import argparse
from datetime import datetime, timezone
from collections import defaultdict

import psycopg2
import psycopg2.extras

# =============================================================================
# CONFIGURATION
# =============================================================================

DATABASE_URL = "postgresql://postgres:RcldqFcBwHuiuqpiCemgiTjfuJcvOJLH@ballast.proxy.rlwy.net:12126/railway"
DEFAULT_DATA_DIR = "test/data-2026-02-05-20-15-05-batch-0000"
CARL_USER_ID = "b7c60682-4815-4d9d-8ebe-66c6cd24eff9"

# Skip the starter project
SKIP_PROJECT_UUIDS = {"0198b90d-bb8b-77d0-b168-42797c8b908a"}

# Claude project UUID → Syntax knowledge_project mapping
# Set to None to create new; set to int to map to existing project_id
# Carl: update these if you want to map any Claude project to existing Syntax projects
PROJECT_MAPPING_OVERRIDES = {
    # Example: "019c005b-6a46-754a-9f68-aa3bd7879e66": 1,  # Map "AMCF" to existing project_id=1
}

# Project category/icon defaults for new Claude projects
PROJECT_DEFAULTS = {
    "category": "claude_project",
    "color": "#8B5CF6",  # Purple for Claude projects
    "icon": "🤖",
}


# =============================================================================
# HELPERS
# =============================================================================

def extract_text_from_message(msg):
    """
    Extract plain text content from a Claude message.
    Priority: msg['text'] field, then extract from msg['content'] blocks.
    """
    # Try the top-level text field first
    text = msg.get("text")
    if text and text.strip():
        return text.strip()

    # Fall back to extracting from content blocks
    content = msg.get("content")
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                block_type = block.get("type", "")
                if block_type == "text" and block.get("text"):
                    parts.append(block["text"])
                elif block_type == "tool_use":
                    # Preserve tool use as metadata-style text
                    tool_name = block.get("name", "unknown_tool")
                    tool_input = block.get("input", {})
                    parts.append(f"[Tool: {tool_name}]")
                elif block_type == "tool_result":
                    result_content = block.get("content", "")
                    if isinstance(result_content, str) and result_content:
                        parts.append(f"[Tool result: {result_content[:500]}]")
            elif isinstance(block, str):
                parts.append(block)
        
        if parts:
            return "\n".join(parts).strip()

    return ""


def extract_attachment_metadata(msg):
    """Extract attachment and file info as JSON metadata."""
    metadata = {}

    attachments = msg.get("attachments")
    if attachments and len(attachments) > 0:
        metadata["attachments"] = []
        for att in attachments:
            att_info = {
                "file_name": att.get("file_name"),
                "file_size": att.get("file_size"),
                "file_type": att.get("file_type"),
            }
            # Include extracted content preview (not full content to save space)
            extracted = att.get("extracted_content", "")
            if extracted:
                att_info["extracted_content_preview"] = extracted[:500]
                att_info["extracted_content_length"] = len(extracted)
            metadata["attachments"].append(att_info)

    files = msg.get("files")
    if files and len(files) > 0:
        metadata["files"] = [
            {"file_name": f.get("file_name")} for f in files
        ]

    return metadata if metadata else {}


def map_sender_to_role(sender):
    """Map Claude export sender to Syntax role."""
    if sender == "human":
        return "user"
    elif sender == "assistant":
        return "assistant"
    return sender or "unknown"


def sha1_hash(content):
    """Generate SHA1 hash for deduplication."""
    return hashlib.sha1(content.encode("utf-8")).hexdigest()


def fmt(count):
    """Format number with commas."""
    return f"{count:,}"


# =============================================================================
# DATABASE OPERATIONS
# =============================================================================

def connect():
    """Connect to Syntax Prime database."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        return conn
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        sys.exit(1)


def get_existing_thread_uuids(cursor):
    """Get all existing conversation thread UUIDs for dedup."""
    cursor.execute("SELECT id FROM conversation_threads")
    return {str(row[0]) for row in cursor.fetchall()}


def get_existing_message_uuids(cursor):
    """Get all existing message UUIDs for dedup."""
    cursor.execute("SELECT id FROM conversation_messages")
    return {str(row[0]) for row in cursor.fetchall()}


def get_existing_project_names(cursor):
    """Get existing knowledge_project names."""
    cursor.execute("SELECT id, name FROM knowledge_projects")
    return {row[1]: row[0] for row in cursor.fetchall()}


def ensure_claude_source(cursor):
    """Ensure 'Claude Conversation' knowledge source exists."""
    cursor.execute("SELECT id FROM knowledge_sources WHERE name = 'Claude Conversation'")
    row = cursor.fetchone()
    if row:
        return row[0]

    cursor.execute("""
        INSERT INTO knowledge_sources (name, source_type, description, is_active)
        VALUES ('Claude Conversation', 'conversation', 'Imported from Claude.ai data export', TRUE)
        RETURNING id
    """)
    return cursor.fetchone()[0]


def ensure_claude_docs_source(cursor):
    """Ensure 'Claude Project Doc' knowledge source exists."""
    cursor.execute("SELECT id FROM knowledge_sources WHERE name = 'Claude Project Doc'")
    row = cursor.fetchone()
    if row:
        return row[0]

    cursor.execute("""
        INSERT INTO knowledge_sources (name, source_type, description, is_active)
        VALUES ('Claude Project Doc', 'document', 'Project documentation from Claude.ai', TRUE)
        RETURNING id
    """)
    return cursor.fetchone()[0]


def ensure_claude_memory_source(cursor):
    """Ensure 'Claude Memory' knowledge source exists."""
    cursor.execute("SELECT id FROM knowledge_sources WHERE name = 'Claude Memory'")
    row = cursor.fetchone()
    if row:
        return row[0]

    cursor.execute("""
        INSERT INTO knowledge_sources (name, source_type, description, is_active)
        VALUES ('Claude Memory', 'memory', 'Memory snapshots from Claude.ai', TRUE)
        RETURNING id
    """)
    return cursor.fetchone()[0]


# =============================================================================
# IMPORT: PROJECTS
# =============================================================================

def import_projects(cursor, data_dir, dry_run=False):
    """Import Claude projects into knowledge_projects."""
    print("\n" + "=" * 70)
    print("📂 PHASE 1: IMPORTING PROJECTS")
    print("=" * 70)

    projects_path = os.path.join(data_dir, "projects.json")
    if not os.path.exists(projects_path):
        print("  ⚠️ No projects.json found, skipping.")
        return {}

    with open(projects_path, "r", encoding="utf-8") as f:
        projects = json.load(f)

    existing_names = get_existing_project_names(cursor)
    claude_uuid_to_project_id = {}
    created = 0
    skipped = 0
    mapped = 0

    for proj in projects:
        uuid = proj["uuid"]
        name = proj["name"]

        # Skip starter projects
        if uuid in SKIP_PROJECT_UUIDS:
            print(f"  ⏭️  Skipping starter: {name}")
            skipped += 1
            continue

        # Check override mapping
        if uuid in PROJECT_MAPPING_OVERRIDES:
            override_id = PROJECT_MAPPING_OVERRIDES[uuid]
            if override_id is not None:
                claude_uuid_to_project_id[uuid] = override_id
                print(f"  🔗 Mapped '{name}' → existing project_id={override_id}")
                mapped += 1
                continue

        # Check if name already exists
        if name in existing_names:
            claude_uuid_to_project_id[uuid] = existing_names[name]
            print(f"  ✅ Already exists: '{name}' (id={existing_names[name]})")
            mapped += 1
            continue

        # Create new project
        description = proj.get("description", "") or ""
        prompt_template = proj.get("prompt_template", "") or ""
        created_at = proj.get("created_at")

        # Build instructions from prompt_template if present
        instructions = prompt_template if prompt_template else None

        if not dry_run:
            cursor.execute("""
                INSERT INTO knowledge_projects 
                    (name, display_name, description, category, is_active,
                     instructions, color, icon, created_at, updated_at)
                VALUES (%s, %s, %s, %s, TRUE, %s, %s, %s, %s, NOW())
                RETURNING id
            """, (
                name, name, description,
                PROJECT_DEFAULTS["category"],
                instructions,
                PROJECT_DEFAULTS["color"],
                PROJECT_DEFAULTS["icon"],
                created_at,
            ))
            new_id = cursor.fetchone()[0]
            claude_uuid_to_project_id[uuid] = new_id
            existing_names[name] = new_id
        else:
            claude_uuid_to_project_id[uuid] = -1  # Placeholder for dry run

        print(f"  ✨ Created: '{name}'")
        created += 1

    print(f"\n  📊 Projects: {created} created, {mapped} mapped, {skipped} skipped")
    return claude_uuid_to_project_id


# =============================================================================
# IMPORT: PROJECT DOCS → KNOWLEDGE ENTRIES
# =============================================================================

def import_project_docs(cursor, data_dir, project_map, dry_run=False):
    """Import project docs into knowledge_entries."""
    print("\n" + "=" * 70)
    print("📄 PHASE 2: IMPORTING PROJECT DOCS")
    print("=" * 70)

    projects_path = os.path.join(data_dir, "projects.json")
    if not os.path.exists(projects_path):
        print("  ⚠️ No projects.json found, skipping.")
        return

    with open(projects_path, "r", encoding="utf-8") as f:
        projects = json.load(f)

    source_id = ensure_claude_docs_source(cursor) if not dry_run else -1
    imported = 0
    skipped = 0

    for proj in projects:
        uuid = proj["uuid"]
        if uuid in SKIP_PROJECT_UUIDS:
            continue

        project_id = project_map.get(uuid)
        docs = proj.get("docs", [])

        for doc in docs:
            content = doc.get("content", "")
            if not content or not content.strip():
                skipped += 1
                continue

            filename = doc.get("filename", "untitled")
            content_hash = sha1_hash(content)

            # Check for duplicate
            if not dry_run:
                cursor.execute("SELECT id FROM knowledge_entries WHERE sha1 = %s", (content_hash,))
                if cursor.fetchone():
                    skipped += 1
                    continue

                word_count = len(content.split())
                cursor.execute("""
                    INSERT INTO knowledge_entries
                        (source_id, title, project_id, content, content_type, sha1,
                         user_id, word_count, relevance_score, processed,
                         created_at, updated_at,
                         search_vector)
                    VALUES (
                        %s, %s, %s, %s, 'document', %s,
                        %s, %s, 7.0, TRUE,
                        %s, NOW(),
                        setweight(to_tsvector('english', COALESCE(%s, '')), 'A') ||
                        setweight(to_tsvector('english', COALESCE(%s, '')), 'C')
                    )
                """, (
                    source_id, filename, project_id, content, content_hash,
                    CARL_USER_ID, word_count,
                    doc.get("created_at"),
                    filename, content,
                ))

            imported += 1
            print(f"  📄 {proj['name']}/{filename} ({len(content):,} chars)")

    print(f"\n  📊 Docs: {imported} imported, {skipped} skipped (empty/duplicate)")


# =============================================================================
# IMPORT: MEMORIES → KNOWLEDGE ENTRIES
# =============================================================================

def import_memories(cursor, data_dir, project_map, dry_run=False):
    """Import Claude memory snapshots into knowledge_entries."""
    print("\n" + "=" * 70)
    print("🧠 PHASE 3: IMPORTING MEMORIES")
    print("=" * 70)

    memories_path = os.path.join(data_dir, "memories.json")
    if not os.path.exists(memories_path):
        print("  ⚠️ No memories.json found, skipping.")
        return

    with open(memories_path, "r", encoding="utf-8") as f:
        memories = json.load(f)

    if not memories:
        print("  ⚠️ Empty memories file, skipping.")
        return

    source_id = ensure_claude_memory_source(cursor) if not dry_run else -1
    imported = 0

    for mem_entry in memories:
        # Global conversation memory
        conv_memory = mem_entry.get("conversations_memory", "")
        if conv_memory and conv_memory.strip():
            content_hash = sha1_hash(conv_memory)
            if not dry_run:
                cursor.execute("SELECT id FROM knowledge_entries WHERE sha1 = %s", (content_hash,))
                if not cursor.fetchone():
                    cursor.execute("""
                        INSERT INTO knowledge_entries
                            (source_id, title, content, content_type, sha1,
                             user_id, word_count, relevance_score, processed,
                             created_at, updated_at,
                             search_vector)
                        VALUES (
                            %s, %s, %s, 'memory', %s,
                            %s, %s, 8.0, TRUE,
                            NOW(), NOW(),
                            setweight(to_tsvector('english', COALESCE(%s, '')), 'A') ||
                            setweight(to_tsvector('english', COALESCE(%s, '')), 'C')
                        )
                    """, (
                        source_id,
                        "Claude Global Memory Snapshot",
                        conv_memory, content_hash,
                        CARL_USER_ID, len(conv_memory.split()),
                        "Claude Global Memory Snapshot",
                        conv_memory,
                    ))
                    imported += 1
                    print(f"  🧠 Global memory ({len(conv_memory):,} chars)")

        # Per-project memories
        project_memories = mem_entry.get("project_memories", {})
        for proj_uuid, proj_memory in project_memories.items():
            if not proj_memory or not proj_memory.strip():
                continue

            content_hash = sha1_hash(proj_memory)
            project_id = project_map.get(proj_uuid)

            # Look up project name for title
            proj_name = proj_uuid[:12]  # fallback
            for p_uuid, p_id in project_map.items():
                if p_uuid == proj_uuid:
                    proj_name = proj_uuid
                    break

            if not dry_run:
                cursor.execute("SELECT id FROM knowledge_entries WHERE sha1 = %s", (content_hash,))
                if not cursor.fetchone():
                    cursor.execute("""
                        INSERT INTO knowledge_entries
                            (source_id, title, project_id, content, content_type, sha1,
                             user_id, word_count, relevance_score, processed,
                             created_at, updated_at,
                             search_vector)
                        VALUES (
                            %s, %s, %s, %s, 'memory', %s,
                            %s, %s, 8.0, TRUE,
                            NOW(), NOW(),
                            setweight(to_tsvector('english', COALESCE(%s, '')), 'A') ||
                            setweight(to_tsvector('english', COALESCE(%s, '')), 'C')
                        )
                    """, (
                        source_id,
                        f"Claude Project Memory: {proj_uuid[:20]}",
                        project_id,
                        proj_memory, content_hash,
                        CARL_USER_ID, len(proj_memory.split()),
                        f"Claude Project Memory",
                        proj_memory,
                    ))
                    imported += 1
                    print(f"  🧠 Project memory: {proj_uuid[:20]}... ({len(proj_memory):,} chars)")

    print(f"\n  📊 Memories: {imported} imported")


# =============================================================================
# IMPORT: CONVERSATIONS → conversation_threads + conversation_messages
# =============================================================================

def import_conversations(cursor, data_dir, dry_run=False):
    """Import conversations and messages."""
    print("\n" + "=" * 70)
    print("💬 PHASE 4: IMPORTING CONVERSATIONS & MESSAGES")
    print("=" * 70)

    conv_path = os.path.join(data_dir, "conversations.json")
    if not os.path.exists(conv_path):
        print("  ❌ conversations.json not found!")
        return

    print(f"  Loading conversations.json...")
    with open(conv_path, "r", encoding="utf-8") as f:
        conversations = json.load(f)

    print(f"  Total conversations in export: {fmt(len(conversations))}")

    # Get existing UUIDs for dedup
    existing_threads = get_existing_thread_uuids(cursor) if not dry_run else set()
    existing_messages = get_existing_message_uuids(cursor) if not dry_run else set()

    print(f"  Existing threads in DB: {fmt(len(existing_threads))}")
    print(f"  Existing messages in DB: {fmt(len(existing_messages))}")

    # Stats
    stats = {
        "threads_created": 0,
        "threads_skipped": 0,
        "messages_created": 0,
        "messages_skipped": 0,
        "messages_empty": 0,
        "errors": 0,
    }

    total = len(conversations)
    conn = cursor.connection

    for i, conv in enumerate(conversations):
        conv_uuid = conv["uuid"]

        # Skip if thread already exists
        if conv_uuid in existing_threads:
            stats["threads_skipped"] += 1
            continue

        # Extract thread data
        name = conv.get("name", "") or ""
        summary = conv.get("summary", "") or ""
        created_at = conv.get("created_at")
        updated_at = conv.get("updated_at")
        messages = conv.get("chat_messages", [])
        message_count = len(messages)

        # Find last message timestamp
        last_message_at = updated_at
        if messages:
            last_msg_time = messages[-1].get("created_at")
            if last_msg_time:
                last_message_at = last_msg_time

        if not dry_run:
            try:
                # Insert thread
                cursor.execute("""
                    INSERT INTO conversation_threads
                        (id, user_id, title, summary, platform, status,
                         message_count, created_at, updated_at,
                         last_message_at, personality, last_activity)
                    VALUES (%s, %s, %s, %s, 'claude.ai', 'archived',
                            %s, %s, %s, %s, 'claude', %s)
                    ON CONFLICT (id) DO NOTHING
                """, (
                    conv_uuid, CARL_USER_ID,
                    name[:255] if name else None,
                    summary if summary else None,
                    message_count,
                    created_at, updated_at,
                    last_message_at,
                    last_message_at,
                ))

                # Prepare all messages for this conversation
                msg_rows = []
                conv_msg_empty = 0
                for msg in messages:
                    msg_uuid = msg.get("uuid")
                    if not msg_uuid or msg_uuid in existing_messages:
                        if msg_uuid in existing_messages:
                            stats["messages_skipped"] += 1
                        continue

                    text_content = extract_text_from_message(msg)
                    if not text_content:
                        conv_msg_empty += 1
                        text_content = ""

                    role = map_sender_to_role(msg.get("sender"))
                    metadata = extract_attachment_metadata(msg)

                    msg_rows.append((
                        msg_uuid, conv_uuid, CARL_USER_ID,
                        role, text_content,
                        msg.get("created_at"), msg.get("updated_at"),
                        json.dumps(metadata) if metadata else '{}',
                    ))

                # Batch insert messages
                if msg_rows:
                    psycopg2.extras.execute_batch(cursor, """
                        INSERT INTO conversation_messages
                            (id, thread_id, user_id, role, content,
                             content_type, created_at, updated_at, metadata)
                        VALUES (%s, %s, %s, %s, %s,
                                'text', %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING
                    """, msg_rows)

                # Commit this conversation
                conn.commit()

                stats["threads_created"] += 1
                stats["messages_created"] += len(msg_rows)
                stats["messages_empty"] += conv_msg_empty
                existing_threads.add(conv_uuid)
                for row in msg_rows:
                    existing_messages.add(row[0])

            except Exception as e:
                conn.rollback()
                stats["errors"] += 1
                if stats["errors"] <= 10:
                    print(f"\n  ❌ Error ({conv_uuid[:12]}): {e}")
                continue
        else:
            stats["threads_created"] += 1
            stats["messages_created"] += len(messages)

        # Progress every 25 conversations
        if (i + 1) % 25 == 0 or i == total - 1:
            progress = (i + 1) / total * 100
            print(f"  📦 [{progress:5.1f}%] {i+1}/{total} "
                  f"| {fmt(stats['threads_created'])} threads "
                  f"| {fmt(stats['messages_created'])} messages", end="\r")

    print()  # Newline after progress
    print(f"\n  📊 CONVERSATION IMPORT RESULTS:")
    print(f"     Threads created:  {fmt(stats['threads_created'])}")
    print(f"     Threads skipped:  {fmt(stats['threads_skipped'])} (already existed)")
    print(f"     Messages created: {fmt(stats['messages_created'])}")
    print(f"     Messages skipped: {fmt(stats['messages_skipped'])} (already existed)")
    print(f"     Empty messages:   {fmt(stats['messages_empty'])} (preserved with empty content)")
    print(f"     Errors:           {fmt(stats['errors'])}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Import Claude data export into Syntax Prime V2")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to database")
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR, help="Path to Claude export directory")
    parser.add_argument("--skip-conversations", action="store_true", help="Skip conversation import")
    parser.add_argument("--skip-projects", action="store_true", help="Skip project import")
    parser.add_argument("--skip-memories", action="store_true", help="Skip memory import")
    parser.add_argument("--skip-docs", action="store_true", help="Skip project docs import")
    args = parser.parse_args()

    print("=" * 70)
    print("🚀 CLAUDE DATA EXPORT → SYNTAX PRIME V2 IMPORT")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📁 Data: {args.data_dir}")
    print(f"👤 User: {CARL_USER_ID}")
    if args.dry_run:
        print("⚠️  DRY RUN MODE - No database changes will be made")
    print("=" * 70)

    # Verify data directory
    if not os.path.exists(args.data_dir):
        print(f"❌ Data directory not found: {args.data_dir}")
        sys.exit(1)

    # List files
    files = os.listdir(args.data_dir)
    print(f"\n📂 Files found: {', '.join(files)}")

    # Connect
    print(f"\n📡 Connecting to database...")
    conn = connect()
    cursor = conn.cursor()
    print("✅ Connected!")

    try:
        # Phase 1: Projects
        project_map = {}
        if not args.skip_projects:
            project_map = import_projects(cursor, args.data_dir, args.dry_run)
            if not args.dry_run:
                conn.commit()

        # Phase 2: Project Docs
        if not args.skip_docs:
            import_project_docs(cursor, args.data_dir, project_map, args.dry_run)
            if not args.dry_run:
                conn.commit()

        # Phase 3: Memories
        if not args.skip_memories:
            import_memories(cursor, args.data_dir, project_map, args.dry_run)
            if not args.dry_run:
                conn.commit()

        # Phase 4: Conversations & Messages
        if not args.skip_conversations:
            import_conversations(cursor, args.data_dir, args.dry_run)

        # Final commit
        if not args.dry_run:
            conn.commit()

        # Summary counts
        print("\n" + "=" * 70)
        print("📊 FINAL DATABASE COUNTS")
        print("=" * 70)

        if not args.dry_run:
            cursor.execute("SELECT COUNT(*) FROM knowledge_projects")
            print(f"  knowledge_projects:    {fmt(cursor.fetchone()[0])}")

            cursor.execute("SELECT COUNT(*) FROM knowledge_entries")
            print(f"  knowledge_entries:     {fmt(cursor.fetchone()[0])}")

            cursor.execute("SELECT COUNT(*) FROM conversation_threads")
            print(f"  conversation_threads:  {fmt(cursor.fetchone()[0])}")

            cursor.execute("SELECT COUNT(*) FROM conversation_messages")
            print(f"  conversation_messages: {fmt(cursor.fetchone()[0])}")

            cursor.execute("""
                SELECT platform, COUNT(*) 
                FROM conversation_threads 
                GROUP BY platform 
                ORDER BY COUNT(*) DESC
            """)
            print(f"\n  Threads by platform:")
            for row in cursor.fetchall():
                print(f"    {row[0]}: {fmt(row[1])}")

        print("\n" + "=" * 70)
        print("✅ Import complete!")
        print("=" * 70)

    except Exception as e:
        conn.rollback()
        print(f"\n❌ IMPORT FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()