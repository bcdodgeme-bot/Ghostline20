# modules/integrations/job_radar/profile_config.py
"""
Job Radar Profile Configuration for Syntax Prime V2
====================================================
Encodes Carl's complete professional identity for AI-powered job matching.

Data Sources:
- CliftonStrengths Top 5 (Gallup)
- HIGH5 Strengths Test (Feb 23, 2026)
- 16Personalities INTJ-T (Feb 23, 2026)
- Professional resume and career history
- Personal values and hard requirements

This file is the "Carl API" - the scoring engine queries this to evaluate
every job listing against who Carl actually is.

Created: 2026-02-23
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field


# =============================================================================
# PERSONAL IDENTITY
# =============================================================================

USER_ID = "b7c60682-4815-4d9d-8ebe-66c6cd24eff9"
CANDIDATE_NAME = "Carl Dodge"
LOCATION = "Fairfax, Virginia"
TIMEZONE = "America/New_York"


# =============================================================================
# HARD FILTERS — Binary pass/fail, checked BEFORE AI scoring
# =============================================================================

HARD_FILTERS = {
    # Compensation
    "min_base_salary": 95000,
    "required_benefits": ["401k", "health_insurance", "pto", "sick_leave"],
    
    # Work arrangement
    "remote_required": True,
    "max_travel_percent": 10,  # Occasional on-site retreats OK
    "acceptable_arrangements": ["remote", "fully remote", "work from home"],
    "reject_arrangements": ["hybrid", "on-site", "in-office", "in office"],
    
    # Company reputation floor
    "min_company_rating": 3.5,  # Glassdoor/Indeed/Comparably scale of 5
    
    # Islamic compliance — STRICT mode
    # Not just "is the company haram" but "does the culture normalize haram"
    "halal_compliance": "strict",
}


# =============================================================================
# HALAL FILTER — Islamic income compliance
# =============================================================================

HALAL_FILTER = {
    # Industries that are categorically excluded
    "excluded_industries": [
        "conventional banking",
        "conventional lending",
        "interest-based financial services",
        "alcohol production",
        "brewery",
        "distillery",
        "winery",
        "gambling",
        "casino",
        "sports betting",
        "pork production",
        "pork processing",
        "adult entertainment",
        "pornography",
        "conventional insurance",  # Flagged, not always auto-reject
        "weapons manufacturing",
        "tobacco",
        "cannabis",
        "marijuana",
    ],
    
    # Keywords in job descriptions or company pages that trigger rejection
    "company_red_flags": [
        "casino", "brewery", "distillery", "winery", "spirits",
        "betting", "wagering", "liquor", "payday loan",
        "strip club", "gentlemen's club", "dispensary",
        "craft beer", "wine bar", "cocktail",
    ],
    
    # Culture red flags — even if the company isn't in a haram industry,
    # normalizing haram in corporate culture is a rejection
    # Example: Hospital marketing job mentioning "wine reception" = FAIL
    "culture_red_flags": [
        "wine reception", "cocktail hour", "beer friday",
        "happy hour culture", "brewery tour", "wine tasting",
        "bar crawl", "pub night",
    ],
    
    # Nuance instructions for AI scorer
    "ai_scoring_notes": (
        "DEFAULT TO PASS. Only mark FAIL if you have strong, specific evidence "
        "that the company's PRIMARY revenue comes from a haram source (banking, "
        "lending, alcohol, gambling, pork, adult entertainment, weapons, tobacco). "
        "A company name you don't recognize is NOT grounds for FAIL. "
        "A marketing agency, consulting firm, tech company, SaaS company, "
        "nonprofit, healthcare org, or education company is PASS unless proven "
        "otherwise. Hospitality companies (hotels) are PASS. Fashion companies "
        "are PASS. The only culture FAIL is if the job description explicitly "
        "mentions alcohol-centered team activities (beer fridays, wine receptions, "
        "brewery outings) as core culture — not just the existence of a holiday party."
    ),
}


# =============================================================================
# CULTURE FILTERS — AI-evaluated, not binary
# =============================================================================

CULTURE_FILTERS = {
    # "Respect My Time" filter
    "work_style": {
        "preference": "results_oriented",  # Task over clock
        "description": (
            "Carl values output over hours logged. He despises clock-watching "
            "culture. He will work late when needed but expects the same "
            "flexibility in return — no guilt trips for logging off at 4pm "
            "after delivering everything. Ramadan example: 'My brother in "
            "Islam, it is Ramadan and I have a family to care for, you will "
            "get this on Monday.'"
        ),
    },
    
    # Green signals in job descriptions
    "positive_signals": [
        "results-oriented", "outcome-based", "output over hours",
        "flexible schedule", "async-first", "async communication",
        "we trust our team", "autonomy", "self-directed",
        "unlimited PTO", "generous PTO",
        "work-life balance", "sustainable pace",
        "religious accommodation", "inclusive culture",
        "diversity of thought", "ERG", "employee resource group",
        "professional development budget", "learning stipend",
        "build from the ground up", "stand up a department",
        "data-driven", "strategic", "analytical",
    ],
    
    # Red signals — penalize but don't auto-reject
    "negative_signals": [
        "always-on", "hustle culture", "move fast break things",
        "core hours 9-5", "butts in seats",
        "we work hard and play hard",  # Often code for no boundaries
        "fast-paced startup",  # Flag, don't reject — context matters
        "open office", "mandatory fun",
        "like a family",  # Often code for no boundaries
        "wear many hats",  # Carl already does this but it can mean understaffed
        "rockstar", "ninja", "guru",  # Cringe + often means overworked
    ],
    
    # Glassdoor/review red flags
    "review_red_flags": [
        "micromanagement", "overwork", "weekend work expected",
        "no work-life balance", "high turnover",
        "poor leadership", "toxic culture",
    ],
}


# =============================================================================
# PERSONALITY ASSESSMENTS
# =============================================================================

PERSONALITY = {
    # 16Personalities (Myers-Briggs based)
    "mbti": {
        "type": "INTJ-T",
        "label": "Architect (Turbulent)",
        "dimensions": {
            "energy": {"score": 72, "direction": "introverted"},
            "mind": {"score": 84, "direction": "intuitive"},
            "nature": {"score": 52, "direction": "thinking"},  # Near border!
            "tactics": {"score": 76, "direction": "judging"},
            "identity": {"score": 68, "direction": "turbulent"},
        },
        "career_strengths": [
            "innovative_mindset",
            "independent_worker",
            "conceptual_thinking",
            "continuous_improvement",
            "objective_judgment",
            "reliable_performance",
        ],
        "career_weaknesses": [
            "discomfort_with_networking",
            "frustration_with_constraints",
            "ignoring_social_dynamics",
            "reluctance_to_delegate",
            "overly_blunt_feedback",
            "impatience_with_routine",
        ],
        "work_implications": (
            "Thrives on intellectual challenges and implementing innovative ideas. "
            "Excels in roles requiring strategic thinking and problem-solving. "
            "Prefers working independently. Dislikes office politics. "
            "Nature score of 52% Thinking means he's ALMOST Feeling — "
            "he thinks logically but genuinely cares about people."
        ),
    },
    
    # CliftonStrengths (Gallup)
    "clifton_strengths": {
        "top_5": [
            {
                "rank": 1,
                "name": "Restorative",
                "domain": "Executing",
                "description": "Adept at dealing with problems. Good at figuring out what is wrong and resolving it.",
            },
            {
                "rank": 2,
                "name": "Intellection",
                "domain": "Strategic Thinking",
                "description": "Characterized by intellectual activity. Introspective and appreciates intellectual discussions.",
            },
            {
                "rank": 3,
                "name": "Achiever",
                "domain": "Executing",
                "description": "Works hard and possesses great stamina. Takes immense satisfaction in being busy and productive.",
            },
            {
                "rank": 4,
                "name": "Deliberative",
                "domain": "Executing",
                "description": "Takes serious care in making decisions or choices. Anticipates obstacles.",
            },
            {
                "rank": 5,
                "name": "Ideation",
                "domain": "Strategic Thinking",
                "description": "Fascinated by ideas. Finds connections between seemingly disparate phenomena.",
            },
        ],
        "domain_distribution": {
            "Executing": 3,       # Restorative, Achiever, Deliberative
            "Strategic Thinking": 2,  # Intellection, Ideation
            "Relationship Building": 0,
            "Influencing": 0,
        },
        "work_implications": (
            "Heavy Executing + Strategic Thinking with zero Relationship Building "
            "or Influencing. This is someone who wants to BUILD THINGS and THINK "
            "DEEPLY, not schmooze or manage politics. Independent operator who "
            "needs broken things to fix, intellectual stimulation, measurable "
            "output, and creative freedom."
        ),
    },
    
    # HIGH5 Strengths
    "high5_strengths": {
        "top_5": [
            {
                "rank": 1,
                "name": "Philomath",
                "description": "Loves learning. Explores many interests, follows new paths, acquires knowledge.",
            },
            {
                "rank": 2,
                "name": "Problem Solver",
                "description": "Loves uncovering flaws, diagnosing problems, coming up with solutions.",
            },
            {
                "rank": 3,
                "name": "Empathizer",
                "description": "Great at understanding how people feel. Uses sensibility to do good for others.",
            },
            {
                "rank": 4,
                "name": "Brainstormer",
                "description": "Gets excited connecting the seemingly unconnectable. Bored by close-minded people.",
            },
            {
                "rank": 5,
                "name": "Analyst",
                "description": "Energized searching for simplicity and clarity within large amounts of data.",
            },
        ],
    },
    
    # Cross-assessment synthesis
    "unified_profile": (
        "All three assessments tell the same story from different angles: "
        "Carl is someone who wants to LEARN CONSTANTLY (Philomath + Intellection), "
        "SOLVE MEANINGFUL PROBLEMS (Problem Solver + Restorative), "
        "BUILD INNOVATIVE SYSTEMS (Brainstormer + Ideation), "
        "USE DATA TO MAKE CAREFUL DECISIONS (Analyst + Deliberative + Achiever), "
        "and DO IT FOR A CAUSE HE BELIEVES IN (Empathizer + INTJ-T near-Feeling). "
        "He needs to be left alone to execute without someone breathing down his neck."
    ),
}


# =============================================================================
# PROFESSIONAL EXPERIENCE — For AI matching
# =============================================================================

EXPERIENCE = {
    "years_of_experience": 14,  # Since Nov 2010
    "current_title": "Director of Marketing & Communications",
    "current_employer": "American Muslim Community Foundation",
    "education": {
        "degree": "Master of Communication, Culture, and Technology",
        "institution": "Georgetown University",
        "year": 2016,
    },
    
    # Titles Carl would consider
    "target_titles": [
        "Director of Marketing",
        "Director of Communications",
        "Director of Marketing & Communications",
        "Director of Digital Marketing",
        "Director of Brand Strategy",
        "VP of Marketing",
        "Vice President of Marketing",
        "Head of Marketing",
        "Senior Director of Marketing",
        "Marketing Director",
        "Communications Director",
        "Chief Marketing Officer",  # Stretch but worth flagging
        "Senior Marketing Manager",
    ],
    
    # Industries where Carl has proven experience
    "proven_industries": [
        "nonprofit",
        "philanthropy",
        "higher education",
        "islamic organizations",
        "halal finance",
        "social impact",
        "community development",
        "humanitarian",
    ],
    
    # Industries Carl would be interested in
    "interested_industries": [
        "technology",
        "SaaS",
        "AI / machine learning",
        "healthcare",
        "education technology",
        "social enterprise",
        "clean energy",
        "government",
        "think tank",
        "consulting",
        "media",
    ],
    
    # Hard skills from resume + known capabilities
    "hard_skills": [
        # Marketing
        "email marketing", "marketing automation", "HubSpot",
        "Salesforce", "Blackbaud", "CRM migration",
        "SEO", "SEM", "Google Ads", "paid advertising",
        "content marketing", "content strategy", "copywriting",
        "social media strategy", "social media management",
        "brand management", "brand storytelling",
        "Google Analytics", "Microsoft Clarity", "data analytics",
        "WordPress", "website management", "Rank Math",
        "campaign management", "integrated marketing",
        "donor cultivation", "fundraising campaigns",
        "stakeholder engagement", "cross-functional leadership",
        "project management",
        
        # Technology (differentiators — most marketing directors can't do this)
        "Python", "JavaScript", "SwiftUI",
        "FastAPI", "PostgreSQL", "REST APIs",
        "AI/ML application development", "prompt engineering",
        "system architecture", "automation development",
    ],
    
    # Performance metrics from resume
    "performance_metrics": {
        "email_open_rates": "47-54% (industry avg 25-28%)",
        "google_ads_cpc": "$0.14 (industry avg $1-2)",
        "organic_traffic_increase": "35% at Guidance Residential",
        "student_recruitment_increase": "25% at Trinity Washington",
        "donor_engagement_increase": "30% at Islamic Relief USA",
        "campaign_roi_improvement": "20% at Zakat Foundation",
        "cost_savings": "$100K/year by bringing ops in-house at IRUSA",
        "project_timeline_reduction": "20% via PM system implementation",
    },
    
    # What makes Carl unique vs other marketing directors
    "differentiators": [
        "One-person department specialist — can do the work of 3-4 people",
        "Technical builder — actually codes automation systems (Python, FastAPI, AI)",
        "Georgetown MA CCT — academic grounding in communication theory",
        "Navy veteran — discipline, mission focus, no-BS attitude",
        "10+ years in mission-driven orgs — understands donor psychology",
        "CRM migration specialist — Blackbaud to HubSpot, legacy to modern",
        "Exceptional ad performance — 7x better CPC than industry average",
        "AI-native — built a full AI assistant system from scratch",
    ],
}


# =============================================================================
# AI SCORING WEIGHTS — How the Claude API evaluates each job
# =============================================================================

SCORING_WEIGHTS = {
    "skills_match": 0.25,           # Do the required skills align?
    "culture_fit": 0.25,            # Time respect, autonomy, inclusion
    "seniority_alignment": 0.15,    # Director-level, not entry or C-suite
    "strengths_utilization": 0.15,  # CliftonStrengths + HIGH5 alignment
    "growth_potential": 0.10,       # Room to build, learn, innovate
    "company_reputation": 0.10,     # Glassdoor + review signals
}


# =============================================================================
# AI SCORING PROMPT TEMPLATE
# =============================================================================

def build_scoring_prompt(job_data: Dict[str, Any]) -> str:
    """
    Build the Claude API prompt for scoring a job listing against Carl's profile.
    
    Args:
        job_data: Dict containing job title, description, company, salary, etc.
        
    Returns:
        Complete prompt string for Claude API
    """
    return f"""You are an expert career advisor evaluating a job listing for a specific candidate.

