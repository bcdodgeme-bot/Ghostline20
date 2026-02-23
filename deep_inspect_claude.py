#!/usr/bin/env python3
"""
Deep Inspection of Claude Export - Phase 2
Focuses on:
1. All unique keys across ALL conversations (not just first)
2. How conversations link to projects
3. Message content vs text field differences
4. Sender types and patterns
5. Attachment/file structures
6. Project details and doc contents
"""

import json
import os
import sys
from collections import defaultdict, Counter
from datetime import datetime


DATA_DIR = "test/data-2026-02-05-20-15-05-batch-0000"


def deep_inspect():
    print("=" * 80)
    print("🔬 DEEP INSPECTION - Claude Export")
    print("=" * 80)

    # =========================================================================
    # 1. CONVERSATIONS - Full key analysis
    # =========================================================================
    print("\n\n📨 CONVERSATIONS DEEP DIVE")
    print("=" * 80)

    conv_path = os.path.join(DATA_DIR, "conversations.json")
    print(f"Loading {conv_path}...")

    with open(conv_path, "r", encoding="utf-8") as f:
        conversations = json.load(f)

    print(f"Total conversations: {len(conversations)}")

    # Collect ALL unique keys across all conversations
    all_conv_keys = set()
    for conv in conversations:
        all_conv_keys.update(conv.keys())

    print(f"\n🔑 ALL unique conversation-level keys (across all {len(conversations)}):")
    for k in sorted(all_conv_keys):
        print(f"   • {k}")

    # Check which conversations have project info
    project_linked = 0
    project_uuids_in_convs = Counter()
    no_project_count = 0

    for conv in conversations:
        proj_uuid = conv.get("project_uuid") or conv.get("project") or conv.get("project_id")
        if proj_uuid:
            project_linked += 1
            project_uuids_in_convs[proj_uuid] += 1
        else:
            no_project_count += 1

    print(f"\n📁 PROJECT LINKAGE:")
    print(f"   Conversations WITH project: {project_linked}")
    print(f"   Conversations WITHOUT project: {no_project_count}")

    if project_uuids_in_convs:
        print(f"\n   Conversations per project UUID:")
        for uuid, count in project_uuids_in_convs.most_common():
            print(f"     {uuid}: {count} conversations")

    # =========================================================================
    # 2. MESSAGE STRUCTURE - Deep analysis
    # =========================================================================
    print("\n\n💬 MESSAGE STRUCTURE DEEP DIVE")
    print("=" * 80)

    all_msg_keys = set()
    sender_types = Counter()
    msg_count_total = 0
    text_vs_content = {"both_same": 0, "both_diff": 0, "text_only": 0, "content_only": 0, "neither": 0}
    content_types = Counter()
    has_attachments = 0
    has_files = 0
    attachment_samples = []
    file_samples = []
    content_is_list = 0
    content_is_str = 0
    content_is_other = 0

    for conv in conversations:
        for msg in conv.get("chat_messages", []):
            msg_count_total += 1
            all_msg_keys.update(msg.keys())

            # Sender analysis
            sender = msg.get("sender")
            if isinstance(sender, str):
                sender_types[sender] += 1
            elif isinstance(sender, dict):
                sender_types[str(sender)] += 1
            else:
                sender_types[f"({type(sender).__name__}){sender}"] += 1

            # text vs content
            text_val = msg.get("text")
            content_val = msg.get("content")

            if isinstance(content_val, list):
                content_is_list += 1
            elif isinstance(content_val, str):
                content_is_str += 1
            else:
                content_is_other += 1

            if text_val and content_val:
                if isinstance(content_val, str) and text_val == content_val:
                    text_vs_content["both_same"] += 1
                else:
                    text_vs_content["both_diff"] += 1
            elif text_val and not content_val:
                text_vs_content["text_only"] += 1
            elif content_val and not text_val:
                text_vs_content["content_only"] += 1
            else:
                text_vs_content["neither"] += 1

            # Attachments
            atts = msg.get("attachments")
            if atts and len(atts) > 0:
                has_attachments += 1
                if len(attachment_samples) < 3:
                    attachment_samples.append(atts[0])

            # Files
            fils = msg.get("files")
            if fils and len(fils) > 0:
                has_files += 1
                if len(file_samples) < 3:
                    file_samples.append(fils[0])

    print(f"Total messages across all conversations: {msg_count_total}")
    print(f"Average messages per conversation: {msg_count_total / len(conversations):.1f}")

    print(f"\n🔑 ALL unique message-level keys:")
    for k in sorted(all_msg_keys):
        print(f"   • {k}")

    print(f"\n👤 SENDER TYPES:")
    for sender, count in sender_types.most_common():
        print(f"   {sender}: {count}")

    print(f"\n📝 TEXT vs CONTENT field analysis:")
    for k, v in text_vs_content.items():
        print(f"   {k}: {v}")
    print(f"\n   content field type: list={content_is_list}, str={content_is_str}, other={content_is_other}")

    print(f"\n📎 ATTACHMENTS: {has_attachments} messages have attachments")
    if attachment_samples:
        print(f"   Sample attachment structure:")
        for i, att in enumerate(attachment_samples):
            print(f"   [{i+1}] keys: {list(att.keys()) if isinstance(att, dict) else type(att).__name__}")
            if isinstance(att, dict):
                for k, v in att.items():
                    display = str(v)[:100] if v else "null"
                    print(f"       • {k}: {display}")

    print(f"\n📁 FILES: {has_files} messages have files")
    if file_samples:
        print(f"   Sample file structure:")
        for i, fil in enumerate(file_samples):
            print(f"   [{i+1}] keys: {list(fil.keys()) if isinstance(fil, dict) else type(fil).__name__}")
            if isinstance(fil, dict):
                for k, v in fil.items():
                    display = str(v)[:100] if v else "null"
                    print(f"       • {k}: {display}")

    # =========================================================================
    # 3. SAMPLE MESSAGES - Show actual content structure
    # =========================================================================
    print("\n\n📋 SAMPLE MESSAGES (first conversation, first 3 messages)")
    print("=" * 80)

    first_conv = conversations[0]
    print(f"Conversation: {first_conv.get('name', '(unnamed)')}")
    print(f"UUID: {first_conv['uuid']}")
    print(f"Messages: {len(first_conv['chat_messages'])}")

    for i, msg in enumerate(first_conv["chat_messages"][:3]):
        print(f"\n--- Message {i+1} ---")
        print(f"  sender: {msg.get('sender')}")
        print(f"  uuid: {msg.get('uuid')}")
        print(f"  created_at: {msg.get('created_at')}")

        text = msg.get("text", "")
        content = msg.get("content", "")

        if text:
            print(f"  text (first 300 chars): {str(text)[:300]}")
        if content:
            if isinstance(content, list):
                print(f"  content: LIST with {len(content)} items")
                for j, item in enumerate(content[:3]):
                    if isinstance(item, dict):
                        print(f"    [{j}] keys: {list(item.keys())}")
                        for k, v in item.items():
                            display = str(v)[:150] if v else "null"
                            print(f"        {k}: {display}")
                    else:
                        print(f"    [{j}] {str(item)[:150]}")
            elif isinstance(content, str):
                print(f"  content (first 300 chars): {content[:300]}")
            else:
                print(f"  content type: {type(content).__name__}")

    # =========================================================================
    # 4. CONTENT LIST STRUCTURE (for assistant messages)
    # =========================================================================
    print("\n\n🤖 ASSISTANT MESSAGE CONTENT STRUCTURE")
    print("=" * 80)

    # Find first assistant message with list content
    found = 0
    for conv in conversations[:50]:
        for msg in conv.get("chat_messages", []):
            if msg.get("sender") == "assistant" and isinstance(msg.get("content"), list):
                print(f"\nConversation: {conv.get('name', '(unnamed)')}")
                print(f"Content list has {len(msg['content'])} items")
                for j, item in enumerate(msg["content"][:5]):
                    if isinstance(item, dict):
                        print(f"  [{j}] type={item.get('type', '?')}, keys={list(item.keys())}")
                        if item.get("type") == "text":
                            print(f"       text (first 200): {str(item.get('text', ''))[:200]}")
                    else:
                        print(f"  [{j}] {type(item).__name__}: {str(item)[:100]}")
                found += 1
                if found >= 3:
                    break
        if found >= 3:
            break

    # =========================================================================
    # 5. PROJECTS - Full details
    # =========================================================================
    print("\n\n📂 PROJECTS DETAIL")
    print("=" * 80)

    proj_path = os.path.join(DATA_DIR, "projects.json")
    with open(proj_path, "r", encoding="utf-8") as f:
        projects = json.load(f)

    # Create UUID -> name mapping
    proj_uuid_to_name = {}
    for proj in projects:
        proj_uuid_to_name[proj["uuid"]] = proj["name"]

    for proj in projects:
        is_starter = proj.get("is_starter_project", False)
        marker = " ⭐ STARTER" if is_starter else ""
        print(f"\n{'─' * 60}")
        print(f"  Name: {proj['name']}{marker}")
        print(f"  UUID: {proj['uuid']}")
        desc = proj.get("description", "")
        print(f"  Description: {desc[:200] if desc else '(none)'}")
        print(f"  Private: {proj.get('is_private')}")
        print(f"  Created: {proj.get('created_at')}")
        print(f"  Prompt template: {str(proj.get('prompt_template', ''))[:200] or '(none)'}")

        docs = proj.get("docs", [])
        print(f"  Docs: {len(docs)}")
        for doc in docs[:5]:
            content_preview = str(doc.get("content", ""))[:150]
            print(f"    📄 {doc.get('filename', '?')} ({len(str(doc.get('content', '')))} chars)")
            print(f"       Preview: {content_preview}")

        # Count conversations for this project
        conv_count = project_uuids_in_convs.get(proj["uuid"], 0)
        print(f"  Conversations in this project: {conv_count}")

    # Show unmapped project UUIDs
    unmapped = set(project_uuids_in_convs.keys()) - set(proj_uuid_to_name.keys())
    if unmapped:
        print(f"\n⚠️ UNMAPPED PROJECT UUIDs (in conversations but not in projects.json):")
        for u in unmapped:
            print(f"   {u}: {project_uuids_in_convs[u]} conversations")

    # =========================================================================
    # 6. CONVERSATION NAME/SUMMARY STATS
    # =========================================================================
    print("\n\n📊 CONVERSATION METADATA STATS")
    print("=" * 80)

    named = sum(1 for c in conversations if c.get("name"))
    has_summary = sum(1 for c in conversations if c.get("summary"))
    msg_counts = [len(c.get("chat_messages", [])) for c in conversations]

    print(f"  Named conversations: {named} / {len(conversations)}")
    print(f"  With summary: {has_summary} / {len(conversations)}")
    print(f"  Message count stats:")
    print(f"    Min: {min(msg_counts)}")
    print(f"    Max: {max(msg_counts)}")
    print(f"    Avg: {sum(msg_counts)/len(msg_counts):.1f}")
    print(f"    Median: {sorted(msg_counts)[len(msg_counts)//2]}")
    print(f"    Total: {sum(msg_counts)}")

    # Date range
    dates = []
    for c in conversations:
        try:
            dt = datetime.fromisoformat(c["created_at"].replace("Z", "+00:00"))
            dates.append(dt)
        except:
            pass

    if dates:
        print(f"\n  Date range: {min(dates).strftime('%Y-%m-%d')} → {max(dates).strftime('%Y-%m-%d')}")

        # Monthly breakdown
        monthly = Counter()
        for d in dates:
            monthly[d.strftime("%Y-%m")] += 1
        print(f"\n  Monthly breakdown:")
        for month, count in sorted(monthly.items()):
            bar = "█" * (count // 5)
            print(f"    {month}: {count:4d} {bar}")

    print("\n" + "=" * 80)
    print("✅ Deep inspection complete!")


if __name__ == "__main__":
    deep_inspect()