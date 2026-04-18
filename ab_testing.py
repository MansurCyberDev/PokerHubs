"""A/B Testing framework for optimizing features.

Allows testing different configurations on different user groups:
- Different gold prices
- Different skin prices
- Different game settings
- Different UI variations
"""
import hashlib
import json
import logging
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from database import aiosqlite, DB_NAME

logger = logging.getLogger(__name__)


class ExperimentStatus(Enum):
    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"


@dataclass
class Variant:
    """A/B test variant configuration."""
    name: str
    config: Dict[str, Any]
    weight: float = 0.5  # Traffic percentage (0.0 - 1.0)


@dataclass
class Experiment:
    """A/B test experiment definition."""
    id: str
    name: str
    description: str
    variants: List[Variant]
    status: ExperimentStatus
    target_users: Optional[List[int]] = None  # None = all users
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class ABTestingFramework:
    """Manage A/B tests and variant assignments."""
    
    def __init__(self):
        self.experiments: Dict[str, Experiment] = {}
        self._initialized = False
    
    async def init_tables(self):
        """Create A/B testing tables."""
        if self._initialized:
            return
        
        async with aiosqlite.connect(DB_NAME) as db:
            # Experiments table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS ab_experiments (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    config TEXT NOT NULL,
                    status TEXT DEFAULT 'draft',
                    created_at TEXT,
                    updated_at TEXT
                )
            ''')
            
            # User assignments table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS ab_assignments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    experiment_id TEXT,
                    variant_name TEXT,
                    assigned_at TEXT,
                    UNIQUE(user_id, experiment_id)
                )
            ''')
            
            # Events/conversions table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS ab_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    experiment_id TEXT,
                    variant_name TEXT,
                    event_type TEXT,
                    event_data TEXT,
                    timestamp TEXT
                )
            ''')
            
            await db.commit()
        
        self._initialized = True
        logger.info("🧪 A/B Testing tables initialized")
    
    def _hash_user_to_variant(self, user_id: int, experiment_id: str, 
                              num_variants: int) -> int:
        """Consistently assign user to variant based on hash."""
        hash_input = f"{user_id}:{experiment_id}"
        hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
        return hash_value % num_variants
    
    async def get_variant(self, user_id: int, experiment_id: str) -> Optional[str]:
        """
        Get assigned variant for a user in an experiment.
        
        Returns variant name or None if not in experiment.
        """
        await self.init_tables()
        
        # Check if experiment exists and is running
        exp = await self._get_experiment(experiment_id)
        if not exp or exp.status != ExperimentStatus.RUNNING:
            return None
        
        # Check if user is targeted
        if exp.target_users and user_id not in exp.target_users:
            return None
        
        # Check existing assignment
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute(
                "SELECT variant_name FROM ab_assignments WHERE user_id = ? AND experiment_id = ?",
                (user_id, experiment_id)
            ) as c:
                row = await c.fetchone()
                if row:
                    return row[0]
        
        # Create new assignment
        variant_index = self._hash_user_to_variant(
            user_id, experiment_id, len(exp.variants)
        )
        variant_name = exp.variants[variant_index].name
        
        # Save assignment
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute('''
                INSERT INTO ab_assignments (user_id, experiment_id, variant_name, assigned_at)
                VALUES (?, ?, ?, ?)
            ''', (user_id, experiment_id, variant_name, datetime.now().isoformat()))
            await db.commit()
        
        logger.info(f"🧪 User {user_id} assigned to {experiment_id}/{variant_name}")
        return variant_name
    
    async def get_variant_config(self, user_id: int, experiment_id: str) -> Optional[Dict]:
        """Get configuration for user's assigned variant."""
        variant_name = await self.get_variant(user_id, experiment_id)
        if not variant_name:
            return None
        
        exp = await self._get_experiment(experiment_id)
        if not exp:
            return None
        
        for variant in exp.variants:
            if variant.name == variant_name:
                return variant.config
        
        return None
    
    async def _get_experiment(self, experiment_id: str) -> Optional[Experiment]:
        """Load experiment from database."""
        async with aiosqlite.connect(DB_NAME) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM ab_experiments WHERE id = ?",
                (experiment_id,)
            ) as c:
                row = await c.fetchone()
                if not row:
                    return None
                
                config = json.loads(row['config'])
                return Experiment(
                    id=row['id'],
                    name=row['name'],
                    description=row['description'],
                    variants=[Variant(**v) for v in config['variants']],
                    status=ExperimentStatus(row['status']),
                    target_users=config.get('target_users'),
                    start_date=config.get('start_date'),
                    end_date=config.get('end_date')
                )
    
    async def create_experiment(self, experiment: Experiment) -> bool:
        """Create a new A/B test experiment."""
        await self.init_tables()
        
        try:
            config = {
                'variants': [
                    {'name': v.name, 'config': v.config, 'weight': v.weight}
                    for v in experiment.variants
                ],
                'target_users': experiment.target_users,
                'start_date': experiment.start_date,
                'end_date': experiment.end_date
            }
            
            async with aiosqlite.connect(DB_NAME) as db:
                await db.execute('''
                    INSERT OR REPLACE INTO ab_experiments 
                    (id, name, description, config, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    experiment.id,
                    experiment.name,
                    experiment.description,
                    json.dumps(config),
                    experiment.status.value,
                    datetime.now().isoformat(),
                    datetime.now().isoformat()
                ))
                await db.commit()
            
            logger.info(f"🧪 Experiment created: {experiment.id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create experiment: {e}")
            return False
    
    async def track_event(self, user_id: int, experiment_id: str, 
                         event_type: str, event_data: dict = None):
        """Track a conversion/event for A/B test analysis."""
        await self.init_tables()
        
        variant = await self.get_variant(user_id, experiment_id)
        if not variant:
            return
        
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute('''
                INSERT INTO ab_events (user_id, experiment_id, variant_name, 
                                    event_type, event_data, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                user_id, experiment_id, variant, event_type,
                json.dumps(event_data) if event_data else None,
                datetime.now().isoformat()
            ))
            await db.commit()
    
    async def get_experiment_results(self, experiment_id: str) -> Dict:
        """Get statistical results for an experiment."""
        await self.init_tables()
        
        async with aiosqlite.connect(DB_NAME) as db:
            # Get user counts per variant
            async with db.execute('''
                SELECT variant_name, COUNT(*) as users
                FROM ab_assignments
                WHERE experiment_id = ?
                GROUP BY variant_name
            ''', (experiment_id,)) as c:
                assignments = {r[0]: r[1] for r in await c.fetchall()}
            
            # Get event counts per variant
            async with db.execute('''
                SELECT variant_name, event_type, COUNT(*) as count
                FROM ab_events
                WHERE experiment_id = ?
                GROUP BY variant_name, event_type
            ''', (experiment_id,)) as c:
                events = {}
                for row in await c.fetchall():
                    variant, event_type, count = row
                    if variant not in events:
                        events[variant] = {}
                    events[variant][event_type] = count
        
        return {
            'experiment_id': experiment_id,
            'assignments': assignments,
            'events': events,
            'timestamp': datetime.now().isoformat()
        }
    
    async def list_experiments(self) -> List[Experiment]:
        """List all experiments."""
        await self.init_tables()
        
        experiments = []
        async with aiosqlite.connect(DB_NAME) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM ab_experiments ORDER BY created_at DESC"
            ) as c:
                for row in await c.fetchall():
                    config = json.loads(row['config'])
                    experiments.append(Experiment(
                        id=row['id'],
                        name=row['name'],
                        description=row['description'],
                        variants=[Variant(**v) for v in config['variants']],
                        status=ExperimentStatus(row['status'])
                    ))
        
        return experiments


# Predefined experiments for common optimizations
DEFAULT_EXPERIMENTS = {
    "gold_price_test": Experiment(
        id="gold_price_test",
        name="Gold Package Pricing",
        description="Test different gold package prices",
        variants=[
            Variant("control", {"gold_100": 100, "gold_500": 450}, weight=0.5),
            Variant("discount", {"gold_100": 90, "gold_500": 400}, weight=0.5)
        ],
        status=ExperimentStatus.DRAFT
    ),
    "daily_bonus_freq": Experiment(
        id="daily_bonus_freq",
        name="Daily Bonus Frequency",
        description="Test different daily bonus win rates",
        variants=[
            Variant("standard", {"win_rate": 0.25}, weight=0.5),
            Variant("generous", {"win_rate": 0.35}, weight=0.5)
        ],
        status=ExperimentStatus.DRAFT
    )
}


# Global instance
_ab_testing: ABTestingFramework = None


def get_ab_testing() -> ABTestingFramework:
    """Get or create global A/B testing framework."""
    global _ab_testing
    if _ab_testing is None:
        _ab_testing = ABTestingFramework()
    return _ab_testing
