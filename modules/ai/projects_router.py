# modules/ai/projects_router.py
"""
Projects API Router for Syntax Prime V2
Handles Claude-style project folders functionality
Date: 2/4/26
"""

import uuid
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Router Setup
router = APIRouter(prefix="/ai/projects", tags=["projects"])
DEFAULT_USER_ID = "b7c60682-4815-4d9d-8ebe-66c6cd24eff9"

# Dependency function
async def get_current_user_id() -> str:
    """Get current user ID - placeholder for now"""
    return DEFAULT_USER_ID


# ============================================================================
# Request/Response Models
# ============================================================================

class ProjectCreate(BaseModel):
    """Create a new project"""
    name: str = Field(..., min_length=1, max_length=100, description="Project name (unique identifier)")
    display_name: str = Field(..., min_length=1, max_length=200, description="Display name for UI")
    description: Optional[str] = Field(None, max_length=1000, description="Project description")
    instructions: Optional[str] = Field(None, max_length=10000, description="Custom AI instructions for this project")
    category: Optional[str] = Field(None, max_length=100, description="Project category")
    color: Optional[str] = Field(None, max_length=7, description="Hex color for UI (e.g., #3B82F6)")
    icon: Optional[str] = Field(None, max_length=10, description="Emoji icon for project")


class ProjectUpdate(BaseModel):
    """Update an existing project"""
    display_name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    instructions: Optional[str] = Field(None, max_length=10000)
    category: Optional[str] = Field(None, max_length=100)
    color: Optional[str] = Field(None, max_length=7)
    icon: Optional[str] = Field(None, max_length=10)
    is_active: Optional[bool] = None


class ProjectResponse(BaseModel):
    """Project response model"""
    id: int
    name: str
    display_name: str
    description: Optional[str]
    instructions: Optional[str]
    category: Optional[str]
    color: Optional[str]
    icon: Optional[str]
    is_active: bool
    thread_count: int = 0
    created_at: Optional[str]
    updated_at: Optional[str]


class ProjectListResponse(BaseModel):
    """List of projects response"""
    projects: List[ProjectResponse]
    total: int


class ThreadAssignment(BaseModel):
    """Assign thread to project"""
    project_id: Optional[int] = Field(None, description="Project ID to assign (null to unassign)")


