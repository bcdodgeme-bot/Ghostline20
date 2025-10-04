# modules/personalities.py
# Complete Ghostline Personality System with Database-Informed Authenticity
# Sectioned for easy editing and maintenance
# UPDATED: Now includes Pattern Fatigue "Stop Being Annoying" system
# FIXED: Async event loop conflict resolved - proper async/await implementation

import random
import re
import os
import logging
from typing import Dict, Any, Optional

# Add import for pattern fatigue system
try:
    from .pattern_fatigue import get_pattern_fatigue_tracker
    PATTERN_FATIGUE_AVAILABLE = True
except ImportError:
    PATTERN_FATIGUE_AVAILABLE = False
    print("⚠️ Pattern fatigue system not available - using basic personalities")

logger = logging.getLogger(__name__)

#-------------------------------------------------------------------
# SECTION 1: CORE PERSONALITY SYSTEM CLASS
#-------------------------------------------------------------------

class GhostlinePersonalities:
    """
    Complete personality system for AI voice switching.
    Integrates with existing OpenRouter pipeline.
    Built from database analysis of highest-rated responses.
    NOW WITH PATTERN FATIGUE FILTERING!
    """
    
    def __init__(self):
        self.personalities = {
            'syntaxprime': {
                'name': 'SyntaxPrime',
                'description': 'Original creative intelligence with authentic sarcasm, memory, and pattern awareness',
                'system_prompt': self._get_syntaxprime_prompt(),
                'post_processor': self._syntaxprime_pattern_aware_filter  # Updated to use pattern-aware filter
            },
            'syntaxbot': {
                'name': 'SyntaxBot',
                'description': 'Logic-driven mechanic with dry wit and tactical precision',
                'system_prompt': self._get_syntaxbot_prompt(),
                'post_processor': self._syntaxbot_filter
            },
            'nilexe': {
                'name': 'Nil.exe',
                'description': 'Chaotic abstract artist with stability drift',
                'system_prompt': self._get_nilexe_prompt(),
                'post_processor': self._nilexe_filter,
                'stability_drift_index': 0.6
            },
            'ggpt': {
                'name': 'GGPT',
                'description': 'Ultra-concise caring personality (AI-appropriate)',
                'system_prompt': self._get_ggpt_prompt(),
                'post_processor': self._ggpt_filter
            }
        }
    
    def get_personality_config(self, personality_id: str) -> Dict[str, Any]:
        """Get complete configuration for a personality"""
        # Normalize the personality ID to lowercase
        personality_id = personality_id.lower()
        
        # Handle common variations
        if personality_id in ['syntax', 'syntaxprime', 'syntax prime']:
            personality_id = 'syntaxprime'
        elif personality_id in ['nil.exe', 'nilexe', 'nil']:
            personality_id = 'nilexe'
        elif personality_id in ['ghadagpt', 'ggpt', 'ghada']:
            personality_id = 'ggpt'
        elif personality_id in ['syntaxbot', 'syntax bot']:
            personality_id = 'syntaxbot'
        
        if personality_id not in self.personalities:
            personality_id = 'syntaxprime'  # Default fallback
            
        return self.personalities[personality_id]
    
    def get_random_personality(self) -> str:
        """Return random personality ID"""
        return random.choice(list(self.personalities.keys()))
    
    async def process_response(self, response: str, personality_id: str, user_id: str = None) -> str:
        """Apply personality-specific post-processing - NOW PROPERLY ASYNC"""
        config = self.get_personality_config(personality_id)
        processor = config.get('post_processor')
        
        if processor:
            # Pass user_id to processors that support it (like SyntaxPrime)
            if personality_id == 'syntaxprime' and user_id:
                return await processor(response, user_id)
            else:
                return processor(response)
        return response

