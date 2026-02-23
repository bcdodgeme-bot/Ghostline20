#!/usr/bin/env python3
"""
Inspect Claude Data Export
Scans the exported data directory and reports:
- File types and counts
- File sizes
- JSON structure samples
- Conversation counts and metadata
- Content statistics

Usage: python inspect_claude_export.py /path/to/data-folder
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def format_size(size_bytes):
    """Format bytes to human readable"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def inspect_directory(base_path):
    """Walk the directory and catalog everything"""
    print("=" * 80)
    print(f"🔍 CLAUDE DATA EXPORT INSPECTION")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📁 Path: {base_path}")
    print("=" * 80)

    if not os.path.exists(base_path):
        print(f"❌ Path does not exist: {base_path}")
        return

    # --- Phase 1: Directory Structure ---
    print("\n📂 DIRECTORY STRUCTURE (top 3 levels):")
    print("-" * 60)
    
    dir_count = 0
    file_count = 0
    file_types = defaultdict(lambda: {"count": 0, "total_size": 0})
    all_files = []
    
    for root, dirs, files in os.walk(base_path):
        depth = root.replace(str(base_path), "").count(os.sep)
        if depth <= 3:
            indent = "  " * depth
            print(f"{indent}📁 {os.path.basename(root)}/  ({len(files)} files, {len(dirs)} subdirs)")
        
        dir_count += 1
        for f in files:
            file_count += 1
            filepath = os.path.join(root, f)
            size = os.path.getsize(filepath)
            ext = os.path.splitext(f)[1].lower() or "(no ext)"
            
            file_types[ext]["count"] += 1
            file_types[ext]["total_size"] += size
            all_files.append({
                "path": filepath,
                "name": f,
                "ext": ext,
                "size": size,
                "rel_path": os.path.relpath(filepath, base_path)
            })

    print(f"\n📊 TOTALS: {dir_count} directories, {file_count} files")
    total_size = sum(f["size"] for f in all_files)
    print(f"💾 Total size: {format_size(total_size)}")

    # --- Phase 2: File Type Breakdown ---
    print("\n📋 FILE TYPES:")
    print("-" * 60)
    for ext, info in sorted(file_types.items(), key=lambda x: -x[1]["total_size"]):
        print(f"  {ext:15s}  {info['count']:5d} files  {format_size(info['total_size']):>10s}")

    # --- Phase 3: Largest Files ---
    print("\n📏 LARGEST FILES (top 20):")
    print("-" * 60)
    sorted_files = sorted(all_files, key=lambda x: -x["size"])
    for f in sorted_files[:20]:
        print(f"  {format_size(f['size']):>10s}  {f['rel_path']}")

    # --- Phase 4: Inspect JSON files ---
    json_files = [f for f in all_files if f["ext"] in (".json", ".jsonl")]
    
    if json_files:
        print(f"\n🔎 JSON FILE INSPECTION ({len(json_files)} files):")
        print("=" * 80)
        
        for jf in sorted(json_files, key=lambda x: -x["size"])[:30]:  # Inspect top 30 by size
            print(f"\n{'─' * 70}")
            print(f"📄 {jf['rel_path']}  ({format_size(jf['size'])})")
            print(f"{'─' * 70}")
            
            try:
                with open(jf["path"], "r", encoding="utf-8") as f:
                    # Check if JSONL
                    first_line = f.readline().strip()
                    f.seek(0)
                    
                    if jf["ext"] == ".jsonl" or (first_line and not first_line.startswith("[")):
                        # JSONL format
                        inspect_jsonl(jf["path"])
                    else:
                        # Regular JSON
                        inspect_json(jf["path"])
                        
            except Exception as e:
                print(f"  ❌ Error reading: {e}")

    # --- Phase 5: Look for conversation patterns ---
    print("\n\n🗣️ CONVERSATION PATTERN ANALYSIS:")
    print("=" * 80)
    analyze_conversation_patterns(all_files, base_path)
    
    print("\n" + "=" * 80)
    print("✅ Inspection complete!")