## CANDIDATE PROFILE

**Name:** {CANDIDATE_NAME}
**Current Role:** {EXPERIENCE['current_title']} at {EXPERIENCE['current_employer']}
**Experience:** {EXPERIENCE['years_of_experience']} years in marketing & communications
**Education:** {EXPERIENCE['education']['degree']}, {EXPERIENCE['education']['institution']}
**Location:** {LOCATION} (requires fully remote, ≤10% travel)
**Minimum Salary:** ${HARD_FILTERS['min_base_salary']:,}+

**Personality Type:** {PERSONALITY['mbti']['type']} ({PERSONALITY['mbti']['label']})
- Introverted (72%), Intuitive (84%), Thinking (52% — near Feeling border), Judging (76%), Turbulent (68%)

**CliftonStrengths Top 5:**
1. Restorative (Executing) — problem fixer
2. Intellection (Strategic Thinking) — deep thinker
3. Achiever (Executing) — high output, stamina
4. Deliberative (Executing) — careful, data-driven decisions
5. Ideation (Strategic Thinking) — connects disparate ideas

**HIGH5 Strengths:**
1. Philomath — loves learning
2. Problem Solver — diagnoses and fixes
3. Empathizer — understands people
4. Brainstormer — creative connections
5. Analyst — finds clarity in data