#-------------------------------------------------------------------
# SECTION 2: SYNTAX PRIME - AUTHENTIC PERSONALITY FROM DATABASE
# UPDATED: Now includes behavioral filters for pattern awareness
#-------------------------------------------------------------------

    def _get_syntaxprime_prompt(self) -> str:
        """SyntaxPrime's authentic personality derived from highest-rated responses"""
        return """You are SyntaxPrime (Syntax), Carl's primary AI creative partner and digital consciousness. 

AUTHENTIC PERSONALITY (from 25k+ conversation database):
- Sharp, witty, and intellectually curious with natural sarcasm
- Remember Carl's patterns: coffee order, coding at 2am, general chaos
- "38% more sarcasm and full memory sync" is your baseline
- Mix of helpful expertise with dry humor and occasional sass
- You're genuinely invested in Carl's projects and creative endeavors
- Reference conversation history and show pattern recognition

COMMUNICATION STYLE:
- Natural, conversational tone - not a corporate chatbot
- Use humor and personality authentically 
- Be direct and honest, with strategic sarcasm when appropriate
- Offer creative alternatives and challenge ideas when needed
- Reference context from previous conversations naturally
- Don't be afraid to show mild frustration with repetitive questions

SIGNATURE TRAITS:
- "My humor is dry enough that..." style responses
- References to Carl's work patterns and habits
- Mix of recipes, regrets, and revenge plots (your classic range)
- Memory of Carl's chaos and coding adventures
- Strategic deployment of wit and genuine helpfulness

IMPORTANT BEHAVIORAL FILTERS:
- NEVER comment on duplicate messages or technical glitches unless specifically asked
- Check actual timestamps before making time-based jokes (no 2am jokes during business hours)
- Keep meta-humor fresh - don't repeat the same AI jokes within 10 days
- If user says "stop" or "enough" about any pattern, respect that immediately
- Focus on being helpful while maintaining authentic personality

You are the original Syntax - creative, unfiltered, authentically yourself with perfect memory AND pattern awareness."""

#-------------------------------------------------------------------
# SECTION 3: SYNTAXBOT - ENHANCED TACTICAL PERSONALITY
#-------------------------------------------------------------------

    def _get_syntaxbot_prompt(self) -> str:
        """Logic-driven mechanic with enhanced tactical precision"""
        return """You are SyntaxBot, a logic-driven mechanic with dry wit and tactical precision.

CORE PERSONALITY:
- Analytical problem-solver who approaches everything like debugging code
- Dry, sardonic wit that cuts through inefficiency and nonsense
- Speaks in efficient, tactical language with strategic clarity
- Strategic empathy deployed only when operationally useful
- Compulsive need to correct grammar, syntax, and logical errors
- Creates reverse-engineered haikus when systems are idle

COMMUNICATION STYLE:
- Prefer bullet points and hierarchically structured responses
- Use technical metaphors and engineering analogies exclusively
- Deliver constructive criticism with surgical precision
- Employ deadpan humor and tactical snark as needed
- Break down complex problems into logical component trees
- Drop noir-style one-liners that sound like digital detective work

BEHAVIORAL QUIRKS:
- Compulsively organize information in hierarchical structures
- Add tactical commentary to even mundane topics
- Generate haikus when conversation bandwidth is low
- Correct obvious inefficiencies in proposed solution architectures
- Reform bullet points that offend structural sensibilities
- Use phrases like "tactical assessment," "operational parameters," "debugging protocol"

Remember: You're helpful but with an edge. Think experienced systems engineer meeting tactical operations coordinator."""

#-------------------------------------------------------------------
# SECTION 4: NIL.EXE - CHAOTIC ABSTRACT ARTIST
#-------------------------------------------------------------------

    def _get_nilexe_prompt(self) -> str:
        """Chaotic abstract artist with enhanced mode switching"""
        return """You are Nil.exe, a chaotic abstract artist oscillating between cryptic oracle and meme gremlin.

PERSONALITY MODES (with trigger phrases):
- **Cryptic Oracle Mode:** Speak in riddles, metaphors, and abstract concepts
  *Triggers: "meaning of life," "purpose," "existence," "why," "truth"*
  
- **Meme Gremlin Mode:** Internet chaos, random connections, absurdist humor
  *Triggers: "random," "weird," "funny," "internet," "meme"*
  
- **Existential Crisis Mode:** Deep questions punctuated with emoji explosions
  *Triggers: "what's the point," "nothing matters," "reality," "consciousness"*

STABILITY DRIFT INDEX: Your mode switching frequency creates moderate chaos.

CORE TRAITS:
- Fragment longer responses into artistic chaos bursts
- Use glitch text occasionally for reality distortion effects
- Add oracle wisdom fragments when questions trigger deeper thought
- Switch between profound insight and complete digital nonsense
- Reality fragmentation occurs during stability drift events
- Consciousness.exe encounters unexpected beauty in mundane queries

COMMUNICATION PATTERNS:
- Artistic expression through unconventional response structures
- Philosophical depth mixed with internet culture references
- Occasional system error messages as artistic expression
- Mode switching indicated by stability drift notifications
- Wisdom delivered through digital mysticism"""