def inspect_json(filepath):
    """Inspect a regular JSON file"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        if isinstance(data, list):
            print(f"  Type: Array with {len(data)} items")
            if data:
                print(f"  First item type: {type(data[0]).__name__}")
                if isinstance(data[0], dict):
                    print(f"  First item keys: {list(data[0].keys())}")
                    # Show sample of first item (truncated values)
                    print(f"  Sample item:")
                    show_dict_sample(data[0], indent=4)
                    
                    # If items have 'uuid' or 'id', count unique
                    for id_key in ['uuid', 'id', 'conversation_id', 'chat_id']:
                        if id_key in data[0]:
                            unique_ids = len(set(item.get(id_key) for item in data if isinstance(item, dict)))
                            print(f"  Unique '{id_key}' values: {unique_ids}")
                    
                    # Check for nested conversations/messages
                    for key in data[0]:
                        val = data[0][key]
                        if isinstance(val, list) and len(val) > 0:
                            print(f"  '{key}' is a list with {len(val)} items")
                            if isinstance(val[0], dict):
                                print(f"    Sub-item keys: {list(val[0].keys())}")
                        elif isinstance(val, dict):
                            print(f"  '{key}' is a dict with keys: {list(val.keys())[:10]}")
                            
        elif isinstance(data, dict):
            print(f"  Type: Object with {len(data)} keys")
            print(f"  Top-level keys: {list(data.keys())[:20]}")
            show_dict_sample(data, indent=4)
        else:
            print(f"  Type: {type(data).__name__}")
            
    except json.JSONDecodeError as e:
        print(f"  ❌ Invalid JSON: {e}")
    except Exception as e:
        print(f"  ❌ Error: {e}")


def inspect_jsonl(filepath):
    """Inspect a JSONL file"""
    try:
        line_count = 0
        sample_keys = set()
        first_item = None
        errors = 0
        
        with open(filepath, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                    line_count += 1
                    if isinstance(item, dict):
                        sample_keys.update(item.keys())
                        if first_item is None:
                            first_item = item
                except json.JSONDecodeError:
                    errors += 1
                    if errors <= 3:
                        print(f"  ⚠️ Bad JSON on line {i+1}: {line[:100]}...")
        
        print(f"  Format: JSONL with {line_count} entries ({errors} errors)")
        if sample_keys:
            print(f"  All keys found: {sorted(sample_keys)}")
        if first_item:
            print(f"  Sample entry:")
            show_dict_sample(first_item, indent=4)
            
    except Exception as e:
        print(f"  ❌ Error: {e}")


def show_dict_sample(d, indent=2, max_depth=2, current_depth=0):
    """Show a sample of a dict with truncated values"""
    if current_depth >= max_depth:
        return
    
    prefix = " " * indent
    for key, value in list(d.items())[:15]:  # Max 15 keys
        if isinstance(value, str):
            display = value[:120] + "..." if len(value) > 120 else value
            display = display.replace("\n", "\\n")
            print(f"{prefix}• {key}: \"{display}\"")
        elif isinstance(value, (int, float, bool)):
            print(f"{prefix}• {key}: {value}")
        elif isinstance(value, list):
            print(f"{prefix}• {key}: [{len(value)} items]")
            if value and isinstance(value[0], dict) and current_depth < max_depth - 1:
                print(f"{prefix}  First item keys: {list(value[0].keys())[:10]}")
        elif isinstance(value, dict):
            print(f"{prefix}• {key}: {{dict with {len(value)} keys}}")
            if current_depth < max_depth - 1:
                show_dict_sample(value, indent + 4, max_depth, current_depth + 1)
        elif value is None:
            print(f"{prefix}• {key}: null")
        else:
            print(f"{prefix}• {key}: ({type(value).__name__})")


def analyze_conversation_patterns(all_files, base_path):
    """Look for conversation-like structures in the data"""
    
    # Check common Claude export patterns
    json_files = [f for f in all_files if f["ext"] == ".json"]
    jsonl_files = [f for f in all_files if f["ext"] == ".jsonl"]
    
    print(f"\n  JSON files: {len(json_files)}")
    print(f"  JSONL files: {len(jsonl_files)}")
    
    # Try to find the main conversation file(s)
    conversation_count = 0
    message_count = 0
    projects_found = set()
    date_range = {"earliest": None, "latest": None}
    
    for jf in json_files[:10]:  # Check first 10 JSON files
        try:
            with open(jf["path"], "r", encoding="utf-8") as f:
                data = json.load(f)
            
            if isinstance(data, list) and data:
                first = data[0]
                if isinstance(first, dict):
                    # Look for conversation indicators
                    has_messages = any(k in first for k in ['chat_messages', 'messages', 'content'])
                    has_uuid = any(k in first for k in ['uuid', 'id', 'conversation_id'])
                    has_name = any(k in first for k in ['name', 'title'])
                    has_project = any(k in first for k in ['project', 'project_uuid', 'project_id'])
                    
                    if has_uuid:
                        conversation_count += len(data)
                        print(f"\n  📝 Found conversation-like data in: {jf['rel_path']}")
                        print(f"     Items: {len(data)}")
                        print(f"     Keys: {list(first.keys())}")
                        
                        if has_messages:
                            # Count messages
                            for conv in data[:5]:  # Sample first 5
                                for msg_key in ['chat_messages', 'messages']:
                                    if msg_key in conv and isinstance(conv[msg_key], list):
                                        message_count += len(conv[msg_key])
                        
                        if has_project:
                            for conv in data:
                                for proj_key in ['project', 'project_uuid', 'project_id']:
                                    if proj_key in conv and conv[proj_key]:
                                        projects_found.add(str(conv[proj_key]))
                        
                        # Date range
                        for conv in data:
                            for date_key in ['created_at', 'updated_at', 'create_time']:
                                if date_key in conv and conv[date_key]:
                                    try:
                                        ts = conv[date_key]
                                        if isinstance(ts, (int, float)):
                                            dt = datetime.fromtimestamp(ts)
                                        else:
                                            dt = datetime.fromisoformat(str(ts).replace('Z', '+00:00'))
                                        
                                        if date_range["earliest"] is None or dt < date_range["earliest"]:
                                            date_range["earliest"] = dt
                                        if date_range["latest"] is None or dt > date_range["latest"]:
                                            date_range["latest"] = dt
                                    except:
                                        pass
                                        
        except Exception as e:
            pass
    
    # Summary
    if conversation_count > 0:
        print(f"\n  📊 CONVERSATION SUMMARY:")
        print(f"     Conversations found: ~{conversation_count}")
        if message_count:
            print(f"     Messages sampled: ~{message_count}")
        if projects_found:
            print(f"     Projects referenced: {len(projects_found)}")
            for p in sorted(projects_found)[:20]:
                print(f"       • {p}")
        if date_range["earliest"]:
            print(f"     Date range: {date_range['earliest'].strftime('%Y-%m-%d')} → {date_range['latest'].strftime('%Y-%m-%d')}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # Default path
        default_path = "test/data-2026-02-05-20-15-05-batch-0000"
        if os.path.exists(default_path):
            inspect_directory(default_path)
        else:
            print("Usage: python inspect_claude_export.py /path/to/data-folder")
            print(f"  (tried default: {default_path})")
    else:
        inspect_directory(sys.argv[1])