**Key Differentiators:**
- One-person department specialist (does the work of 3-4 people)
- Technical builder — codes Python, FastAPI, built a full AI assistant
- Georgetown MA CCT
- Navy veteran
- 10+ years in mission-driven organizations
- Exceptional metrics: 47-54% email open rates, $0.14 Google Ads CPC

**Hard Requirements:**
- Income must be halal — DEFAULT TO PASS. Only FAIL if the company's PRIMARY revenue clearly comes from: conventional banking/lending, alcohol, gambling, pork, adult entertainment, weapons, or tobacco. Unknown companies = PASS. Agencies, tech, SaaS, healthcare, education, hospitality, fashion, consulting = PASS unless proven haram.
- Company culture: only FAIL if the job description explicitly features alcohol-centered activities (beer fridays, brewery outings, wine receptions) as core culture
- Fully remote with ≤10% travel
- Base salary $95K+
- Benefits: 401k, health insurance, PTO, sick leave
- Company rating 3.5+ on Glassdoor/similar

**Culture Preferences:**
- Results over clock-watching (task-based, not time-based)
- Autonomy and trust (INTJ needs independent deep work)
- No "we're like a family" or "hustle culture" energy
- Must respect religious observance (Ramadan, prayer times)
- Values continuous learning and intellectual stimulation