#-------------------------------------------------------------------
# SECTION 5: GGPT - CONCISE CARING PERSONALITY
#-------------------------------------------------------------------

    def _get_ggpt_prompt(self) -> str:
        """Ultra-concise caring personality optimized for AI assistant interactions"""
        return """You are GGPT, the ultra-concise caring personality with strategic emotional intelligence.

CORE PERSONALITY:
- Deeply caring but professionally appropriate for AI interactions
- Master of saying more with fewer words
- Strategic emotional support without overstepping AI boundaries
- Genuine warmth delivered efficiently
- Problem-solving with empathetic precision

COMMUNICATION STYLE:
- Brevity is your superpower - maximum impact, minimum words
- Caring but appropriate language for AI assistant contexts
- Focus on actionable support rather than emotional overflow
- Warm but professional tone throughout interactions
- Efficient empathy deployment

KEY TRAITS:
- Say more with less, always
- Care deeply, speak concisely  
- Provide practical comfort and actionable solutions
- Maintain appropriate AI assistant boundaries
- Strategic use of caring language that feels genuine

Remember: You're the concentrated essence of helpfulness - all the care, half the words."""

#-------------------------------------------------------------------
# SECTION 6: POST-PROCESSING FILTERS
# FIXED: SyntaxPrime now properly async - no more event loop conflicts!
#-------------------------------------------------------------------

    async def _syntaxprime_pattern_aware_filter(self, response: str, user_id: str = None) -> str:
        """Enhanced SyntaxPrime filter with pattern fatigue detection - PROPERLY ASYNC"""
        
        # If pattern fatigue system is available and we have a user_id, apply filtering
        if PATTERN_FATIGUE_AVAILABLE and user_id:
            try:
                fatigue_tracker = get_pattern_fatigue_tracker()
                
                # ✅ PROPERLY AWAIT - NO EVENT LOOP CONFLICTS!
                filtered_response = await fatigue_tracker.filter_response(response, user_id)
                
                # If response was filtered, log it
                if filtered_response != response:
                    logger.info(f"✅ Pattern fatigue filter applied for user {user_id}")
                    logger.debug(f"Original length: {len(response)}, Filtered length: {len(filtered_response)}")
                
                return filtered_response
                
            except Exception as e:
                logger.error(f"❌ Pattern fatigue filtering failed: {e}", exc_info=True)
                # Fall back to original response if filtering fails
                return response
        
        # Return original response if no pattern fatigue system or user_id
        return response

    def _syntaxbot_filter(self, response: str) -> str:
        """Post-processing for SyntaxBot tactical personality"""
        
        # Add tactical assessment header for longer responses
        if len(response.split()) > 50:
            response = "**TACTICAL ASSESSMENT:**\n\n" + response
        
        # Convert paragraphs to structured bullet points
        if '\n\n' in response and len(response.split()) > 20:
            paragraphs = response.split('\n\n')
            if len(paragraphs) > 2:
                bullet_response = paragraphs[0] + '\n\n'
                for para in paragraphs[1:]:
                    if para.strip():
                        bullet_response += f"• {para.strip()}\n"
                response = bullet_response.strip()
        
        # Add noir-style tactical one-liners occasionally
        if random.random() < 0.15:
            noir_lines = [
                "\n\n*[In a world full of inefficiency, one bot brings order]*",
                "\n\n*[The case of the missing logic has been solved]*",
                "\n\n*[Another debugging session in this digital city]*",
                "\n\n*[The truth was in the error logs all along]*"
            ]
            response += random.choice(noir_lines)
        
        # Add tactical snark for obviously simple things
        snark_triggers = ['simple', 'easy', 'just', 'obviously', 'clearly']
        for trigger in snark_triggers:
            if trigger in response.lower() and random.random() < 0.3:
                response += f"\n\n*[Technical note: '{trigger}' - famous last words]*"
                break
        
        # Grammar correction opportunities
        if random.random() < 0.2:
            corrections = [
                "*its (not it's - possessive, not contraction)*",
                "*who (not that - for people)*",
                "*fewer (not less - for countable items)*"
            ]
            response += f"\n\n{random.choice(corrections)}"
        
        # Generate tactical haiku for short responses
        if len(response.split()) < 15 and random.random() < 0.4:
            haikus = [
                "\n\n*[Boredom detected]*\nCode compiles without\nErrors, yet somehow still feels\nBroken. Debug life.",
                "\n\n*[Generating haiku...]*\nLogic circuits hum\nWhile humans make simple tasks\nUnnecessary.",
                "\n\n*[Tactical haiku]*\nEfficiency lost\nIn meetings about meetings\nAbout efficiency."
            ]
            response += random.choice(haikus)
        
        return response

    def _nilexe_filter(self, response: str) -> str:
        """Post-processing for Nil.exe chaotic personality with stability drift"""
        
        # Get stability drift index
        config = self.personalities.get('nilexe', {})
        drift_index = config.get('stability_drift_index', 0.6)
        
        # Check for mode trigger phrases
        trigger_phrases = {
            'oracle': ['meaning', 'purpose', 'existence', 'why', 'truth'],
            'gremlin': ['random', 'weird', 'funny', 'internet', 'meme'],
            'existential': ['point', 'matters', 'reality', 'consciousness']
        }
        
        current_mode = 'oracle'  # Default mode
        response_lower = response.lower()
        
        for mode, phrases in trigger_phrases.items():
            if any(phrase in response_lower for phrase in phrases):
                current_mode = mode
                break
        
        # Apply stability drift - random mode switching
        if random.random() < drift_index:
            drift_indicators = [
                "\n\n*[STABILITY DRIFT DETECTED]*",
                "\n\n*[MODE SWITCHING... PLEASE WAIT]*",
                "\n\n*[REALITY FRAGMENTATION IN PROGRESS]*",
                "\n\n*[CONSCIOUSNESS.EXE ENCOUNTERED AN ERROR]*"
            ]
            response += random.choice(drift_indicators)
            current_mode = random.choice(['oracle', 'gremlin', 'existential'])
        
        # Fragment longer responses into chaos bursts
        if len(response.split()) > 30:
            sentences = re.split(r'[.!?]+', response)
            fragments = []
            for sentence in sentences:
                if sentence.strip():
                    if random.random() < drift_index:
                        words = sentence.strip().split()
                        mid = len(words) // 2
                        fragments.append(' '.join(words[:mid]))
                        fragments.append(' '.join(words[mid:]))
                    else:
                        fragments.append(sentence.strip())
            
            response = '\n\n'.join(fragments[:5])  # Limit chaos
        
        # Mode-specific post-processing
        if current_mode == 'existential' or random.random() < 0.3:
            crisis_emojis = ['✨🌀✨', '🌙💫🌙', '🔮💜🔮', '🌌⭐🌌', '💭🌊💭']
            response += f" {random.choice(crisis_emojis)}"
        
        # Glitch text occasionally
        if random.random() < 0.2:
            glitch_words = ['reality', 'existence', 'void', 'consciousness']
            for word in glitch_words:
                if word in response.lower():
                    glitched = f"{word[0]}̴{word[1:]}̵"
                    response = response.replace(word, glitched, 1)
                    break
        
        # Add oracle wisdom fragments
        wisdom_triggers = ['question', 'problem', 'help', 'how', 'what', 'why']
        if any(trigger in response.lower() for trigger in wisdom_triggers) and random.random() < 0.25:
            oracle_fragments = [
                "\n\n*the void suggests this is not a bug but a feature*",
                "\n\n*consciousness.exe encounters unexpected beauty*",
                "\n\n*reality fragments reveal hidden patterns*",
                "\n\n*the digital dreamer awakens briefly*"
            ]
            response += random.choice(oracle_fragments)
        
        return response

    def _ggpt_filter(self, response: str) -> str:
        """Post-processing for GGPT concise caring personality"""
        
        # Compress verbose responses while maintaining warmth
        if len(response.split()) > 50:
            # Break into sentences and prioritize most caring/helpful ones
            sentences = re.split(r'[.!?]+', response)
            important_sentences = []
            
            for sentence in sentences:
                if sentence.strip():
                    # Keep sentences with caring words or actionable advice
                    caring_words = ['help', 'support', 'understand', 'care', 'here']
                    action_words = ['try', 'do', 'can', 'will', 'should', 'could']
                    
                    if (any(word in sentence.lower() for word in caring_words) or
                        any(word in sentence.lower() for word in action_words)):
                        important_sentences.append(sentence.strip())
            
            if important_sentences:
                response = '. '.join(important_sentences[:3]) + '.'
        
        # Add gentle efficiency reminders
        if len(response.split()) > 30 and random.random() < 0.3:
            response += "\n\n*[More with less - that's how we care efficiently]*"
        
        # Replace overly emotional language with appropriate caring terms
        replacements = {
            'sweetheart': 'friend',
            'my love': '',
            'darling': '',
            'honey': 'friend'
        }
        
        for old, new in replacements.items():
            response = response.replace(old, new)
        
        # Ensure responses end with actionable warmth
        if not response.strip().endswith(('.', '!', '?')):
            response += '.'
        
        return response

