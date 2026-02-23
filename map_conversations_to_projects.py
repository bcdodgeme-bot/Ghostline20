#!/usr/bin/env python3
"""
Map Claude Conversations to Projects
=====================================
Scans conversation titles and summaries for keywords,
assigns primary_project_id where there's a confident match.

Usage:
  python map_conversations_to_projects.py [--dry-run] [--verbose]
"""

import psycopg2
import argparse
import re
from collections import defaultdict

DATABASE_URL = "postgresql://postgres:RcldqFcBwHuiuqpiCemgiTjfuJcvOJLH@ballast.proxy.rlwy.net:12126/railway"

# =============================================================================
# PROJECT KEYWORD MAPPINGS
# =============================================================================
# Each project has:
#   - title_keywords: matched against conversation title (case-insensitive)
#   - summary_keywords: matched against conversation summary (case-insensitive)
#   - exclude_keywords: if these appear, skip the match (prevents false positives)
#   - priority: higher = wins in case of conflict (10 = highest)

PROJECT_RULES = {
    # --- Ghostline Beta 2.0 / Syntax Prime V2 (most specific first) ---
    "Ghostline Beta 2.0": {
        "title_keywords": [
            r"\bsyntax prime\b", r"\bsyntax\s*prime\s*v2\b", r"\bghostline\s*beta\b",
            r"\bghostline\s*2\.0\b", r"\bghostline2\b", r"\bghostline 2\b",
            r"\brailway\s+deploy", r"\brailway\s+error",
            r"\btelegram\s+bot\b", r"\btelegram\s+notification",
            r"\bproactive\s+queue\b", r"\bunified\s+proactive\b",
            r"\bbluesky\s+engagement\b", r"\bbluesky\s+keyword",
            r"\bios\s+app\b", r"\bios\s+companion\b", r"\btestflight\b",
            r"\bswiftui\b", r"\bxcode\b", r"\bchatview\b",
            r"\bknowledge\s+entr", r"\bknowledge\s+base\b",
            r"\bvoice\s+synthesis\b", r"\belevenlabs\b",
            r"\bopenrouter\b", r"\bai\s+brain\b",
            r"\bmacos\s+integration\b", r"\bmulti.file\s+handling",
            r"\btwo.phase\s+response\b", r"\bproject\s+folders?\s+frontend",
            r"\bfathom\s+meet", r"\bclickup\s+task",
            r"\bweather\s+read", r"\bprayer\s+time",
            r"\bpersonalit(y|ies)\s+(mapping|system|switch)",
            r"\bauto.execut", r"\bapproval\s+(queue|system|workflow)",
        ],
        "summary_keywords": [
            r"\bsyntax\s*prime\b", r"\bghostline\b", r"\brailway\b",
            r"\btelegram\b.*\bbot\b", r"\bbluesky\b.*\bengagement\b",
            r"\bios\s+app\b", r"\bswiftui\b", r"\btestflight\b",
            r"\bfastapi\b", r"\bpostgresql\b.*\b(schema|table|database)\b",
            r"\bproactive\b.*\b(queue|system|content)\b",
        ],
        "exclude_keywords": [],
        "priority": 9,
    },

    # --- Ghostline 2.0 (earlier iteration) ---
    "Ghostline 2.0": {
        "title_keywords": [
            r"\bghostline\s*2\b", r"\bghostline\s*v2\b",
        ],
        "summary_keywords": [
            r"\bghostline\s*2\b",
        ],
        "exclude_keywords": [r"\bbeta\b", r"\bsyntax\s*prime\b"],
        "priority": 7,
    },

    # --- Ghostline (original) ---
    "Ghostline": {
        "title_keywords": [
            r"\bghostline\b",
        ],
        "summary_keywords": [
            r"\bghostline\b",
        ],
        "exclude_keywords": [r"\b2\.0\b", r"\bbeta\b", r"\bsyntax\s*prime\b", r"\bv2\b"],
        "priority": 5,
    },

    # --- AMCF CSUite HubSpot Sync ---
    "AMCF CSUite HubSpot Sync": {
        "title_keywords": [
            r"\bhubspot\b", r"\bcsuite\b", r"\bc.?suite\b",
            r"\bcrm\s+sync\b", r"\bcontact\s+sync\b",
        ],
        "summary_keywords": [
            r"\bhubspot\b", r"\bcsuite\b",
        ],
        "exclude_keywords": [],
        "priority": 8,
    },

    # --- AMCF - Ramadan 2025 ---
    "AMCF - Ramadan 2025": {
        "title_keywords": [
            r"\bramadan\b", r"\biftar\b", r"\bzakat\b", r"\beid\b",
            r"\bramadan\s+campaign\b", r"\bramadan\s+giving\b",
        ],
        "summary_keywords": [
            r"\bramadan\b", r"\biftar\b", r"\bzakat\b",
        ],
        "exclude_keywords": [],
        "priority": 8,
    },

    # --- AMCF-AGL (Arab Giving League) ---
    "AMCF-AGL": {
        "title_keywords": [
            r"\bagl\b", r"\barab\s+giving\b", r"\bgiving\s+league\b",
        ],
        "summary_keywords": [
            r"\bagl\b", r"\barab\s+giving\b",
        ],
        "exclude_keywords": [],
        "priority": 8,
    },

    # --- AMCF Website Overhaul ---
    "AMCF Website Overhaul": {
        "title_keywords": [
            r"\bamcf\b.*\bwebsite\b", r"\bamuslimcf\b.*\bwebsite\b",
            r"\bamcf\b.*\bweb\s*(page|site|design|overhaul|redesign)\b",
        ],
        "summary_keywords": [
            r"\bamcf\b.*\bwebsite\b",
        ],
        "exclude_keywords": [],
        "priority": 7,
    },

    # --- AMCF (general - catch-all for AMCF stuff) ---
    "AMCF": {
        "title_keywords": [
            r"\bamcf\b", r"\bamuslimcf\b", r"\bamerican\s+muslim\s+community\b",
            r"\bnonprofit\s+summit\b", r"\bgiving\s+circle\b",
            r"\bdonor\s+portal\b", r"\bdonor\s+advised\b", r"\bdaf\b",
            r"\bjidhr\b", r"\bfund\s+management\b",
            r"\bnewsletter\b.*\b(amcf|nonprofit)\b",
            r"\bamcf\b.*\b(email|campaign|event|gala|awards)\b",
            r"\bwomen.s\s+giving\b",
        ],
        "summary_keywords": [
            r"\bamcf\b", r"\bamuslimcf\b", r"\bamerican\s+muslim\s+community\b",
            r"\bnonprofit\b.*\b(foundation|fund|donor|giving)\b",
            r"\bjidhr\b", r"\bdonor\s+advised\b",
        ],
        "exclude_keywords": [],
        "priority": 4,
    },

    # --- HalalBot ---
    "HalalBot": {
        "title_keywords": [
            r"\bhalalbot\b", r"\bhalal\s+bot\b",
            r"\bislamic\s+ruling\b", r"\bfatwa\b", r"\bfiqh\b",
            r"\bislamic\s+knowledge\s+assistant\b",
        ],
        "summary_keywords": [
            r"\bhalalbot\b", r"\bislamic\s+ruling\b",
        ],
        "exclude_keywords": [],
        "priority": 8,
    },

    # --- NotHere.one ---
    "NotHere.one - Values-Based Search Engine": {
        "title_keywords": [
            r"\bnothere\b", r"\bnot\s*here\.one\b",
            r"\bethical\s+search\b", r"\bvalues.based\s+search\b",
            r"\balgorithm\s+of\s+justice\b",
        ],
        "summary_keywords": [
            r"\bnothere\b", r"\bethical\s+search\b",
        ],
        "exclude_keywords": [],
        "priority": 8,
    },

    # --- RFK Refugees ---
    "RFK Refugess": {
        "title_keywords": [
            r"\brfk\b", r"\brefugee", r"\brefugess\b",
            r"\bdc\s+united\s+podcast\b", r"\bsoccer\s+podcast\b",
            r"\bpodcast\b.*\b(episode|transcript|launch|seo)\b",
            r"\bcross.podcast\b",
        ],
        "summary_keywords": [
            r"\brfk\b.*\brefuge", r"\bdc\s+united\b.*\bpodcast\b",
            r"\bpodcast\b.*\b(rfk|soccer|dc\s+united)\b",
        ],
        "exclude_keywords": [],
        "priority": 7,
    },
}


