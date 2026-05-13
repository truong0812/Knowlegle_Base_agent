from __future__ import annotations

import shutil
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_python_source() -> bytes:
    return (FIXTURES_DIR / "sample_python.py").read_bytes()


@pytest.fixture
def sample_csharp_source() -> bytes:
    return (FIXTURES_DIR / "sample_csharp.cs").read_bytes()


@pytest.fixture
def sample_cpp_source() -> bytes:
    return (FIXTURES_DIR / "sample_cpp.cpp").read_bytes()


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    """Create a temp directory structured as a multi-language repo."""
    # Python files
    py_dir = tmp_path / "src" / "services"
    py_dir.mkdir(parents=True)
    shutil.copy(FIXTURES_DIR / "sample_python.py", py_dir / "user_service.py")

    # C# files
    cs_dir = tmp_path / "src" / "MyApp.Services"
    cs_dir.mkdir(parents=True)
    shutil.copy(FIXTURES_DIR / "sample_csharp.cs", cs_dir / "UserService.cs")

    # C++ files
    cpp_dir = tmp_path / "src" / "core"
    cpp_dir.mkdir(parents=True)
    shutil.copy(FIXTURES_DIR / "sample_cpp.cpp", cpp_dir / "user_service.cpp")

    return tmp_path
