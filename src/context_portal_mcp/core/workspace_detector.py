"""
Universal Workspace Detection for ConPort MCP Server

This module provides intelligent workspace detection that works across different
project types and directory structures, eliminating the need for hardcoded
workspace_id parameters.
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

log = logging.getLogger(__name__)


class WorkspaceDetector:
    """Intelligent workspace detection for ConPort MCP server"""
    
    # Indicators that suggest a directory is a workspace root
    WORKSPACE_INDICATORS = [
        'package.json',
        '.git',
        'pyproject.toml',
        'Cargo.toml',
        'go.mod',
        'pom.xml',
        'composer.json',
        'Gemfile',
        'requirements.txt',
        'setup.py',
        'CMakeLists.txt',
        'Makefile',
        '.gitignore',
        'README.md',
        'README.rst',
        'LICENSE'
    ]
    
    # Strong indicators that are more reliable for workspace detection
    STRONG_INDICATORS = [
        'package.json',
        '.git',
        'pyproject.toml',
        'Cargo.toml',
        'go.mod',
        'pom.xml'
    ]
    
    # Project-specific files that indicate a development workspace
    PROJECT_FILES = [
        'package.json',
        'pyproject.toml',
        'Cargo.toml',
        'go.mod',
        'pom.xml',
        'composer.json',
        'Gemfile'
    ]
    
    def __init__(self, start_path: Optional[str] = None, max_depth: int = 10):
        """
        Initialize the workspace detector.
        
        Args:
            start_path: Starting directory for detection (default: current working directory)
            max_depth: Maximum depth to search up the directory tree
        """
        self.start_path = Path(start_path or os.getcwd()).resolve()
        self.max_depth = max_depth
        log.debug(f"WorkspaceDetector initialized with start_path: {self.start_path}")
    
    def find_workspace_root(self) -> Path:
        """
        Find the workspace root using multiple detection strategies.
        
        Returns:
            Path to the detected workspace root
        """
        log.debug(f"Starting workspace detection from: {self.start_path}")
        
        # Strategy 1: Look for strong indicators with validation
        workspace = self._detect_by_strong_indicators()
        if workspace:
            log.info(f"Workspace detected by strong indicators: {workspace}")
            return workspace
        
        # Strategy 2: Look for any workspace indicators
        workspace = self._detect_by_any_indicators()
        if workspace:
            log.info(f"Workspace detected by general indicators: {workspace}")
            return workspace
        
        # Strategy 3: Look for context_portal directory (existing ConPort workspace)
        workspace = self._detect_by_context_portal()
        if workspace:
            log.info(f"Workspace detected by existing context_portal: {workspace}")
            return workspace
        
        # Fallback: Use start path
        log.warning(f"No workspace indicators found, using start path: {self.start_path}")
        return self.start_path
    
    def _detect_by_strong_indicators(self) -> Optional[Path]:
        """Detect workspace using strong indicators with validation."""
        current = self.start_path
        depth = 0
        
        while current != current.parent and depth < self.max_depth:
            log.debug(f"Checking for strong indicators at: {current} (depth: {depth})")
            
            # Check for strong indicators
            strong_found = []
            for indicator in self.STRONG_INDICATORS:
                indicator_path = current / indicator
                if indicator_path.exists():
                    strong_found.append(indicator)
                    log.debug(f"Found strong indicator: {indicator} at {current}")
            
            if strong_found:
                # Validate the workspace
                if self._validate_workspace(current, strong_found):
                    return current
            
            current = current.parent
            depth += 1
        
        return None
    
    def _detect_by_any_indicators(self) -> Optional[Path]:
        """Detect workspace using any workspace indicators."""
        current = self.start_path
        depth = 0
        
        while current != current.parent and depth < self.max_depth:
            log.debug(f"Checking for any indicators at: {current} (depth: {depth})")
            
            # Count indicators found
            indicators_found = []
            for indicator in self.WORKSPACE_INDICATORS:
                indicator_path = current / indicator
                if indicator_path.exists():
                    indicators_found.append(indicator)
            
            # If we find multiple indicators, it's likely a workspace
            if len(indicators_found) >= 2:
                log.debug(f"Found {len(indicators_found)} indicators at {current}: {indicators_found}")
                return current
            
            current = current.parent
            depth += 1
        
        return None
    
    def _detect_by_context_portal(self) -> Optional[Path]:
        """Detect workspace by looking for existing context_portal directory."""
        current = self.start_path
        depth = 0
        
        while current != current.parent and depth < self.max_depth:
            context_portal = current / 'context_portal'
            if context_portal.exists() and context_portal.is_dir():
                log.debug(f"Found existing context_portal at: {current}")
                return current
            
            current = current.parent
            depth += 1
        
        return None
    
    def _validate_workspace(self, path: Path, indicators: List[str]) -> bool:
        """
        Validate that the detected path is actually a workspace root.
        
        Args:
            path: Path to validate
            indicators: List of indicators found at this path
            
        Returns:
            True if the path is a valid workspace root
        """
        log.debug(f"Validating workspace at {path} with indicators: {indicators}")
        
        # Check package.json for project-specific content
        if 'package.json' in indicators:
            if self._validate_package_json(path / 'package.json'):
                return True
        
        # Check pyproject.toml for Python projects
        if 'pyproject.toml' in indicators:
            if self._validate_pyproject_toml(path / 'pyproject.toml'):
                return True
        
        # Check for other project files
        for project_file in self.PROJECT_FILES:
            if project_file in indicators:
                log.debug(f"Found project file {project_file}, considering valid workspace")
                return True
        
        # If .git exists, it's likely a workspace root
        if '.git' in indicators:
            log.debug("Found .git directory, considering valid workspace")
            return True
        
        return False
    
    def _validate_package_json(self, package_json_path: Path) -> bool:
        """Validate package.json contains project-specific content."""
        try:
            with open(package_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Look for project-specific indicators
            has_name = bool(data.get('name'))
            has_scripts = bool(data.get('scripts', {}).get('dev') or 
                             data.get('scripts', {}).get('start') or
                             data.get('scripts', {}).get('build'))
            has_dependencies = bool(data.get('dependencies') or data.get('devDependencies'))
            is_module = data.get('type') == 'module'
            
            is_valid = has_name and (has_scripts or has_dependencies or is_module)
            log.debug(f"package.json validation: name={has_name}, scripts={has_scripts}, "
                     f"deps={has_dependencies}, module={is_module}, valid={is_valid}")
            return is_valid
            
        except (json.JSONDecodeError, IOError, KeyError) as e:
            log.debug(f"Failed to validate package.json: {e}")
            return False
    
    def _validate_pyproject_toml(self, pyproject_path: Path) -> bool:
        """Validate pyproject.toml contains project-specific content."""
        try:
            # Basic validation - if it exists and is readable, it's likely a project
            with open(pyproject_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Look for common project sections
            has_project = '[project]' in content or '[tool.' in content
            log.debug(f"pyproject.toml validation: has_project_sections={has_project}")
            return has_project
            
        except (IOError, UnicodeDecodeError) as e:
            log.debug(f"Failed to validate pyproject.toml: {e}")
            return False
    
    def get_context_portal_path(self, workspace_root: Path) -> Path:
        """Get the context_portal path for the workspace."""
        return workspace_root / 'context_portal'
    
    def detect_from_mcp_context(self) -> Optional[str]:
        """
        Detect workspace from MCP client environment variables.
        
        Returns:
            Workspace path if detected from MCP context, None otherwise
        """
        # Check for VSCode workspace folder
        vscode_workspace = os.environ.get('VSCODE_WORKSPACE_FOLDER')
        if vscode_workspace and os.path.isdir(vscode_workspace):
            log.debug(f"Detected workspace from VSCODE_WORKSPACE_FOLDER: {vscode_workspace}")
            return vscode_workspace
        
        # Check for other MCP client context indicators
        conport_workspace = os.environ.get('CONPORT_WORKSPACE')
        if conport_workspace and os.path.isdir(conport_workspace):
            log.debug(f"Detected workspace from CONPORT_WORKSPACE: {conport_workspace}")
            return conport_workspace
        
        # Check current working directory if it looks like a workspace
        cwd = os.getcwd()
        detector = WorkspaceDetector(cwd)
        detected = detector.find_workspace_root()
        if detected != Path(cwd):  # Only return if we detected something different
            log.debug(f"Detected workspace from CWD analysis: {detected}")
            return str(detected)
        
        return None
    
    def get_detection_info(self) -> Dict[str, Any]:
        """
        Get detailed information about the workspace detection process.
        
        Returns:
            Dictionary with detection details for debugging
        """
        workspace_root = self.find_workspace_root()
        
        info = {
            'start_path': str(self.start_path),
            'detected_workspace': str(workspace_root),
            'context_portal_path': str(self.get_context_portal_path(workspace_root)),
            'detection_method': 'fallback',
            'indicators_found': [],
            'environment_variables': {
                'VSCODE_WORKSPACE_FOLDER': os.environ.get('VSCODE_WORKSPACE_FOLDER'),
                'CONPORT_WORKSPACE': os.environ.get('CONPORT_WORKSPACE'),
                'PWD': os.environ.get('PWD'),
                'CWD': os.getcwd()
            }
        }
        
        # Check what indicators exist at the detected workspace
        for indicator in self.WORKSPACE_INDICATORS:
            indicator_path = workspace_root / indicator
            if indicator_path.exists():
                info['indicators_found'].append(indicator)
        
        # Determine detection method
        if any(ind in info['indicators_found'] for ind in self.STRONG_INDICATORS):
            info['detection_method'] = 'strong_indicators'
        elif len(info['indicators_found']) >= 2:
            info['detection_method'] = 'multiple_indicators'
        elif (workspace_root / 'context_portal').exists():
            info['detection_method'] = 'existing_context_portal'
        
        return info


def auto_detect_workspace(start_path: Optional[str] = None) -> str:
    """
    Convenience function for automatic workspace detection.
    
    Args:
        start_path: Starting directory for detection
        
    Returns:
        Detected workspace path as string
    """
    detector = WorkspaceDetector(start_path)
    
    # First try MCP context detection
    mcp_workspace = detector.detect_from_mcp_context()
    if mcp_workspace:
        return mcp_workspace
    
    # Fall back to directory-based detection
    workspace_root = detector.find_workspace_root()
    return str(workspace_root)


def resolve_workspace_id(provided_workspace_id: Optional[str] = None, 
                        auto_detect: bool = True,
                        start_path: Optional[str] = None) -> str:
    """
    Resolve workspace ID using provided value or auto-detection.
    
    Args:
        provided_workspace_id: Explicitly provided workspace ID
        auto_detect: Whether to use auto-detection if no workspace_id provided
        start_path: Starting directory for auto-detection
        
    Returns:
        Resolved workspace ID
    """
    # If explicitly provided, use it (but handle special cases)
    if provided_workspace_id:
        # Handle VSCode variable that wasn't expanded
        if provided_workspace_id == "${workspaceFolder}":
            log.warning("workspace_id was literal '${workspaceFolder}', falling back to auto-detection")
        else:
            log.debug(f"Using provided workspace_id: {provided_workspace_id}")
            return provided_workspace_id
    
    # Auto-detect if enabled
    if auto_detect:
        detected = auto_detect_workspace(start_path)
        log.info(f"Auto-detected workspace: {detected}")
        return detected
    
    # Final fallback to current directory
    fallback = os.getcwd()
    log.warning(f"No workspace detection method available, using current directory: {fallback}")
    return fallback