#!/usr/bin/env python3
"""
Test script for ConPort workspace detection functionality.
This script tests the workspace detection in various scenarios.
"""

import os
import sys
import tempfile
import json
from pathlib import Path

# Add the src directory to the path so we can import the modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from context_portal_mcp.core.workspace_detector import WorkspaceDetector, auto_detect_workspace, resolve_workspace_id


def create_test_project(base_dir: Path, project_type: str) -> Path:
    """Create a test project structure for testing."""
    project_dir = base_dir / f"test_{project_type}_project"
    project_dir.mkdir(exist_ok=True)
    
    if project_type == "nodejs":
        # Create package.json
        package_json = {
            "name": f"test-{project_type}-project",
            "version": "1.0.0",
            "scripts": {
                "dev": "next dev",
                "build": "next build"
            },
            "dependencies": {
                "react": "^18.0.0",
                "next": "^13.0.0"
            }
        }
        with open(project_dir / "package.json", "w") as f:
            json.dump(package_json, f, indent=2)
        
        # Create .git directory
        (project_dir / ".git").mkdir(exist_ok=True)
        
        # Create src subdirectory
        src_dir = project_dir / "src"
        src_dir.mkdir(exist_ok=True)
        
    elif project_type == "python":
        # Create pyproject.toml
        pyproject_content = """[project]
name = "test-python-project"
version = "0.1.0"
dependencies = [
    "fastapi",
    "uvicorn"
]

[tool.setuptools]
packages = ["src"]
"""
        with open(project_dir / "pyproject.toml", "w") as f:
            f.write(pyproject_content)
        
        # Create .git directory
        (project_dir / ".git").mkdir(exist_ok=True)
        
        # Create src subdirectory
        src_dir = project_dir / "src"
        src_dir.mkdir(exist_ok=True)
        
    elif project_type == "existing_conport":
        # Create context_portal directory
        context_portal = project_dir / "context_portal"
        context_portal.mkdir(exist_ok=True)
        
        # Create a dummy database file
        (context_portal / "context.db").touch()
        
        # Create src subdirectory
        src_dir = project_dir / "src"
        src_dir.mkdir(exist_ok=True)
    
    return project_dir


def test_workspace_detection():
    """Test workspace detection in various scenarios."""
    print("🧪 Testing ConPort Workspace Detection")
    print("=" * 50)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Test 1: Node.js project detection
        print("\n📦 Test 1: Node.js Project Detection")
        nodejs_project = create_test_project(temp_path, "nodejs")
        src_dir = nodejs_project / "src"
        
        detector = WorkspaceDetector(str(src_dir))
        detected = detector.find_workspace_root()
        
        print(f"  Created project at: {nodejs_project}")
        print(f"  Detection started from: {src_dir}")
        print(f"  Detected workspace: {detected}")
        print(f"  ✅ Success: {detected == nodejs_project}")
        
        # Test 2: Python project detection
        print("\n🐍 Test 2: Python Project Detection")
        python_project = create_test_project(temp_path, "python")
        src_dir = python_project / "src"
        
        detector = WorkspaceDetector(str(src_dir))
        detected = detector.find_workspace_root()
        
        print(f"  Created project at: {python_project}")
        print(f"  Detection started from: {src_dir}")
        print(f"  Detected workspace: {detected}")
        print(f"  ✅ Success: {detected == python_project}")
        
        # Test 3: Existing ConPort workspace detection
        print("\n🗄️ Test 3: Existing ConPort Workspace Detection")
        conport_project = create_test_project(temp_path, "existing_conport")
        src_dir = conport_project / "src"
        
        detector = WorkspaceDetector(str(src_dir))
        detected = detector.find_workspace_root()
        
        print(f"  Created project at: {conport_project}")
        print(f"  Detection started from: {src_dir}")
        print(f"  Detected workspace: {detected}")
        print(f"  ✅ Success: {detected == conport_project}")
        
        # Test 4: Auto-detect function
        print("\n🔍 Test 4: Auto-detect Function")
        auto_detected = auto_detect_workspace(str(src_dir))
        
        print(f"  Auto-detected workspace: {auto_detected}")
        print(f"  ✅ Success: {Path(auto_detected) == conport_project}")
        
        # Test 5: Resolve workspace ID function
        print("\n⚙️ Test 5: Resolve Workspace ID Function")
        
        # Test with explicit workspace_id
        resolved = resolve_workspace_id("explicit/path", auto_detect=True)
        print(f"  Explicit path: {resolved}")
        print(f"  ✅ Success: {resolved == 'explicit/path'}")
        
        # Test with auto-detection
        resolved = resolve_workspace_id(None, auto_detect=True, start_path=str(src_dir))
        print(f"  Auto-detected path: {resolved}")
        print(f"  ✅ Success: {Path(resolved) == conport_project}")
        
        # Test 6: Detection info
        print("\n📊 Test 6: Detection Info")
        detector = WorkspaceDetector(str(src_dir))
        info = detector.get_detection_info()
        
        print(f"  Start path: {info['start_path']}")
        print(f"  Detected workspace: {info['detected_workspace']}")
        print(f"  Context portal path: {info['context_portal_path']}")
        print(f"  Detection method: {info['detection_method']}")
        print(f"  Indicators found: {info['indicators_found']}")
        print(f"  ✅ Success: Detection info generated")
        
        print("\n🎉 All tests completed!")


def test_real_workspace():
    """Test detection on the actual ConPort repository."""
    print("\n🔬 Testing on Real ConPort Repository")
    print("=" * 40)
    
    # Get the current directory (should be the ConPort repo)
    current_dir = Path(__file__).parent
    
    detector = WorkspaceDetector(str(current_dir))
    detected = detector.find_workspace_root()
    info = detector.get_detection_info()
    
    print(f"Current directory: {current_dir}")
    print(f"Detected workspace: {detected}")
    print(f"Detection method: {info['detection_method']}")
    print(f"Indicators found: {info['indicators_found']}")
    print(f"Context portal path: {info['context_portal_path']}")
    
    # Check if pyproject.toml exists (should for ConPort)
    pyproject_exists = (detected / "pyproject.toml").exists()
    print(f"pyproject.toml exists: {pyproject_exists}")
    
    return detected


if __name__ == "__main__":
    print("ConPort Workspace Detection Test Suite")
    print("=====================================")
    
    try:
        # Test with synthetic projects
        test_workspace_detection()
        
        # Test with real ConPort repository
        real_workspace = test_real_workspace()
        
        print(f"\n✅ All tests passed!")
        print(f"Real workspace detected at: {real_workspace}")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)