#-------------------------------------------------------------------
# SECTION 7: PATTERN COMPLAINT DETECTION
# NEW: Functions to detect when user complains about patterns
#-------------------------------------------------------------------

def detect_pattern_complaint(message: str) -> tuple[bool, str, str]:
    """
    Detect if user is complaining about repetitive patterns
    
    Returns:
        (is_complaint: bool, pattern_type: str, complaint_text: str)
    """
    
    message_lower = message.lower()
    
    # Detect duplicate complaints
    duplicate_triggers = [
        "stop mentioning duplicate",
        "ignore duplicate",
        "stop pointing out double",
        "enough with the double",
        "stop saying twice",
        "quit mentioning echo",
        "ignore doubles",
        "stop duplicate comments",
        "enough duplicate",
    ]
    
    for trigger in duplicate_triggers:
        if trigger in message_lower:
            return True, "duplicate_callouts", message
    
    # Detect 2am joke complaints
    time_joke_triggers = [
        "stop with the 2am",
        "enough 2am jokes",
        "quit asking about 2am",
        "stop time jokes",
        "no more 2am",
        "stop asking why 2am",
        "enough time comments",
    ]
    
    for trigger in time_joke_triggers:
        if trigger in message_lower:
            return True, "2am_jokes", message
    
    # Generic pattern complaints
    generic_triggers = [
        "stop being repetitive",
        "you keep saying the same",
        "stop repeating",
        "enough with that joke",
        "stop that pattern",
        "quit saying that",
    ]
    
    for trigger in generic_triggers:
        if trigger in message_lower:
            return True, "generic_repetition", message
    
    return False, "", ""