# =============================================================================
# MATCHING ENGINE
# =============================================================================

def match_conversation(title, summary, rules):
    """
    Match a conversation against all project rules.
    Returns (project_name, score, matched_keywords) or (None, 0, []) if no match.
    """
    title = (title or "").lower()
    summary = (summary or "").lower()
    combined = f"{title} {summary}"

    candidates = []

    for project_name, rule in rules.items():
        score = 0
        matched = []

        # Check exclude first
        excluded = False
        for pattern in rule.get("exclude_keywords", []):
            if re.search(pattern, combined, re.IGNORECASE):
                excluded = True
                break
        if excluded:
            continue

        # Title matches (worth more)
        for pattern in rule["title_keywords"]:
            if re.search(pattern, title, re.IGNORECASE):
                score += 3
                matched.append(f"title:{pattern}")

        # Summary matches
        for pattern in rule.get("summary_keywords", []):
            if re.search(pattern, summary, re.IGNORECASE):
                score += 1
                matched.append(f"summary:{pattern}")

        if score > 0:
            # Add priority as tiebreaker
            final_score = score * 10 + rule["priority"]
            candidates.append((project_name, final_score, matched))

    if not candidates:
        return None, 0, []

    # Return highest scoring match
    candidates.sort(key=lambda x: -x[1])
    return candidates[0]


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Map Claude conversations to projects")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--verbose", action="store_true", help="Show all matches")
    parser.add_argument("--all-platforms", action="store_true", help="Map all platforms, not just claude.ai")
    args = parser.parse_args()

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

    # Get project name → id mapping
    cursor.execute("SELECT id, name FROM knowledge_projects")
    project_name_to_id = {row[1]: row[0] for row in cursor.fetchall()}

    # Verify all rule project names exist in DB
    for name in PROJECT_RULES:
        if name not in project_name_to_id:
            print(f"⚠️  Project '{name}' in rules but not in database!")

    # Get unmapped conversations
    platform_filter = "" if args.all_platforms else "AND platform = 'claude.ai'"
    cursor.execute(f"""
        SELECT id, title, summary, platform, created_at::date
        FROM conversation_threads
        WHERE primary_project_id IS NULL
        {platform_filter}
        ORDER BY created_at
    """)
    conversations = cursor.fetchall()

    print("=" * 70)
    print(f"🗂️  CONVERSATION → PROJECT MAPPING")
    print(f"   Unmapped conversations: {len(conversations)}")
    if args.dry_run:
        print("   ⚠️  DRY RUN MODE")
    print("=" * 70)

    # Stats
    mapped = defaultdict(list)
    unmapped = []
    total_mapped = 0

    for conv_id, title, summary, platform, created_date in conversations:
        project_name, score, matched = match_conversation(title, summary, PROJECT_RULES)

        if project_name:
            project_id = project_name_to_id.get(project_name)
            if project_id:
                mapped[project_name].append((conv_id, title, score, matched, created_date))
                total_mapped += 1

                if not args.dry_run:
                    cursor.execute("""
                        UPDATE conversation_threads
                        SET primary_project_id = %s
                        WHERE id = %s
                    """, (project_id, str(conv_id)))
            else:
                unmapped.append((title, created_date, f"Project '{project_name}' not in DB"))
        else:
            unmapped.append((title, created_date, None))

    if not args.dry_run:
        conn.commit()

    # Report
    print(f"\n📊 MAPPING RESULTS")
    print(f"   Total mapped: {total_mapped} / {len(conversations)}")
    print(f"   Unmapped: {len(unmapped)}")

    print(f"\n{'─' * 70}")
    print(f"✅ MAPPED CONVERSATIONS BY PROJECT:")
    print(f"{'─' * 70}")

    for project_name in sorted(mapped.keys()):
        convs = mapped[project_name]
        print(f"\n  📁 {project_name} ({len(convs)} conversations)")
        if args.verbose:
            for conv_id, title, score, matched, created_date in convs:
                t = (title or "(untitled)")[:60]
                print(f"     [{score:3d}] {created_date} | {t}")
        else:
            # Show first 5 and last 2
            for conv_id, title, score, matched, created_date in convs[:5]:
                t = (title or "(untitled)")[:60]
                print(f"     [{score:3d}] {created_date} | {t}")
            if len(convs) > 7:
                print(f"     ... ({len(convs) - 7} more) ...")
            for conv_id, title, score, matched, created_date in convs[-2:]:
                t = (title or "(untitled)")[:60]
                print(f"     [{score:3d}] {created_date} | {t}")

    print(f"\n{'─' * 70}")
    print(f"❓ UNMAPPED CONVERSATIONS ({len(unmapped)}):")
    print(f"{'─' * 70}")

    if args.verbose:
        for title, created_date, reason in unmapped:
            t = (title or "(untitled)")[:70]
            print(f"  {created_date} | {t}")
    else:
        # Show sample
        for title, created_date, reason in unmapped[:15]:
            t = (title or "(untitled)")[:70]
            print(f"  {created_date} | {t}")
        if len(unmapped) > 15:
            print(f"  ... and {len(unmapped) - 15} more")

    # Summary table
    print(f"\n{'─' * 70}")
    print(f"📋 SUMMARY:")
    print(f"{'─' * 70}")
    print(f"  {'Project':<45} {'Count':>6}")
    print(f"  {'─' * 45} {'─' * 6}")
    for project_name in sorted(mapped.keys(), key=lambda x: -len(mapped[x])):
        print(f"  {project_name:<45} {len(mapped[project_name]):>6}")
    print(f"  {'(unmapped)':<45} {len(unmapped):>6}")
    print(f"  {'─' * 45} {'─' * 6}")
    print(f"  {'TOTAL':<45} {len(conversations):>6}")

    cursor.close()
    conn.close()

    print(f"\n✅ Done!")


if __name__ == "__main__":
    main()