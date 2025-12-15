#!/usr/bin/env python3
"""
Integration Info for Google Trends Module
Comprehensive health checks and system information for the Google Trends integration

Key Features:
- Complete system health monitoring
- Component status verification
- Database connectivity and data analysis
- Performance metrics and statistics
- Configuration validation
- Integration testing utilities
"""

import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta, timezone
import logging
import os
import sys
from dataclasses import dataclass

from modules.core.database import db_manager

# Import singleton getters for all module components
try:
    from .keyword_expander import get_keyword_expander
    from .trends_client import get_google_trends_client
    from .keyword_monitor import get_keyword_monitor
    from .database_manager import get_trends_database
    from .trend_analyzer import get_trend_analyzer
    from .opportunity_detector import get_opportunity_detector
    from .rss_cross_reference import get_rss_cross_reference
except ImportError:
    # Fallback for direct execution - these will be None
    get_keyword_expander = None
    get_google_trends_client = None
    get_keyword_monitor = None
    get_trends_database = None
    get_trend_analyzer = None
    get_opportunity_detector = None
    get_rss_cross_reference = None

logger = logging.getLogger(__name__)

# Valid business areas whitelist for safe table queries
VALID_BUSINESS_AREAS = frozenset([
    'amcf', 'bcdodge', 'damnitcarl', 'mealsnfeelz', 'roseandangel', 'tvsignals'
])


@dataclass
class ComponentStatus:
    """Status information for a module component"""
    name: str
    available: bool
    version: Optional[str] = None
    last_used: Optional[datetime] = None
    error_message: Optional[str] = None
    performance_metrics: Optional[Dict[str, Any]] = None


@dataclass
class SystemHealth:
    """Overall system health status"""
    healthy: bool
    components_available: int
    components_total: int
    database_connected: bool
    data_quality_score: float  # 0.0 to 1.0
    last_monitoring_cycle: Optional[datetime]
    critical_issues: List[str]
    warnings: List[str]


# Singleton instance
_integration_info_manager_instance: Optional['GoogleTrendsIntegrationInfo'] = None


def get_integration_info_manager() -> 'GoogleTrendsIntegrationInfo':
    """Get singleton GoogleTrendsIntegrationInfo instance"""
    global _integration_info_manager_instance
    if _integration_info_manager_instance is None:
        _integration_info_manager_instance = GoogleTrendsIntegrationInfo()
    return _integration_info_manager_instance