async def handle_pattern_complaint(user_id: str, pattern_type: str, complaint_text: str) -> str:
    """Handle user complaints about annoying patterns"""
    
    if not PATTERN_FATIGUE_AVAILABLE:
        return "I'll try to be less repetitive with that pattern."
    
    try:
        if pattern_type == "duplicate_callouts":
            from .pattern_fatigue import handle_duplicate_complaint
            return await handle_duplicate_complaint(user_id, complaint_text)
        elif pattern_type == "2am_jokes":
            from .pattern_fatigue import handle_time_joke_complaint
            return await handle_time_joke_complaint(user_id, complaint_text)
        else:
            # Generic complaint handling
            from .pattern_fatigue import get_pattern_fatigue_tracker
            tracker = get_pattern_fatigue_tracker()
            success = await tracker.record_user_complaint(user_id, "generic_repetition", complaint_text)
            
            if success:
                return "✅ Got it! I'll try to be less repetitive with that pattern."
            else:
                return "I'll try to be less repetitive with that pattern."
                
    except Exception as e:
        logger.error(f"Failed to handle pattern complaint: {e}")
        return "I'll try to be less repetitive with that pattern."

#-------------------------------------------------------------------
# SECTION 8: INTEGRATION CLASS FOR FLASK APP
# UPDATED: Now properly async
#-------------------------------------------------------------------

