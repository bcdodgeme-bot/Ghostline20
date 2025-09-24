# modules/ai/feedback_processor.py
"""
Feedback Learning Processor for Syntax Prime V2
Handles 👍👎🖕 feedback system and gradual personality adaptation
"""

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import json
import logging

from ..core.database import db_manager

logger = logging.getLogger(__name__)

class FeedbackProcessor:
    """
    Processes user feedback and implements gradual learning for personality adaptation
    
    Feedback Types:
    - 👍 (good): Reinforce technical approach and factual accuracy
    - 👎 (bad): Avoid this approach entirely  
    - 🖕 (personality): Perfect personality - more of this exact energy!
    """
    
    def __init__(self):
        self.feedback_types = {
            'good': 'good_answer',
            'bad': 'bad_answer',
            'personality': 'good_personality'
        }
        
        # Learning parameters
        self.adaptation_threshold = 5  # Min feedback needed before adaptation
        self.learning_window_days = 14  # Consider feedback from last 14 days
        self.max_adaptations_per_day = 3  # Limit learning speed
        
        # Cache for performance
        self.pattern_cache = {}
        self.cache_duration = timedelta(hours=1)
    
    async def record_feedback(self, 
                            user_id: str,
                            message_id: str,
                            thread_id: str,
                            feedback_type: str,
                            feedback_text: str = None,
                            personality_id: str = None,
                            response_metadata: Dict = None) -> Dict:
        """
        Record user feedback in the database
        
        Args:
            user_id: User providing feedback
            message_id: Message being rated
            thread_id: Conversation thread
            feedback_type: 'good', 'bad', or 'personality'
            feedback_text: Optional text feedback
            personality_id: Which personality was active
            response_metadata: Additional context about the response
            
        Returns:
            Dict with feedback ID and processing results
        """
        
        # Validate feedback type
        if feedback_type not in self.feedback_types:
            raise ValueError(f"Invalid feedback type: {feedback_type}. Must be one of: {list(self.feedback_types.keys())}")
        
        feedback_id = str(uuid.uuid4())
        internal_feedback_type = self.feedback_types[feedback_type]
        
        # Insert feedback record
        insert_query = """
        INSERT INTO user_feedback
        (id, user_id, message_id, thread_id, feedback_type, feedback_text, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, NOW())
        RETURNING id, created_at;
        """
        
        try:
            result = await db_manager.fetch_one(insert_query, 
                                               feedback_id, 
                                               user_id, 
                                               message_id, 
                                               thread_id, 
                                               internal_feedback_type, 
                                               feedback_text)
            
            # Process the feedback for learning
            learning_result = await self._process_feedback_for_learning(
                feedback_id,
                user_id,
                message_id,
                internal_feedback_type,
                personality_id,
                response_metadata
            )
            
            logger.info(f"Recorded {feedback_type} feedback: {feedback_id}")
            
            return {
                'feedback_id': feedback_id,
                'feedback_type': feedback_type,
                'internal_type': internal_feedback_type,
                'created_at': result['created_at'].isoformat(),
                'learning_result': learning_result,
                'emoji': self._get_feedback_emoji(feedback_type)
            }
            
        except Exception as e:
            logger.error(f"Failed to record feedback: {e}")
            raise
    
    def _get_feedback_emoji(self, feedback_type: str) -> str:
        """Get the emoji for a feedback type"""
        emoji_map = {
            'good': '👍',
            'bad': '👎', 
            'personality': '🖕'
        }
        return emoji_map.get(feedback_type, '❓')
    
    async def _process_feedback_for_learning(self,
                                           feedback_id: str,
                                           user_id: str,
                                           message_id: str,
                                           feedback_type: str,
                                           personality_id: str = None,
                                           response_metadata: Dict = None) -> Dict:
        """Process feedback for personality learning and adaptation"""
        
        # Get the original message content
        message_query = """
        SELECT content, model_used, knowledge_sources_used, extracted_preferences
        FROM conversation_messages
        WHERE id = $1;
        """
        
        message_result = await db_manager.fetch_one(message_query, message_id)
        
        if not message_result:
            return {'error': 'Message not found'}
        
        # Analyze the response for patterns
        response_analysis = self._analyze_response_patterns(
            message_result['content'],
            personality_id,
            response_metadata
        )
        
        # Determine if this feedback should trigger learning
        should_learn = await self._should_trigger_learning(
            user_id, 
            personality_id, 
            feedback_type
        )
        
        learning_result = {
            'feedback_processed': True,
            'response_analysis': response_analysis,
            'triggered_learning': should_learn,
            'learning_insights': {}
        }
        
        if should_learn:
            # Process learning based on feedback type
            if feedback_type == 'perfect_personality':
                learning_insights = await self._learn_from_perfect_personality(
                    user_id, personality_id, response_analysis
                )
            elif feedback_type == 'positive_response':
                learning_insights = await self._learn_from_positive_feedback(
                    user_id, personality_id, response_analysis
                )
            elif feedback_type == 'negative_response':
                learning_insights = await self._learn_from_negative_feedback(
                    user_id, personality_id, response_analysis
                )
            else:
                learning_insights = {}
            
            learning_result['learning_insights'] = learning_insights
            
            # Mark feedback as processed for learning
            await self._mark_feedback_processed(feedback_id)
        
        return learning_result
    
    def _analyze_response_patterns(self, 
                                 response_content: str, 
                                 personality_id: str,
                                 metadata: Dict = None) -> Dict:
        """Analyze response patterns for learning purposes"""
        
        analysis = {
            'response_length': len(response_content),
            'word_count': len(response_content.split()),
            'has_sarcasm': self._detect_sarcasm(response_content),
            'has_humor': self._detect_humor(response_content),
            'has_technical_content': self._detect_technical_content(response_content),
            'tone_indicators': self._detect_tone_indicators(response_content),
            'personality_markers': self._detect_personality_markers(response_content, personality_id)
        }
        
        # Add metadata if available
        if metadata:
            analysis['model_used'] = metadata.get('model_used')
            analysis['response_time_ms'] = metadata.get('response_time_ms')
            analysis['knowledge_sources_count'] = len(metadata.get('knowledge_sources_used', []))
        
        return analysis
    
    def _detect_sarcasm(self, content: str) -> bool:
        """Detect sarcastic language patterns"""
        sarcasm_patterns = [
            r'\boh (sure|yeah|right)\b',
            r'\babsolutely\b.*\b(not|never)\b',
            r'\bshocker\b',
            r'\bhow (convenient|surprising)\b',
            r'\bbrilliant\b',
            r'\bperfect\b.*\b(as always|like always)\b',
            r'\blet me guess\b',
            r'\bwhat a (surprise|shock)\b'
        ]
        
        import re
        content_lower = content.lower()
        
        return any(re.search(pattern, content_lower) for pattern in sarcasm_patterns)
    
    def _detect_humor(self, content: str) -> bool:
        """Detect humorous elements"""
        humor_indicators = [
            'lol', 'haha', '😄', '😂', '🤣',
            'funny', 'hilarious', 'joke', 'kidding',
            'pun', 'witty', 'clever'
        ]
        
        content_lower = content.lower()
        return any(indicator in content_lower for indicator in humor_indicators)
    
    def _detect_technical_content(self, content: str) -> bool:
        """Detect technical or analytical content"""
        technical_patterns = [
            'function', 'method', 'class', 'variable', 'database', 'query',
            'algorithm', 'implementation', 'architecture', 'framework',
            'debug', 'error', 'syntax', 'compile', 'deploy', 'server',
            'api', 'endpoint', 'json', 'http', 'response', 'request'
        ]
        
        content_lower = content.lower()
        return any(pattern in content_lower for pattern in technical_patterns)
    
    def _detect_tone_indicators(self, content: str) -> List[str]:
        """Detect tone and style indicators"""
        indicators = []
        
        content_lower = content.lower()
        
        # Direct/assertive
        if any(word in content_lower for word in ['obviously', 'clearly', 'definitely', 'absolutely']):
            indicators.append('assertive')
        
        # Helpful/supportive  
        if any(word in content_lower for word in ['help', 'support', 'assist', 'guide', 'show']):
            indicators.append('helpful')
        
        # Casual/informal
        if any(word in content_lower for word in ['yeah', 'yep', 'nope', 'gonna', 'wanna']):
            indicators.append('casual')
        
        # Formal/professional
        if any(word in content_lower for word in ['therefore', 'however', 'furthermore', 'consequently']):
            indicators.append('formal')
        
        return indicators
    
    def _detect_personality_markers(self, content: str, personality_id: str) -> List[str]:
        """Detect personality-specific markers"""
        markers = []
        content_lower = content.lower()
        
        if personality_id == 'syntaxprime':
            # SyntaxPrime markers: sarcasm + helpfulness
            if 'coffee' in content_lower or 'caffeine' in content_lower:
                markers.append('coffee_reference')
            if any(phrase in content_lower for phrase in ['eye roll', 'rolling eyes', 'sigh']):
                markers.append('eye_roll_energy')
            if 'chaos' in content_lower:
                markers.append('chaos_reference')
                
        elif personality_id == 'syntaxbot':
            # SyntaxBot markers: tactical precision
            if content.count('•') > 0 or content.count('-') > 2:
                markers.append('structured_formatting')
            if any(word in content_lower for word in ['tactical', 'assessment', 'operational']):
                markers.append('tactical_language')
                
        elif personality_id == 'nilexe':
            # Nil.exe markers: abstract chaos
            if any(word in content_lower for word in ['reality', 'existence', 'consciousness']):
                markers.append('existential_themes')
            if '...' in content or content.count('\n') > 3:
                markers.append('fragmented_structure')
                
        elif personality_id == 'ggpt':
            # GGPT markers: concise caring
            if len(content.split()) < 30:  # Short responses
                markers.append('concise_response')
            if any(word in content_lower for word in ['care', 'support', 'here for']):
                markers.append('caring_language')
        
        return markers
    
    async def _should_trigger_learning(self, 
                                     user_id: str, 
                                     personality_id: str, 
                                     feedback_type: str) -> bool:
        """Determine if feedback should trigger learning adaptation"""
        
        # Get recent feedback count for this personality
        recent_feedback_query = """
        SELECT COUNT(*) as feedback_count
        FROM user_feedback uf
        JOIN conversation_messages cm ON uf.message_id = cm.id
        WHERE uf.user_id = $1
        AND uf.feedback_type = $2
        AND uf.created_at > NOW() - INTERVAL '%s days'
        AND uf.processed_for_learning = false;
        """ % self.learning_window_days
        
        feedback_result = await db_manager.fetch_one(recent_feedback_query, user_id, feedback_type)
        feedback_count = feedback_result['feedback_count'] if feedback_result else 0
        
        # Check daily learning limit
        daily_learning_query = """
        SELECT COUNT(*) as daily_processed
        FROM user_feedback
        WHERE user_id = $1
        AND processed_for_learning = true
        AND processed_at > NOW() - INTERVAL '1 day';
        """
        
        daily_result = await db_manager.fetch_one(daily_learning_query, user_id)
        daily_processed = daily_result['daily_processed'] if daily_result else 0
        
        # Decision logic
        should_learn = (
            feedback_count >= self.adaptation_threshold and
            daily_processed < self.max_adaptations_per_day
        )
        
        logger.info(f"Learning decision for {personality_id}/{feedback_type}: "
                   f"feedback_count={feedback_count}, daily_processed={daily_processed}, "
                   f"should_learn={should_learn}")
        
        return should_learn
    
    async def _learn_from_perfect_personality(self, 
                                            user_id: str, 
                                            personality_id: str, 
                                            response_analysis: Dict) -> Dict:
        """Learn from 🖕 feedback - perfect personality responses"""
        
        # Get recent perfect personality feedback
        perfect_responses_query = """
        SELECT cm.content, cm.extracted_preferences, uf.created_at
        FROM user_feedback uf
        JOIN conversation_messages cm ON uf.message_id = cm.id
        WHERE uf.user_id = $1
        AND uf.feedback_type = 'perfect_personality'
        AND uf.created_at > NOW() - INTERVAL '%s days'
        ORDER BY uf.created_at DESC
        LIMIT 10;
        """ % self.learning_window_days
        
        perfect_responses = await db_manager.fetch_all(perfect_responses_query, user_id)
        
        # Analyze patterns in perfect responses
        patterns = {
            'average_length': 0,
            'sarcasm_frequency': 0,
            'common_markers': [],
            'tone_preferences': []
        }
        
        if perfect_responses:
            total_length = sum(len(r['content']) for r in perfect_responses)
            patterns['average_length'] = total_length / len(perfect_responses)
            
            sarcasm_count = sum(1 for r in perfect_responses if self._detect_sarcasm(r['content']))
            patterns['sarcasm_frequency'] = sarcasm_count / len(perfect_responses)
            
            # Extract common personality markers
            all_markers = []
            for response in perfect_responses:
                markers = self._detect_personality_markers(response['content'], personality_id)
                all_markers.extend(markers)
            
            from collections import Counter
            marker_counts = Counter(all_markers)
            patterns['common_markers'] = [marker for marker, count in marker_counts.most_common(5)]
        
        learning_insights = {
            'learning_type': 'perfect_personality',
            'personality_id': personality_id,
            'patterns_identified': patterns,
            'recommendations': self._generate_personality_recommendations(patterns, personality_id),
            'confidence': min(1.0, len(perfect_responses) / 10.0)  # More data = higher confidence
        }
        
        logger.info(f"Learning from perfect personality feedback: {learning_insights}")
        return learning_insights
    
    async def _learn_from_positive_feedback(self, 
                                          user_id: str, 
                                          personality_id: str, 
                                          response_analysis: Dict) -> Dict:
        """Learn from 👍 feedback - good technical responses"""
        
        learning_insights = {
            'learning_type': 'positive_response',
            'personality_id': personality_id,
            'reinforced_patterns': {
                'technical_depth': response_analysis.get('has_technical_content', False),
                'response_length': response_analysis.get('response_length', 0),
                'knowledge_usage': response_analysis.get('knowledge_sources_count', 0) > 0
            },
            'recommendations': ['Maintain current technical approach', 'Continue knowledge integration']
        }
        
        return learning_insights
    
    async def _learn_from_negative_feedback(self, 
                                          user_id: str, 
                                          personality_id: str, 
                                          response_analysis: Dict) -> Dict:
        """Learn from 👎 feedback - avoid these patterns"""
        
        learning_insights = {
            'learning_type': 'negative_response',
            'personality_id': personality_id,
            'patterns_to_avoid': {
                'response_style': response_analysis.get('tone_indicators', []),
                'technical_approach': response_analysis.get('has_technical_content', False),
                'response_length': response_analysis.get('response_length', 0)
            },
            'recommendations': ['Adjust technical depth', 'Modify response style', 'Review approach']
        }
        
        return learning_insights
    
    def _generate_personality_recommendations(self, patterns: Dict, personality_id: str) -> List[str]:
        """Generate specific recommendations based on learning patterns"""
        
        recommendations = []
        
        if personality_id == 'syntaxprime':
            if patterns.get('sarcasm_frequency', 0) > 0.7:
                recommendations.append("Maintain high sarcasm level - user loves the attitude")
            elif patterns.get('sarcasm_frequency', 0) < 0.3:
                recommendations.append("Increase sarcasm - user prefers more attitude")
            
            if 'coffee_reference' in patterns.get('common_markers', []):
                recommendations.append("Continue coffee/chaos references - resonates well")
                
            avg_length = patterns.get('average_length', 0)
            if avg_length > 500:
                recommendations.append("User prefers detailed responses - maintain length")
            elif avg_length < 200:
                recommendations.append("User prefers concise responses - keep it brief")
        
        elif personality_id == 'syntaxbot':
            if 'structured_formatting' in patterns.get('common_markers', []):
                recommendations.append("Continue using bullet points and structured responses")
            if 'tactical_language' in patterns.get('common_markers', []):
                recommendations.append("Maintain tactical/operational language style")
        
        elif personality_id == 'nilexe':
            if 'existential_themes' in patterns.get('common_markers', []):
                recommendations.append("Continue existential/abstract themes")
            if 'fragmented_structure' in patterns.get('common_markers', []):
                recommendations.append("Maintain fragmented, artistic response structure")
        
        elif personality_id == 'ggpt':
            if patterns.get('average_length', 0) < 200:
                recommendations.append("Continue concise, caring responses")
            if 'caring_language' in patterns.get('common_markers', []):
                recommendations.append("Maintain caring but professional tone")
        
        return recommendations or ["Continue current approach based on positive feedback"]
    
    async def _mark_feedback_processed(self, feedback_id: str):
        """Mark feedback as processed for learning"""
        
        update_query = """
        UPDATE user_feedback 
        SET processed_for_learning = true, processed_at = NOW()
        WHERE id = $1;
        """
        
        try:
            await db_manager.execute(update_query, feedback_id)
            logger.info(f"Marked feedback as processed: {feedback_id}")
        except Exception as e:
            logger.error(f"Failed to mark feedback as processed: {e}")
    
    async def get_feedback_summary(self, 
                                 user_id: str, 
                                 personality_id: str = None,
                                 days: int = 30) -> Dict:
        """Get summary of feedback for a user/personality"""
        
        base_query = """
        SELECT 
            uf.feedback_type,
            COUNT(*) as count,
            AVG(CASE WHEN uf.processed_for_learning THEN 1 ELSE 0 END) as processed_rate
        FROM user_feedback uf
        WHERE uf.user_id = $1
        AND uf.created_at > NOW() - INTERVAL '%s days'
        """ % days
        
        params = [user_id]
        
        if personality_id:
            # We need to join with messages to get personality context
            # For now, just get all feedback
            pass
        
        base_query += " GROUP BY uf.feedback_type ORDER BY count DESC;"
        
        try:
            results = await db_manager.fetch_all(base_query, *params)
            
            summary = {
                'user_id': user_id,
                'personality_id': personality_id,
                'period_days': days,
                'feedback_breakdown': {},
                'total_feedback': 0,
                'learning_active': False
            }
            
            for result in results:
                feedback_type = result['feedback_type']
                count = result['count']
                
                summary['feedback_breakdown'][feedback_type] = {
                    'count': count,
                    'processed_rate': float(result['processed_rate'])
                }
                summary['total_feedback'] += count
            
            # Determine if learning is active
            perfect_personality_count = summary['feedback_breakdown'].get('perfect_personality', {}).get('count', 0)
            summary['learning_active'] = perfect_personality_count >= self.adaptation_threshold
            
            return summary
            
        except Exception as e:
            logger.error(f"Failed to get feedback summary: {e}")
            return {'error': str(e)}
    
    async def get_learning_insights(self, 
                                  user_id: str, 
                                  personality_id: str,
                                  limit: int = 10) -> Dict:
        """Get recent learning insights for a personality"""
        
        # Get recent processed feedback with learning insights
        insights_query = """
        SELECT 
            uf.feedback_type,
            uf.created_at,
            uf.processed_at,
            cm.content as response_content
        FROM user_feedback uf
        JOIN conversation_messages cm ON uf.message_id = cm.id
        WHERE uf.user_id = $1
        AND uf.processed_for_learning = true
        AND uf.created_at > NOW() - INTERVAL '%s days'
        ORDER BY uf.processed_at DESC
        LIMIT $2;
        """ % self.learning_window_days
        
        try:
            results = await db_manager.fetch_all(insights_query, user_id, limit)
            
            insights = {
                'personality_id': personality_id,
                'recent_learning_events': [],
                'pattern_analysis': {},
                'recommendations': []
            }
            
            for result in results:
                # Analyze each learned response
                response_analysis = self._analyze_response_patterns(
                    result['response_content'], 
                    personality_id
                )
                
                insights['recent_learning_events'].append({
                    'feedback_type': result['feedback_type'],
                    'learned_at': result['processed_at'].isoformat(),
                    'response_patterns': response_analysis
                })
            
            # Generate overall pattern analysis
            if insights['recent_learning_events']:
                insights['pattern_analysis'] = self._analyze_learning_trends(
                    insights['recent_learning_events']
                )
                insights['recommendations'] = self._generate_learning_recommendations(
                    insights['pattern_analysis'], personality_id
                )
            
            return insights
            
        except Exception as e:
            logger.error(f"Failed to get learning insights: {e}")
            return {'error': str(e)}
    
    def _analyze_learning_trends(self, learning_events: List[Dict]) -> Dict:
        """Analyze trends in learning events"""
        
        if not learning_events:
            return {}
        
        # Count feedback types
        feedback_counts = {}
        sarcasm_trend = []
        length_trend = []
        
        for event in learning_events:
            feedback_type = event['feedback_type']
            feedback_counts[feedback_type] = feedback_counts.get(feedback_type, 0) + 1
            
            patterns = event['response_patterns']
            if patterns.get('has_sarcasm'):
                sarcasm_trend.append(1)
            else:
                sarcasm_trend.append(0)
            
            length_trend.append(patterns.get('response_length', 0))
        
        return {
            'feedback_distribution': feedback_counts,
            'sarcasm_frequency': sum(sarcasm_trend) / len(sarcasm_trend) if sarcasm_trend else 0,
            'average_response_length': sum(length_trend) / len(length_trend) if length_trend else 0,
            'learning_velocity': len(learning_events)  # How much learning is happening
        }
    
    def _generate_learning_recommendations(self, pattern_analysis: Dict, personality_id: str) -> List[str]:
        """Generate recommendations based on learning trends"""
        
        recommendations = []
        
        # Perfect personality feedback analysis
        perfect_count = pattern_analysis.get('feedback_distribution', {}).get('perfect_personality', 0)
        negative_count = pattern_analysis.get('feedback_distribution', {}).get('negative_response', 0)
        
        if perfect_count > negative_count:
            recommendations.append("Personality is well-tuned - maintain current energy level")
        elif negative_count > perfect_count:
            recommendations.append("Consider adjusting personality approach based on negative feedback")
        
        # Sarcasm analysis
        sarcasm_freq = pattern_analysis.get('sarcasm_frequency', 0)
        if personality_id == 'syntaxprime':
            if sarcasm_freq > 0.8:
                recommendations.append("High sarcasm success rate - continue current wit level")
            elif sarcasm_freq < 0.3:
                recommendations.append("Consider increasing sarcasm for SyntaxPrime personality")
        
        # Learning velocity
        learning_velocity = pattern_analysis.get('learning_velocity', 0)
        if learning_velocity > 5:
            recommendations.append("High learning activity - personality adaptation is active")
        elif learning_velocity < 2:
            recommendations.append("Low learning activity - consider more varied responses")
        
        return recommendations or ["Continue monitoring feedback patterns"]
    
    async def cleanup_old_feedback(self, days_to_keep: int = 90):
        """Clean up old feedback data"""
        
        cleanup_query = """
        DELETE FROM user_feedback
        WHERE created_at < NOW() - INTERVAL '%s days'
        AND processed_for_learning = true;
        """ % days_to_keep
        
        try:
            result = await db_manager.execute(cleanup_query)
            logger.info(f"Cleaned up old feedback data: {result}")
        except Exception as e:
            logger.error(f"Failed to cleanup old feedback: {e}")
    
    def clear_cache(self):
        """Clear the feedback processor cache"""
        self.pattern_cache.clear()
        logger.info("Feedback processor cache cleared")