class ThreadInProject(BaseModel):
    """Thread info within a project"""
    id: str
    title: Optional[str]
    message_count: int
    created_at: Optional[str]
    updated_at: Optional[str]
    last_message_at: Optional[str]


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("", response_model=ProjectListResponse)
async def list_projects(
    include_inactive: bool = False,
    user_id: str = Depends(get_current_user_id)
):
    """
    Get all projects for the user.
    Returns projects with thread counts.
    """
    try:
        from ..core.database import db_manager
        
        # Build query based on whether to include inactive
        active_filter = "" if include_inactive else "WHERE p.is_active = true"
        
        query = f"""
            SELECT 
                p.id,
                p.name,
                p.display_name,
                p.description,
                p.instructions,
                p.category,
                p.color,
                p.icon,
                p.is_active,
                p.created_at,
                p.updated_at,
                COUNT(ct.id) as thread_count
            FROM knowledge_projects p
            LEFT JOIN conversation_threads ct ON ct.primary_project_id = p.id
            {active_filter}
            GROUP BY p.id
            ORDER BY p.display_name ASC
        """
        
        results = await db_manager.fetch_all(query)
        
        projects = [
            ProjectResponse(
                id=row['id'],
                name=row['name'],
                display_name=row['display_name'],
                description=row['description'],
                instructions=row['instructions'],
                category=row['category'],
                color=row.get('color'),
                icon=row.get('icon'),
                is_active=row['is_active'],
                thread_count=row['thread_count'] or 0,
                created_at=row['created_at'].isoformat() if row['created_at'] else None,
                updated_at=(row['updated_at'].isoformat() + '+00:00') if row['updated_at'] else None
            )
            for row in results
        ]
        
        logger.info(f"📂 Listed {len(projects)} projects")
        
        return ProjectListResponse(projects=projects, total=len(projects))
        
    except Exception as e:
        logger.error(f"❌ Failed to list projects: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: int,
    user_id: str = Depends(get_current_user_id)
):
    """
    Get a specific project by ID.
    """
    try:
        from ..core.database import db_manager
        
        query = """
            SELECT 
                p.id,
                p.name,
                p.display_name,
                p.description,
                p.instructions,
                p.category,
                p.color,
                p.icon,
                p.is_active,
                p.created_at,
                p.updated_at,
                COUNT(ct.id) as thread_count
            FROM knowledge_projects p
            LEFT JOIN conversation_threads ct ON ct.primary_project_id = p.id
            WHERE p.id = $1
            GROUP BY p.id
        """
        
        result = await db_manager.fetch_one(query, project_id)
        
        if not result:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        
        return ProjectResponse(
            id=result['id'],
            name=result['name'],
            display_name=result['display_name'],
            description=result['description'],
            instructions=result['instructions'],
            category=result['category'],
            color=result.get('color'),
            icon=result.get('icon'),
            is_active=result['is_active'],
            thread_count=result['thread_count'] or 0,
            created_at=result['created_at'].isoformat() if result['created_at'] else None,
            updated_at=result['updated_at'].isoformat() if result['updated_at'] else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get project {project_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=ProjectResponse)
async def create_project(
    project: ProjectCreate,
    user_id: str = Depends(get_current_user_id)
):
    """
    Create a new project.
    """
    try:
        from ..core.database import db_manager
        
        # Check if name already exists
        existing = await db_manager.fetch_one(
            "SELECT id FROM knowledge_projects WHERE name = $1",
            project.name
        )
        
        if existing:
            raise HTTPException(status_code=400, detail=f"Project with name '{project.name}' already exists")
        
        # Insert new project
        query = """
            INSERT INTO knowledge_projects 
            (name, display_name, description, instructions, category, color, icon, is_active, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, true, NOW(), NOW())
            RETURNING id, name, display_name, description, instructions, category, color, icon, is_active, created_at, updated_at
        """
        
        result = await db_manager.fetch_one(
            query,
            project.name,
            project.display_name,
            project.description,
            project.instructions,
            project.category,
            project.color or '#6366F1',  # Default indigo
            project.icon or '📁'
        )
        
        logger.info(f"📂 Created project: {project.display_name} (id={result['id']})")
        
        return ProjectResponse(
            id=result['id'],
            name=result['name'],
            display_name=result['display_name'],
            description=result['description'],
            instructions=result['instructions'],
            category=result['category'],
            color=result.get('color'),
            icon=result.get('icon'),
            is_active=result['is_active'],
            thread_count=0,
            created_at=result['created_at'].isoformat() if result['created_at'] else None,
            updated_at=result['updated_at'].isoformat() if result['updated_at'] else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to create project: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: int,
    project: ProjectUpdate,
    user_id: str = Depends(get_current_user_id)
):
    """
    Update an existing project.
    Only provided fields will be updated.
    """
    try:
        from ..core.database import db_manager
        
        # Check project exists
        existing = await db_manager.fetch_one(
            "SELECT id FROM knowledge_projects WHERE id = $1",
            project_id
        )
        
        if not existing:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        
        # Build dynamic update query
        updates = []
        values = []
        param_num = 1
        
        if project.display_name is not None:
            updates.append(f"display_name = ${param_num}")
            values.append(project.display_name)
            param_num += 1
            
        if project.description is not None:
            updates.append(f"description = ${param_num}")
            values.append(project.description)
            param_num += 1
            
        if project.instructions is not None:
            updates.append(f"instructions = ${param_num}")
            values.append(project.instructions)
            param_num += 1
            
        if project.category is not None:
            updates.append(f"category = ${param_num}")
            values.append(project.category)
            param_num += 1
            
        if project.color is not None:
            updates.append(f"color = ${param_num}")
            values.append(project.color)
            param_num += 1
            
        if project.icon is not None:
            updates.append(f"icon = ${param_num}")
            values.append(project.icon)
            param_num += 1
            
        if project.is_active is not None:
            updates.append(f"is_active = ${param_num}")
            values.append(project.is_active)
            param_num += 1
        
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        # Always update updated_at
        updates.append("updated_at = NOW()")
        
        # Add project_id as final parameter
        values.append(project_id)
        
        query = f"""
            UPDATE knowledge_projects 
            SET {', '.join(updates)}
            WHERE id = ${param_num}
            RETURNING id, name, display_name, description, instructions, category, color, icon, is_active, created_at, updated_at
        """
        
        result = await db_manager.fetch_one(query, *values)
        
        # Get thread count
        count_result = await db_manager.fetch_one(
            "SELECT COUNT(*) as count FROM conversation_threads WHERE primary_project_id = $1",
            project_id
        )
        
        logger.info(f"📂 Updated project {project_id}")
        
        # Clear project cache in personality engine
        try:
            from .personality_engine import get_personality_engine
            personality_engine = get_personality_engine()
            personality_engine.clear_project_cache()
            logger.info(f"🔄 Cleared project cache after update")
        except Exception as cache_error:
            logger.warning(f"⚠️ Could not clear project cache: {cache_error}")
        
        return ProjectResponse(
            id=result['id'],
            name=result['name'],
            display_name=result['display_name'],
            description=result['description'],
            instructions=result['instructions'],
            category=result['category'],
            color=result.get('color'),
            icon=result.get('icon'),
            is_active=result['is_active'],
            thread_count=count_result['count'] if count_result else 0,
            created_at=result['created_at'].isoformat() if result['created_at'] else None,
            updated_at=result['updated_at'].isoformat() if result['updated_at'] else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to update project {project_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{project_id}")
async def delete_project(
    project_id: int,
    hard_delete: bool = False,
    user_id: str = Depends(get_current_user_id)
):
    """
    Delete a project.
    By default, soft-deletes (sets is_active=false).
    Use hard_delete=true to permanently remove.
    
    Note: Threads are NOT deleted, just unassigned from the project.
    """
    try:
        from ..core.database import db_manager
        
        # Check project exists
        existing = await db_manager.fetch_one(
            "SELECT id, display_name FROM knowledge_projects WHERE id = $1",
            project_id
        )
        
        if not existing:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        
        # Unassign all threads from this project
        await db_manager.execute(
            "UPDATE conversation_threads SET primary_project_id = NULL WHERE primary_project_id = $1",
            project_id
        )
        
        if hard_delete:
            # Permanently delete
            await db_manager.execute(
                "DELETE FROM knowledge_projects WHERE id = $1",
                project_id
            )
            logger.info(f"🗑️ Hard deleted project {project_id}: {existing['display_name']}")
            message = f"Project '{existing['display_name']}' permanently deleted"
        else:
            # Soft delete
            await db_manager.execute(
                "UPDATE knowledge_projects SET is_active = false, updated_at = NOW() WHERE id = $1",
                project_id
            )
            logger.info(f"📂 Soft deleted project {project_id}: {existing['display_name']}")
            message = f"Project '{existing['display_name']}' archived"
        
        return {"success": True, "message": message}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to delete project {project_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Thread-Project Assignment Endpoints
# ============================================================================

@router.get("/{project_id}/threads", response_model=List[ThreadInProject])
async def get_project_threads(
    project_id: int,
    limit: int = 50,
    user_id: str = Depends(get_current_user_id)
):
    """
    Get all threads in a project.
    """
    try:
        from ..core.database import db_manager
        
        # Verify project exists
        project = await db_manager.fetch_one(
            "SELECT id FROM knowledge_projects WHERE id = $1",
            project_id
        )
        
        if not project:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        
        query = """
            SELECT 
                id, title, message_count, created_at, updated_at, last_message_at
            FROM conversation_threads
            WHERE primary_project_id = $1 AND user_id = $2
            ORDER BY last_message_at DESC NULLS LAST
            LIMIT $3
        """
        
        results = await db_manager.fetch_all(query, project_id, user_id, limit)
        
        return [
            ThreadInProject(
                id=str(row['id']),
                title=row['title'],
                message_count=row['message_count'] or 0,
                created_at=row['created_at'].isoformat() if row['created_at'] else None,
                updated_at=row['updated_at'].isoformat() if row['updated_at'] else None,
                last_message_at=row['last_message_at'].isoformat() if row['last_message_at'] else None
            )
            for row in results
        ]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get threads for project {project_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/threads/{thread_id}/assign")
async def assign_thread_to_project(
    thread_id: str,
    assignment: ThreadAssignment,
    user_id: str = Depends(get_current_user_id)
):
    """
    Assign or unassign a thread to/from a project.
    Set project_id to null to unassign.
    """
    try:
        from ..core.database import db_manager
        
        # Verify thread exists and belongs to user
        thread = await db_manager.fetch_one(
            "SELECT id, title FROM conversation_threads WHERE id = $1 AND user_id = $2",
            thread_id, user_id
        )
        
        if not thread:
            raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")
        
        # If assigning to a project, verify project exists
        if assignment.project_id is not None:
            project = await db_manager.fetch_one(
                "SELECT id, display_name FROM knowledge_projects WHERE id = $1 AND is_active = true",
                assignment.project_id
            )
            
            if not project:
                raise HTTPException(status_code=404, detail=f"Project {assignment.project_id} not found")
            
            project_name = project['display_name']
        else:
            project_name = None
        
        # Update thread
        await db_manager.execute(
            "UPDATE conversation_threads SET primary_project_id = $1, updated_at = NOW() WHERE id = $2",
            assignment.project_id, thread_id
        )
        
        if assignment.project_id:
            logger.info(f"📂 Assigned thread {thread_id} to project {assignment.project_id}")
            message = f"Thread assigned to '{project_name}'"
        else:
            logger.info(f"📂 Unassigned thread {thread_id} from project")
            message = "Thread removed from project"
        
        return {
            "success": True,
            "message": message,
            "thread_id": thread_id,
            "project_id": assignment.project_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to assign thread {thread_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{project_id}/threads")
async def create_thread_in_project(
    project_id: int,
    user_id: str = Depends(get_current_user_id)
):
    """
    Create a new conversation thread in a specific project.
    Returns the new thread ID for immediate use.
    """
    try:
        from ..core.database import db_manager
        
        # Verify project exists
        project = await db_manager.fetch_one(
            "SELECT id, display_name FROM knowledge_projects WHERE id = $1 AND is_active = true",
            project_id
        )
        
        if not project:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        
        # Create new thread with project assignment
        thread_id = str(uuid.uuid4())
        
        query = """
            INSERT INTO conversation_threads 
            (id, user_id, platform, status, primary_project_id, created_at, updated_at)
            VALUES ($1, $2, 'web', 'active', $3, NOW(), NOW())
            RETURNING id
        """
        
        result = await db_manager.fetch_one(query, thread_id, user_id, project_id)
        
        logger.info(f"📂 Created new thread {thread_id} in project {project_id}: {project['display_name']}")
        
        return {
            "success": True,
            "thread_id": str(result['id']),
            "project_id": project_id,
            "project_name": project['display_name'],
            "message": f"New conversation started in '{project['display_name']}'"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to create thread in project {project_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Module Info
# ============================================================================

def get_projects_info():
    """Get information about the projects router"""
    return {
        "name": "Projects Router",
        "version": "1.0.0",
        "description": "Claude-style project folders functionality",
        "endpoints": {
            "list_projects": "GET /ai/projects",
            "get_project": "GET /ai/projects/{id}",
            "create_project": "POST /ai/projects",
            "update_project": "PUT /ai/projects/{id}",
            "delete_project": "DELETE /ai/projects/{id}",
            "get_project_threads": "GET /ai/projects/{id}/threads",
            "create_thread_in_project": "POST /ai/projects/{id}/threads",
            "assign_thread": "PUT /ai/projects/threads/{thread_id}/assign"
        }
    }