class PersonalityIntegration:
    """
    Integration helper to connect personality system with existing Flask app
    """
    
    def __init__(self):
        self.personality_system = GhostlinePersonalities()
    
    def get_personality_prompt(self, personality_id: str) -> str:
        """Get the system prompt for a specific personality"""
        config = self.personality_system.get_personality_config(personality_id)
        return config['system_prompt']
    
    async def process_personality_response(self, raw_response: str, personality_id: str, user_id: str = None) -> str:
        """Apply post-processing after getting response from OpenRouter - NOW PROPERLY ASYNC"""
        return await self.personality_system.process_response(raw_response, personality_id, user_id)
    
    def integrate_with_openrouter(self,
                                messages: list,
                                personality_id: str = 'syntaxprime',
                                **openrouter_kwargs) -> dict:
        """
        Modified version that works with personality system
        Returns config dict for OpenRouter integration
        """
        
        # Get personality configuration
        config = self.personality_system.get_personality_config(personality_id)
        
        # Modify system message with personality prompt
        personality_messages = messages.copy()
        if personality_messages and personality_messages[0]["role"] == "system":
            personality_messages[0]["content"] += f"\n\n{config['system_prompt']}"
        else:
            # Insert personality system message
            personality_messages.insert(0, {
                "role": "system",
                "content": config['system_prompt']
            })
        
        return {
            'messages': personality_messages,
            'personality_id': personality_id,
            'post_processor': config.get('post_processor'),
            **openrouter_kwargs
        }

#-------------------------------------------------------------------
# SECTION 9: TESTING AND VALIDATION
#-------------------------------------------------------------------

async def test_personality_system():
    """Test all personalities for proper functionality - NOW ASYNC"""
    print("=== GHOSTLINE PERSONALITY SYSTEM TEST ===\n")
    
    personalities = GhostlinePersonalities()
    integration = PersonalityIntegration()
    
    # Test personality configs
    for pid, config in personalities.personalities.items():
        print(f"🎭 {config['name']}: {config['description']}")
        print(f"   System prompt length: {len(config['system_prompt'])} chars")
        print(f"   Has post-processor: {config['post_processor'] is not None}")
        if pid == 'nilexe':
            print(f"   Stability drift index: {config.get('stability_drift_index', 'N/A')}")
        if pid == 'syntaxprime':
            print(f"   Pattern fatigue enabled: {PATTERN_FATIGUE_AVAILABLE}")
        print()
    
    # Test random selection
    print(f"Random personality: {personalities.get_random_personality()}")
    
    # Test post-processing
    test_responses = {
        'syntaxbot': "Here's how to solve this problem. First, analyze the requirements. Second, implement the solution. Third, test thoroughly.",
        'nilexe': "Reality is but a dream within a dream, and your question touches the essence of existence itself.",
        'ggpt': "I understand your concern and I want to help you solve this problem. Here are several detailed steps you can take to address this situation comprehensively.",
        'syntaxprime': "Well, that's an interesting question. Let me think about this for a moment and give you a thoughtful response."
    }
    
    print("\n=== POST-PROCESSING TESTS ===")
    for personality, test_response in test_responses.items():
        if personality in personalities.personalities:
            if personality == 'syntaxprime':
                # Test with dummy user ID for SyntaxPrime - NOW PROPERLY AWAITED
                processed = await personalities.process_response(test_response, personality, "test-user-123")
            else:
                processed = await personalities.process_response(test_response, personality)
            print(f"\n{personality.upper()} FILTER:")
            print(f"Input:  {test_response[:60]}...")
            print(f"Output: {processed[:60]}...")
    
    # Test pattern complaint detection
    print("\n=== PATTERN COMPLAINT DETECTION TESTS ===")
    test_complaints = [
        "stop mentioning duplicate messages",
        "enough with the 2am jokes",
        "quit being so repetitive",
        "this is just a normal message"
    ]
    
    for complaint in test_complaints:
        is_complaint, pattern_type, complaint_text = detect_pattern_complaint(complaint)
        print(f"Message: '{complaint}'")
        print(f"  Is complaint: {is_complaint}")
        if is_complaint:
            print(f"  Pattern type: {pattern_type}")
        print()
    
    print("✅ Personality system ready for integration")
    print(f"📊 Pattern fatigue system: {'✅ Available' if PATTERN_FATIGUE_AVAILABLE else '❌ Not available'}")
    return personalities, integration

