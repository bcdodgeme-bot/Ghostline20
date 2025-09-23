#!/usr/bin/env python3
"""
Import Ghostline knowledge base into Syntax Prime database
"""

import json
import psycopg2
import sys
from datetime import datetime
import hashlib
import os

# Database configuration
DATABASE_URL = "postgresql://postgres:RcldqFcBwHuiuqpiCemgiTjfuJcvOJLH@ballast.proxy.rlwy.net:12126/railway"

def connect_to_database():
    """Connect to the PostgreSQL database"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"Error connecting to database: {e}")
        sys.exit(1)

def get_project_id(cursor, project_name):
    """Get project ID, return None if not found"""
    if not project_name or project_name == "no_project":
        return None
    
    cursor.execute("SELECT id FROM knowledge_projects WHERE name = %s", (project_name,))
    result = cursor.fetchone()
    return result[0] if result else None

def get_source_id(cursor, source_name):
    """Get source ID, return None if not found"""
    if not source_name:
        return None
        
    cursor.execute("SELECT id FROM knowledge_sources WHERE name = %s", (source_name,))
    result = cursor.fetchone()
    return result[0] if result else None

def extract_key_topics(content, title=""):
    """Extract basic topics from content"""
    text = (title + " " + content).lower()
    topics = []
    
    # Simple keyword-based topic extraction
    if any(word in text for word in ['business', 'strategy', 'marketing', 'sales', 'revenue']):
        topics.append('business')
    if any(word in text for word in ['health', 'wellness', 'fitness', 'nutrition']):
        topics.append('health')
    if any(word in text for word in ['development', 'growth', 'learning', 'skill']):
        topics.append('personal_development')
    if any(word in text for word in ['amcf', 'muslim', 'giving', 'nonprofit']):
        topics.append('amcf')
    
    return topics

def import_knowledge_entry(cursor, entry):
    """Import a single knowledge entry"""
    try:
        # Extract data from JSONL entry
        source_name = entry.get('source', '')
        title = entry.get('title', '')[:500]  # Truncate to fit field
        project_name = entry.get('project', '')
        conversation_id = entry.get('conversation_id', '')
        create_time = entry.get('create_time', 0)
        content = entry.get('content', '')
        content_type = entry.get('content_type', 'unknown')
        sha1_hash = entry.get('sha1', '')
        
        # Skip if no content
        if not content or not content.strip():
            return False, "No content"
        
        # Generate hash if missing
        if not sha1_hash:
            sha1_hash = hashlib.sha1(content.encode('utf-8')).hexdigest()
        
        # Check for duplicates
        cursor.execute("SELECT id FROM knowledge_entries WHERE sha1 = %s", (sha1_hash,))
        if cursor.fetchone():
            return False, "Duplicate"
        
        # Get IDs
        project_id = get_project_id(cursor, project_name)
        source_id = get_source_id(cursor, source_name)
        
        # Extract metadata
        key_topics = extract_key_topics(content, title)
        word_count = len(content.split()) if content else 0
        
        # Insert entry
        cursor.execute("""
            INSERT INTO knowledge_entries (
                source_id, title, project_id, conversation_id, create_time,
                content, content_type, sha1, key_topics, word_count,
                relevance_score, processed, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s
            )
        """, (
            source_id, title, project_id, conversation_id, create_time,
            content, content_type, sha1_hash, json.dumps(key_topics), word_count,
            5.0, True, datetime.now(), datetime.now()
        ))
        
        return True, "Success"
        
    except Exception as e:
        return False, f"Error: {e}"

def import_jsonl_file(filename, batch_size=100):
    """Import a JSONL file"""
    conn = connect_to_database()
    cursor = conn.cursor()
    
    print(f"Importing {filename}...")
    
    imported_count = 0
    error_count = 0
    duplicate_count = 0
    
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            batch = []
            
            for line_num, line in enumerate(file, 1):
                line = line.strip()
                if not line:
                    continue
                
                try:
                    entry = json.loads(line)
                    batch.append((entry, line_num))
                    
                    if len(batch) >= batch_size:
                        # Process batch
                        for entry_data, entry_line in batch:
                            success, message = import_knowledge_entry(cursor, entry_data)
                            if success:
                                imported_count += 1
                            elif "Duplicate" in message:
                                duplicate_count += 1
                            else:
                                error_count += 1
                                print(f"Line {entry_line}: {message}")
                        
                        # Commit batch
                        conn.commit()
                        print(f"Processed {line_num} lines: {imported_count} imported, {duplicate_count} duplicates, {error_count} errors")
                        batch = []
                        
                except json.JSONDecodeError as e:
                    print(f"JSON error on line {line_num}: {e}")
                    error_count += 1
            
            # Process final batch
            for entry_data, entry_line in batch:
                success, message = import_knowledge_entry(cursor, entry_data)
                if success:
                    imported_count += 1
                elif "Duplicate" in message:
                    duplicate_count += 1
                else:
                    error_count += 1
                    print(f"Line {entry_line}: {message}")
            
            conn.commit()
    
    except FileNotFoundError:
        print(f"File not found: {filename}")
        return 0, 1, 0
    
    finally:
        cursor.close()
        conn.close()
    
    print(f"Completed {filename}: {imported_count} imported, {duplicate_count} duplicates, {error_count} errors")
    return imported_count, error_count, duplicate_count

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python import_knowledge.py <jsonl_file>")
        sys.exit(1)
    
    filename = sys.argv[1]
    if not os.path.exists(filename):
        print(f"File not found: {filename}")
        sys.exit(1)
    
    imported, errors, duplicates = import_jsonl_file(filename)
    print(f"Final result: {imported} entries imported, {duplicates} duplicates skipped, {errors} errors")