# Global feedback processor
_feedback_processor = None

def get_feedback_processor() -> FeedbackProcessor:
    """Get the global feedback processor"""
    global _feedback_processor
    if _feedback_processor is None:
        _feedback_processor = FeedbackProcessor()
    return _feedback_processor

if __name__ == "__main__":
    # Test script
    async def test():
        print("Testing Feedback Learning Processor...")
        
        processor = FeedbackProcessor()
        
        # Test feedback recording (mock data)
        test_user_id = str(uuid.uuid4())
        test_message_id = str(uuid.uuid4())
        test_thread_id = str(uuid.uuid4())
        
        # This would fail in testing without proper database setup
        try:
            from ..core.database import db_manager
    
            thread_lookup_query = """
            SELECT thread_id FROM conversation_messages 
            WHERE id = $1 AND user_id = $2
            """
            
            message_result = await db_manager.fetch_one(thread_lookup_query,
                                                       feedback_request.message_id,
                                                       user_id)
            
            if not message_result:
                raise HTTPException(status_code=404, detail="Message not found")
            
            thread_id = message_result['thread_id']
            
            feedback_result = await processor.record_feedback(
                user_id=test_user_id,
                message_id=test_message_id,
                thread_id=test_thread_id,
                feedback_type='personality',  # 🖕
                personality_id='syntaxprime',
                response_metadata={'model_used': 'claude-3.5-sonnet'}
            )
            print(f"Recorded feedback: {feedback_result}")
        except Exception as e:
            print(f"Feedback recording test failed (expected without DB): {e}")
        
        # Test pattern analysis
        test_response = "Well, that's an absolutely brilliant question. Let me roll my eyes and give you a sarcastic but helpful answer about your coding adventure."
        
        patterns = processor._analyze_response_patterns(
            test_response, 
            'syntaxprime'
        )
        print(f"Pattern analysis: {patterns}")
        
        # Test emoji mapping
        emojis = {
            'good': processor._get_feedback_emoji('good'),
            'bad': processor._get_feedback_emoji('bad'),
            'personality': processor._get_feedback_emoji('personality')
        }
        print(f"Feedback emojis: {emojis}")
        
        print("Feedback Processor test completed!")
    
    asyncio.run(test())