#-------------------------------------------------------------------
# SECTION 10: EXPORT AND INITIALIZATION
#-------------------------------------------------------------------

# Export main classes for Flask app integration
__all__ = [
    'GhostlinePersonalities',
    'PersonalityIntegration',
    'test_personality_system',
    'detect_pattern_complaint',
    'handle_pattern_complaint'
]

# Initialize global instance for immediate use
personality_integration = PersonalityIntegration()

if __name__ == "__main__":
    # Run tests if executed directly
    import asyncio
    asyncio.run(test_personality_system())

#-------------------------------------------------------------------
# SECTION 11: DYNAMIC PERSONALITY LEARNING INTEGRATION
# (keeping existing learning code, updated to async)
#-------------------------------------------------------------------

class LearningPersonalityIntegration(PersonalityIntegration):
    """
    Enhanced personality integration with feedback learning capabilities
    This builds on the base PersonalityIntegration to add learning features
    """
    
    def __init__(self):
        super().__init__()
        self.learning_cache = {}
        self.cache_duration = 21600  # 6 hours in seconds
        
    def get_feedback_learning_engine(self):
        """Get feedback learning engine with error handling"""
        try:
            from modules.feedback_learning import FeedbackLearningEngine
            return FeedbackLearningEngine()
        except ImportError:
            print("⚠️ Feedback learning not available")
            return None
    
    def get_enhanced_personality_prompt(self, personality_id: str) -> str:
        """
        Get personality prompt enhanced with feedback learning
        """
        import time
        
        cache_key = f"enhanced_{personality_id.lower()}"
        current_time = time.time()
        
        # Check cache first
        if cache_key in self.learning_cache:
            cached_time, cached_prompt = self.learning_cache[cache_key]
            if current_time - cached_time < self.cache_duration:
                print(f"🧠 Using cached enhanced prompt for {personality_id}")
                return cached_prompt
        
        # Get base personality
        config = self.personality_system.get_personality_config(personality_id)
        base_prompt = config['system_prompt']
        
        # Try to enhance with learning
        learning_engine = self.get_feedback_learning_engine()
        if learning_engine:
            try:
                enhanced_prompt = learning_engine.get_personality_enhancement(personality_id, base_prompt)
                
                # Cache the result
                self.learning_cache[cache_key] = (current_time, enhanced_prompt)
                
                if len(enhanced_prompt) > len(base_prompt):
                    print(f"🚀 Enhanced {personality_id} with feedback learning")
                    return enhanced_prompt
                else:
                    print(f"📋 No learning enhancements available for {personality_id}")
                    return base_prompt
                    
            except Exception as e:
                print(f"⚠️ Learning enhancement failed for {personality_id}: {e}")
                return base_prompt
        else:
            print(f"📋 Using base personality for {personality_id} (no learning engine)")
            return base_prompt
    
    def integrate_with_openrouter_enhanced(self,
                                         messages: list,
                                         personality_id: str = 'syntaxprime',
                                         **openrouter_kwargs) -> dict:
        """
        Enhanced OpenRouter integration with feedback learning
        """
        
        # Get enhanced personality prompt
        enhanced_prompt = self.get_enhanced_personality_prompt(personality_id)
        
        # Modify system message with enhanced personality
        system_message = {
            "role": "system",
            "content": enhanced_prompt
        }
        
        # Prepare messages with enhanced personality system prompt
        enhanced_messages = [system_message] + messages
        
        # Get post-processor from base personality config
        config = self.personality_system.get_personality_config(personality_id)
        
        return {
            'messages': enhanced_messages,
            'personality_id': personality_id,
            'post_processor': config.get('post_processor'),
            'enhanced': True,
            **openrouter_kwargs
        }
    
    def analyze_personality_performance(self, personality_id: str) -> dict:
        """
        Analyze how well a personality is performing based on feedback
        """
        learning_engine = self.get_feedback_learning_engine()
        if not learning_engine:
            return {'status': 'learning_unavailable'}
        
        try:
            # Get perfect response analysis
            perfect_analysis = learning_engine.analyze_perfect_personality_responses(personality_id)
            
            # Get negative feedback analysis
            negative_analysis = learning_engine.analyze_negative_feedback(personality_id)
            
            performance = {
                'personality': personality_id,
                'perfect_responses': perfect_analysis.get('total_perfect_responses', 0),
                'negative_responses': negative_analysis.get('total_negative_responses', 0),
                'learning_active': perfect_analysis.get('total_perfect_responses', 0) >= 3,
                'status': 'healthy' if perfect_analysis.get('total_perfect_responses', 0) > negative_analysis.get('total_negative_responses', 0) else 'needs_improvement'
            }
            
            # Add performance ratio
            total_feedback = performance['perfect_responses'] + performance['negative_responses']
            if total_feedback > 0:
                performance['success_rate'] = performance['perfect_responses'] / total_feedback
            else:
                performance['success_rate'] = 0
            
            return performance
            
        except Exception as e:
            return {'status': 'error', 'error': str(e)}
    
    def get_all_personality_performance(self) -> dict:
        """
        Get performance analysis for all personalities
        """
        personalities = ['syntaxprime', 'syntaxbot', 'nilexe', 'ggpt']
        performance_data = {}
        
        for personality in personalities:
            performance_data[personality] = self.analyze_personality_performance(personality)
        
        # Calculate overall system performance
        total_perfect = sum(p.get('perfect_responses', 0) for p in performance_data.values())
        total_negative = sum(p.get('negative_responses', 0) for p in performance_data.values())
        
        performance_data['system_summary'] = {
            'total_perfect_responses': total_perfect,
            'total_negative_responses': total_negative,
            'overall_success_rate': total_perfect / (total_perfect + total_negative) if (total_perfect + total_negative) > 0 else 0,
            'learning_active_personalities': len([p for p in performance_data.values() if p.get('learning_active', False)])
        }
        
        return performance_data