class GoogleTrendsIntegrationInfo:
    """Comprehensive system information and health monitoring"""
    
    def __init__(self):
        # Component singleton getters registry
        self.component_getters = {
            'keyword_expander': get_keyword_expander,
            'trends_client': get_google_trends_client,
            'keyword_monitor': get_keyword_monitor,
            'database_manager': get_trends_database,
            'trend_analyzer': get_trend_analyzer,
            'opportunity_detector': get_opportunity_detector,
            'rss_cross_reference': get_rss_cross_reference
        }
        
        # Integration metadata
        self.integration_info = {
            'module_name': 'google_trends',
            'version': '1.0.0',
            'description': 'Google Trends monitoring with smart keyword expansion',
            'business_areas': list(VALID_BUSINESS_AREAS),
            'features': [
                'Smart keyword expansion (11.2x multiplier)',
                'Low threshold trend detection',
                'Cross-business correlation analysis',
                'RSS content correlation',
                'Opportunity detection and alerts',
                'User feedback training system'
            ]
        }
    
    async def get_integration_info(self) -> Dict[str, Any]:
        """Get basic integration information"""
        return {
            'integration_info': self.integration_info,
            'system_requirements': {
                'python_version': '3.8+',
                'required_packages': ['asyncpg', 'pytrends', 'pandas'],
                'database': 'PostgreSQL',
                'environment_variables': ['DATABASE_URL']
            },
            'configuration': {
                'monitoring_frequency': '2-3 times daily',
                'keywords_monitored': '51,474 expanded from 4,586 base',
                'alert_thresholds': {
                    'rising': 15,
                    'breakout': 25,
                    'momentum': 20,
                    'stable_high': 40
                },
                'rate_limiting': {
                    'requests_per_day': 800,
                    'safety_margin': '45% under Google limits',
                    'batch_size': 5
                }
            }
        }
    
    async def check_module_health(self) -> SystemHealth:
        """Comprehensive module health check"""
        critical_issues = []
        warnings = []
        
        # Check database connectivity
        database_connected = await self._check_database_connection()
        if not database_connected:
            critical_issues.append("Database connection failed")
        
        # Check component availability
        component_status = await self._check_all_components()
        components_available = sum(1 for status in component_status.values() if status.available)
        components_total = len(component_status)
        
        if components_available < 4:  # Core components required
            critical_issues.append(f"Only {components_available}/{components_total} components available")
        
        # Check data quality
        data_quality_score = 0.0
        last_monitoring_cycle = None
        
        if database_connected:
            data_quality_score = await self._assess_data_quality()
            last_monitoring_cycle = await self._get_last_monitoring_cycle()
            
            if data_quality_score < 0.5:
                warnings.append(f"Low data quality score: {data_quality_score:.2f}")
            
            if last_monitoring_cycle:
                # Handle timezone-aware datetime comparison
                now = datetime.now(timezone.utc)
                if last_monitoring_cycle.tzinfo is None:
                    last_monitoring_cycle = last_monitoring_cycle.replace(tzinfo=timezone.utc)
                
                hours_since_last = (now - last_monitoring_cycle).total_seconds() / 3600
                if hours_since_last > 24:
                    warnings.append(f"Last monitoring cycle was {hours_since_last:.1f} hours ago")
        
        # Check environment variables
        required_env_vars = ['DATABASE_URL']
        missing_env = [var for var in required_env_vars if not os.getenv(var)]
        if missing_env:
            critical_issues.extend([f"Missing environment variable: {var}" for var in missing_env])
        
        # Determine overall health
        healthy = (
            database_connected and
            components_available >= 4 and
            len(critical_issues) == 0
        )
        
        return SystemHealth(
            healthy=healthy,
            components_available=components_available,
            components_total=components_total,
            database_connected=database_connected,
            data_quality_score=data_quality_score,
            last_monitoring_cycle=last_monitoring_cycle,
            critical_issues=critical_issues,
            warnings=warnings
        )
    
    async def _check_database_connection(self) -> bool:
        """Check if database connection is working"""
        conn = None
        try:
            conn = await db_manager.get_connection()
            await conn.fetchval('SELECT 1')
            return True
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            return False
        finally:
            if conn:
                await db_manager.release_connection(conn)
    
    async def _check_all_components(self) -> Dict[str, ComponentStatus]:
        """Check status of all module components"""
        component_status = {}
        
        for name, getter_func in self.component_getters.items():
            try:
                # Check if getter function is available
                if getter_func is None:
                    component_status[name] = ComponentStatus(
                        name=name,
                        available=False,
                        error_message="Getter function not imported"
                    )
                    continue
                
                # Try to get the singleton instance
                instance = getter_func()
                
                # Basic functionality test
                if hasattr(instance, 'health_check'):
                    health_result = await instance.health_check()
                    available = health_result.get('database_connected', True)
                else:
                    available = True
                
                component_status[name] = ComponentStatus(
                    name=name,
                    available=available,
                    version='1.0.0'
                )
                    
            except Exception as e:
                component_status[name] = ComponentStatus(
                    name=name,
                    available=False,
                    error_message=str(e)
                )
        
        return component_status
    
    async def _assess_data_quality(self) -> float:
        """Assess overall data quality (0.0 to 1.0)"""
        conn = None
        try:
            conn = await db_manager.get_connection()
            
            quality_metrics = {}
            
            # Check table existence
            tables_exist = await conn.fetchval('''
                SELECT COUNT(*) FROM information_schema.tables 
                WHERE table_name IN ('trend_monitoring', 'trend_opportunities', 'expanded_keywords_for_trends')
            ''')
            quality_metrics['tables_exist'] = min(1.0, tables_exist / 3.0)
            
            # Check data recency
            recent_trends = await conn.fetchval('''
                SELECT COUNT(*) FROM trend_monitoring 
                WHERE created_at >= NOW() - INTERVAL '7 days'
            ''') or 0
            quality_metrics['data_recency'] = min(1.0, recent_trends / 50.0)  # Expect at least 50 recent trends
            
            # Check keyword expansion
            expanded_count = await conn.fetchval('''
                SELECT COUNT(*) FROM expanded_keywords_for_trends
            ''') or 0
            quality_metrics['keyword_expansion'] = min(1.0, expanded_count / 40000.0)  # Expect ~40k+ keywords
            
            # Check data distribution across business areas
            business_coverage = await conn.fetchval('''
                SELECT COUNT(DISTINCT business_area) FROM trend_monitoring
            ''') or 0
            quality_metrics['business_coverage'] = min(1.0, business_coverage / 6.0)  # 6 business areas
            
            # Calculate weighted average
            weights = {
                'tables_exist': 0.3,
                'data_recency': 0.3,
                'keyword_expansion': 0.2,
                'business_coverage': 0.2
            }
            
            weighted_score = sum(score * weights[metric] for metric, score in quality_metrics.items())
            return round(weighted_score, 3)
            
        except Exception as e:
            logger.error(f"Data quality assessment failed: {e}")
            return 0.0
        finally:
            if conn:
                await db_manager.release_connection(conn)
    
    async def _get_last_monitoring_cycle(self) -> Optional[datetime]:
        """Get timestamp of last monitoring cycle"""
        conn = None
        try:
            conn = await db_manager.get_connection()
            
            last_trend = await conn.fetchval('''
                SELECT MAX(created_at) FROM trend_monitoring
            ''')
            
            return last_trend
            
        except Exception:
            return None
        finally:
            if conn:
                await db_manager.release_connection(conn)
    
    async def get_system_statistics(self) -> Dict[str, Any]:
        """Get comprehensive system statistics"""
        conn = None
        try:
            conn = await db_manager.get_connection()
            
            # Basic counts
            stats = {}
            
            # Keyword statistics
            stats['keywords'] = {
                'total_expanded': await conn.fetchval('SELECT COUNT(*) FROM expanded_keywords_for_trends') or 0,
                'by_business_area': {}
            }
            
            for area in VALID_BUSINESS_AREAS:
                original_count = await conn.fetchval(
                    f'SELECT COUNT(*) FROM {area}_keywords WHERE is_active = true'
                ) or 0
                expanded_count = await conn.fetchval(
                    'SELECT COUNT(*) FROM expanded_keywords_for_trends WHERE business_area = $1', area
                ) or 0
                
                stats['keywords']['by_business_area'][area] = {
                    'original': original_count,
                    'expanded': expanded_count,
                    'expansion_ratio': round(expanded_count / original_count, 1) if original_count > 0 else 0
                }
            
            # Trend monitoring statistics
            stats['trends'] = {
                'total_monitored': await conn.fetchval('SELECT COUNT(*) FROM trend_monitoring') or 0,
                'last_7_days': await conn.fetchval('''
                    SELECT COUNT(*) FROM trend_monitoring 
                    WHERE created_at >= NOW() - INTERVAL '7 days'
                ''') or 0,
                'average_score': await conn.fetchval('''
                    SELECT ROUND(AVG(trend_score), 1) FROM trend_monitoring 
                    WHERE trend_score IS NOT NULL AND created_at >= NOW() - INTERVAL '7 days'
                ''') or 0,
                'high_score_trends': await conn.fetchval('''
                    SELECT COUNT(*) FROM trend_monitoring 
                    WHERE trend_score >= 40 AND created_at >= NOW() - INTERVAL '7 days'
                ''') or 0
            }
            
            # Opportunity statistics
            stats['opportunities'] = {
                'total_created': await conn.fetchval('SELECT COUNT(*) FROM trend_opportunities') or 0,
                'active': await conn.fetchval('''
                    SELECT COUNT(*) FROM trend_opportunities 
                    WHERE processed = FALSE AND optimal_content_window_end > NOW()
                ''') or 0,
                'by_urgency': {}
            }
            
            urgency_levels = ['critical', 'high', 'medium', 'low']
            for urgency in urgency_levels:
                count = await conn.fetchval('''
                    SELECT COUNT(*) FROM trend_opportunities 
                    WHERE urgency_level = $1 AND created_at >= NOW() - INTERVAL '7 days'
                ''', urgency) or 0
                stats['opportunities']['by_urgency'][urgency] = count
            
            # Performance statistics - release connection before calling other methods
            await db_manager.release_connection(conn)
            conn = None
            
            stats['performance'] = {
                'monitoring_frequency': await self._calculate_monitoring_frequency(),
                'data_coverage_days': await self._calculate_data_coverage(),
                'expansion_efficiency': await self._calculate_expansion_efficiency()
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get system statistics: {e}")
            return {'error': str(e)}
        finally:
            if conn:
                await db_manager.release_connection(conn)
    
    async def _calculate_monitoring_frequency(self) -> float:
        """Calculate average monitoring frequency (cycles per day)"""
        conn = None
        try:
            conn = await db_manager.get_connection()
            
            # Count distinct days with trend data in last 7 days
            monitoring_days = await conn.fetchval('''
                SELECT COUNT(DISTINCT DATE(created_at)) 
                FROM trend_monitoring 
                WHERE created_at >= NOW() - INTERVAL '7 days'
            ''') or 0
            
            # Count total monitoring events in last 7 days
            monitoring_events = await conn.fetchval('''
                SELECT COUNT(DISTINCT created_at) 
                FROM trend_monitoring 
                WHERE created_at >= NOW() - INTERVAL '7 days'
            ''') or 0
            
            if monitoring_days > 0:
                return round(monitoring_events / monitoring_days, 1)
            return 0.0
            
        except Exception:
            return 0.0
        finally:
            if conn:
                await db_manager.release_connection(conn)
    
    async def _calculate_data_coverage(self) -> int:
        """Calculate how many days of trend data we have"""
        conn = None
        try:
            conn = await db_manager.get_connection()
            
            coverage = await conn.fetchval('''
                SELECT COUNT(DISTINCT DATE(created_at)) 
                FROM trend_monitoring
            ''') or 0
            
            return coverage
            
        except Exception:
            return 0
        finally:
            if conn:
                await db_manager.release_connection(conn)
    
    async def _calculate_expansion_efficiency(self) -> float:
        """Calculate keyword expansion efficiency"""
        conn = None
        try:
            conn = await db_manager.get_connection()
            
            # Get total original keywords
            total_original = 0
            
            for area in VALID_BUSINESS_AREAS:
                count = await conn.fetchval(
                    f'SELECT COUNT(*) FROM {area}_keywords WHERE is_active = true'
                ) or 0
                total_original += count
            
            # Get total expanded keywords
            total_expanded = await conn.fetchval('SELECT COUNT(*) FROM expanded_keywords_for_trends') or 0
            
            if total_original > 0:
                return round(total_expanded / total_original, 1)
            return 0.0
            
        except Exception:
            return 0.0
        finally:
            if conn:
                await db_manager.release_connection(conn)
    
    async def run_integration_test(self) -> Dict[str, Any]:
        """Run comprehensive integration test"""
        test_results = {
            'test_timestamp': datetime.now(timezone.utc).isoformat(),
            'tests_passed': 0,
            'tests_failed': 0,
            'test_details': {}
        }
        
        # Test 1: Database connectivity
        try:
            db_connected = await self._check_database_connection()
            test_results['test_details']['database_connection'] = {
                'passed': db_connected,
                'message': 'Database connection successful' if db_connected else 'Database connection failed'
            }
            if db_connected:
                test_results['tests_passed'] += 1
            else:
                test_results['tests_failed'] += 1
        except Exception as e:
            test_results['test_details']['database_connection'] = {
                'passed': False,
                'message': f'Database test error: {e}'
            }
            test_results['tests_failed'] += 1
        
        # Test 2: Component initialization
        try:
            components = await self._check_all_components()
            available_components = sum(1 for c in components.values() if c.available)
            total_components = len(components)
            
            passed = available_components >= 4
            test_results['test_details']['component_initialization'] = {
                'passed': passed,
                'message': f'{available_components}/{total_components} components available',
                'components': {name: status.available for name, status in components.items()}
            }
            if passed:
                test_results['tests_passed'] += 1
            else:
                test_results['tests_failed'] += 1
        except Exception as e:
            test_results['test_details']['component_initialization'] = {
                'passed': False,
                'message': f'Component test error: {e}'
            }
            test_results['tests_failed'] += 1
        
        # Test 3: Data quality
        try:
            data_quality = await self._assess_data_quality()
            passed = data_quality >= 0.3  # Lower threshold for testing
            
            test_results['test_details']['data_quality'] = {
                'passed': passed,
                'message': f'Data quality score: {data_quality:.2f}',
                'score': data_quality
            }
            if passed:
                test_results['tests_passed'] += 1
            else:
                test_results['tests_failed'] += 1
        except Exception as e:
            test_results['test_details']['data_quality'] = {
                'passed': False,
                'message': f'Data quality test error: {e}'
            }
            test_results['tests_failed'] += 1
        
        # Test 4: System functionality (basic operations)
        conn = None
        try:
            conn = await db_manager.get_connection()
            
            # Check if we can query trend data
            trend_count = await conn.fetchval('SELECT COUNT(*) FROM trend_monitoring')
            
            # Check if we can query opportunities
            opp_count = await conn.fetchval('SELECT COUNT(*) FROM trend_opportunities')
            
            passed = True  # If we get here without exception, basic operations work
            test_results['test_details']['system_functionality'] = {
                'passed': passed,
                'message': f'Basic operations successful (trends: {trend_count}, opportunities: {opp_count})',
                'trend_count': trend_count,
                'opportunity_count': opp_count
            }
            test_results['tests_passed'] += 1
            
        except Exception as e:
            test_results['test_details']['system_functionality'] = {
                'passed': False,
                'message': f'System functionality test error: {e}'
            }
            test_results['tests_failed'] += 1
        finally:
            if conn:
                await db_manager.release_connection(conn)
        
        # Calculate overall test result
        total_tests = test_results['tests_passed'] + test_results['tests_failed']
        test_results['overall_success'] = test_results['tests_passed'] == total_tests
        test_results['success_rate'] = round(test_results['tests_passed'] / total_tests, 2) if total_tests > 0 else 0
        
        return test_results


# ============================================================================
# PUBLIC API FUNCTIONS
# ============================================================================

async def get_integration_info() -> Dict[str, Any]:
    """Get comprehensive integration information"""
    info_manager = get_integration_info_manager()
    return await info_manager.get_integration_info()


async def check_module_health() -> Dict[str, Any]:
    """Check module health and return status"""
    info_manager = get_integration_info_manager()
    health = await info_manager.check_module_health()
    
    # Check if health is a dict or an object
    if isinstance(health, dict):
        return health
    
    # If it's an object, convert to dict
    return {
        'healthy': getattr(health, 'healthy', False),
        'components_available': getattr(health, 'components_available', 0),
        'components_total': getattr(health, 'components_total', 0),
        'database_connected': getattr(health, 'database_connected', False),
        'data_quality_score': getattr(health, 'data_quality_score', 0.0),
        'last_monitoring_cycle': health.last_monitoring_cycle.isoformat() if hasattr(health, 'last_monitoring_cycle') and health.last_monitoring_cycle else None,
        'critical_issues': getattr(health, 'critical_issues', []),
        'warnings': getattr(health, 'warnings', [])
    }


async def get_system_statistics() -> Dict[str, Any]:
    """Get comprehensive system statistics"""
    info_manager = get_integration_info_manager()
    return await info_manager.get_system_statistics()


async def run_integration_test() -> Dict[str, Any]:
    """Run comprehensive integration test"""
    info_manager = get_integration_info_manager()
    return await info_manager.run_integration_test()


# ============================================================================
# TESTING
# ============================================================================

async def test_integration_info():
    """Test the integration info functionality"""
    print("🧪 TESTING GOOGLE TRENDS INTEGRATION INFO")
    print("=" * 50)
    
    # Test basic info
    print("\n📋 Integration info...")
    info = await get_integration_info()
    print(f"   Module: {info['integration_info']['module_name']} v{info['integration_info']['version']}")
    print(f"   Features: {len(info['integration_info']['features'])} features")
    print(f"   Business areas: {len(info['integration_info']['business_areas'])} areas")
    
    # Test health check
    print("\n🏥 Health check...")
    health = await check_module_health()
    print(f"   Overall health: {'✅ Healthy' if health['healthy'] else '❌ Unhealthy'}")
    print(f"   Components: {health['components_available']}/{health['components_total']}")
    print(f"   Database: {'✅ Connected' if health['database_connected'] else '❌ Disconnected'}")
    print(f"   Data quality: {health['data_quality_score']:.2f}")
    
    if health['critical_issues']:
        print(f"   Critical issues: {health['critical_issues']}")
    if health['warnings']:
        print(f"   Warnings: {health['warnings']}")
    
    # Test statistics
    print("\n📊 System statistics...")
    stats = await get_system_statistics()
    
    if 'keywords' in stats:
        print(f"   Keywords expanded: {stats['keywords']['total_expanded']:,}")
        print(f"   Trends monitored: {stats['trends']['total_monitored']:,}")
        print(f"   Active opportunities: {stats['opportunities']['active']}")
    
    # Test integration
    print("\n🔧 Integration test...")
    test_results = await run_integration_test()
    print(f"   Tests passed: {test_results['tests_passed']}")
    print(f"   Tests failed: {test_results['tests_failed']}")
    print(f"   Success rate: {test_results['success_rate']:.0%}")
    print(f"   Overall success: {'✅' if test_results['overall_success'] else '❌'}")
    
    print("\n✅ Integration info test complete!")


if __name__ == "__main__":
    asyncio.run(test_integration_info())