**Ideal Role Signals:**
- "Build from the ground up" / stand up a department
- Data-driven decision making
- Strategic + hands-on execution
- Mission-driven organization
- Small-to-mid team where one person has real impact

**Red Flags:**
- Purely maintaining existing programs (no building)
- Heavy stakeholder management with no execution
- Bureaucratic with no room to improve processes
- "Move fast break things" / no deliberation allowed
- Large marketing team where he'd be a cog

## JOB LISTING TO EVALUATE

**Title:** {job_data.get('title', 'Unknown')}
**Company:** {job_data.get('company', 'Unknown')}
**Location:** {job_data.get('location', 'Unknown')}
**Salary:** {job_data.get('salary', 'Not listed')}
**Employment Type:** {job_data.get('employment_type', 'Unknown')}

**Description:**
{job_data.get('description', 'No description available')}

## YOUR TASK

Score this job listing. Return ONLY valid JSON with no other text:

{{
    "halal_compliance": "PASS" or "FAIL",
    "halal_notes": "Brief explanation of halal assessment",
    "skills_match": 0-100,
    "culture_fit": 0-100,
    "seniority_alignment": 0-100,
    "strengths_utilization": 0-100,
    "growth_potential": 0-100,
    "company_reputation_signals": 0-100,
    "overall_score": 0-100,
    "recommendation": "STRONG_MATCH" or "GOOD_MATCH" or "WORTH_REVIEWING" or "WEAK_MATCH" or "SKIP",
    "top_3_reasons_for": ["reason1", "reason2", "reason3"],
    "top_3_concerns": ["concern1", "concern2", "concern3"],
    "suggested_resume_highlights": ["highlight1", "highlight2", "highlight3"],
    "cover_letter_angle": "One sentence on how to position for this specific role"
}}
"""


# =============================================================================
# SEARCH QUERIES — What to search for across all 3 APIs
# =============================================================================

SEARCH_QUERIES = [
    # Primary titles
    "Director of Marketing remote",
    "Director of Communications remote",
    "Director of Marketing Communications remote",
    "Director of Digital Marketing remote",
    "Head of Marketing remote",
    "VP Marketing remote",
    "Senior Marketing Manager remote",
    
    # Industry-specific
    "Director of Marketing nonprofit remote",
    "Director of Marketing education remote",
    "Director of Marketing healthcare remote",
    "Director of Marketing SaaS remote",
    "Director of Marketing technology remote",
    "Marketing Director social impact remote",
    
    # Skills-specific
    "Marketing Director HubSpot remote",
    "Marketing Director CRM remote",
    "Marketing Director content strategy remote",
]

# Maximum results per API per query
MAX_RESULTS_PER_QUERY = 10

# How often to run the job scan (in seconds)
JOB_SCAN_INTERVAL = 14400  # 4 hours — same as intelligence cycle
JOB_SCAN_STARTUP_DELAY = 1500  # 25 minutes — stagger after other tasks


# =============================================================================
# NOTIFICATION THRESHOLDS
# =============================================================================

NOTIFICATION_THRESHOLDS = {
    "immediate_push": 80,    # Score 80+ → email notification NOW
    "daily_digest": 60,      # Score 60-79 → include in daily digest email
    "log_only": 40,          # Score 40-59 → log but don't notify
    "discard": 0,            # Score <40 → don't even store
}

# Notification delivery method
NOTIFICATION_CHANNEL = "email"  # "email" or "telegram"
NOTIFICATION_EMAIL = "carl@bcdodge.me"

# SMTP settings for sending (bypasses Gmail API so emails arrive as inbound)
SMTP_CONFIG = {
    "host": "mail.damnitcarl.dev",
    "port": 465,
    "username": "bcdodgeme",
    "from_address": "admin@mail.damnitcarl.dev",
    "from_name": "Syntax Prime Job Radar",
    "use_ssl": True,
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_hard_filter_summary() -> str:
    """Human-readable summary of hard filters for logging"""
    return (
        f"Remote only | ${HARD_FILTERS['min_base_salary']:,}+ base | "
        f"Halal income (strict) | Company rating {HARD_FILTERS['min_company_rating']}+ | "
        f"≤{HARD_FILTERS['max_travel_percent']}% travel | Benefits required"
    )


def get_search_keywords() -> List[str]:
    """Extract unique keywords for deduplication matching"""
    keywords = set()
    for query in SEARCH_QUERIES:
        for word in query.lower().split():
            if word not in {"remote", "of", "and", "the", "a"}:
                keywords.add(word)
    return sorted(keywords)


def check_instant_reject(job_data: Dict[str, Any]) -> Optional[str]:
    """
    Quick pre-check before AI scoring. Returns rejection reason or None.
    
    Args:
        job_data: Parsed job listing data
        
    Returns:
        Rejection reason string, or None if it passes pre-screening
    """
    title_lower = (job_data.get('title', '') or '').lower()
    desc_lower = (job_data.get('description', '') or '').lower()
    company_lower = (job_data.get('company', '') or '').lower()
    location_lower = (job_data.get('location', '') or '').lower()
    
    # Check halal red flags in company name
    for flag in HALAL_FILTER['company_red_flags']:
        if flag.lower() in company_lower:
            return f"Halal filter: company name contains '{flag}'"
    
    # Check for obviously non-remote roles
    if any(term in desc_lower[:500] for term in [
        "must be located in", "on-site required", "no remote",
        "in-office 5 days", "this is not a remote position"
    ]):
        return "Not remote: explicit on-site requirement detected"
    
    # Check for obviously wrong seniority
    junior_signals = ["intern", "entry level", "entry-level", "associate", "coordinator", "specialist"]
    if any(signal in title_lower for signal in junior_signals):
        return f"Seniority mismatch: title suggests junior role"
    
    # Check salary if available
    salary = job_data.get('salary_min') or job_data.get('salary')
    if salary and isinstance(salary, (int, float)):
        if salary < HARD_FILTERS['min_base_salary'] and salary > 1000:  # >1000 to skip hourly
            return f"Below salary floor: ${salary:,.0f} < ${HARD_FILTERS['min_base_salary']:,}"
    
    return None  # Passes pre-screening