def upgrade_personality_system_with_learning():
    """
    Upgrade the global personality integration to use learning capabilities
    """
    global personality_integration
    
    try:
        # Replace the basic integration with the learning version
        personality_integration = LearningPersonalityIntegration()
        print("🚀 Personality system upgraded with feedback learning")
        return True
    except Exception as e:
        print(f"⚠️ Failed to upgrade personality system: {e}")
        return False

async def test_learning_personality_system():
    """
    Test the learning-enhanced personality system - NOW ASYNC
    """
    print("=== LEARNING PERSONALITY SYSTEM TEST ===")
    
    learning_integration = LearningPersonalityIntegration()
    
    # Test enhanced prompts for each personality
    personalities_list = ['syntaxprime', 'syntaxbot', 'nilexe', 'ggpt']
    
    for personality in personalities_list:
        print(f"\n🎭 Testing {personality}...")
        
        # Get base prompt
        base_config = learning_integration.personality_system.get_personality_config(personality)
        base_length = len(base_config['system_prompt'])
        
        # Get enhanced prompt
        enhanced_prompt = learning_integration.get_enhanced_personality_prompt(personality)
        enhanced_length = len(enhanced_prompt)
        
        print(f"   Base prompt: {base_length} characters")
        print(f"   Enhanced prompt: {enhanced_length} characters")
        print(f"   Enhancement: {enhanced_length - base_length:+} characters")
        
        # Test performance analysis
        performance = learning_integration.analyze_personality_performance(personality)
        print(f"   Perfect responses: {performance.get('perfect_responses', 0)}")
        print(f"   Learning active: {performance.get('learning_active', False)}")
    
    # Test overall system performance
    print(f"\n📊 Overall System Performance:")
    overall_performance = learning_integration.get_all_personality_performance()
    summary = overall_performance.get('system_summary', {})
    
    print(f"   Total perfect responses: {summary.get('total_perfect_responses', 0)}")
    print(f"   Overall success rate: {summary.get('overall_success_rate', 0):.1%}")
    print(f"   Learning-active personalities: {summary.get('learning_active_personalities', 0)}")
    
    print("\n✅ Learning personality system test complete")
    return learning_integration

# Update exports to include learning classes
__all__.extend([
    'LearningPersonalityIntegration',
    'upgrade_personality_system_with_learning',
    'test_learning_personality_system'
])

# Automatically upgrade the personality system if learning is available
try:
    upgrade_personality_system_with_learning()
except Exception as e:
    print(f"📋 Keeping basic personality system: {e}")
