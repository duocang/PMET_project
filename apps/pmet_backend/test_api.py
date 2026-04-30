#!/usr/bin/env python3
"""
Test script to verify PMET API functionality locally.
Run with: python test_api.py
"""

import sys
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_imports():
    """Test that all modules can be imported"""
    print("1. Testing imports...")
    try:
        from pmet_backend.config import config
        print(f"   - config loaded, NCPU={config.NCPU}")

        from pmet_backend.api.models.task import TaskCreate, TaskMode
        print("   - TaskCreate model OK")

        from pmet_backend.services.storage import StorageService
        print("   - StorageService OK")

        from pmet_backend.services.executor import PMETExecutor
        print("   - PMETExecutor OK")

        from pmet_backend.services.mail import MailService
        print("   - MailService OK")

        from pmet_backend.worker.celery_app import celery_app
        print(f"   - Celery app OK, broker={celery_app.conf.broker_url}")

        print("   ✓ All imports successful\n")
        return True
    except Exception as e:
        print(f"   ✗ Import error: {e}\n")
        return False


def test_task_model():
    """Test TaskCreate model validation"""
    print("2. Testing TaskCreate model...")
    from pmet_backend.api.models.task import TaskCreate, TaskMode

    try:
        task = TaskCreate(
            email="test@example.com",
            mode=TaskMode.PROMOTERS_PRE,
            genes_file="results/app/test/0.txt",
            ic_threshold=24,
            max_match=5,
            promoter_num=5000,
            fimo_threshold=0.05,
            premade_index="data/precomputed_indexes/Arabidopsis_thaliana/Jaspar_plants_non_redundant_2022"
        )
        print(f"   - Created task for {task.email}")
        print(f"   - Mode: {task.mode}")
        print(f"   - IC threshold: {task.ic_threshold}")
        print("   ✓ Model validation OK\n")
        return True
    except Exception as e:
        print(f"   ✗ Model error: {e}\n")
        return False


def test_storage_service():
    """Test StorageService"""
    print("3. Testing StorageService...")
    from pmet_backend.services.storage import StorageService

    try:
        storage = StorageService()
        task_id = storage.generate_task_id("test@example.com")
        print(f"   - Generated task_id: {task_id}")

        task_dir = storage.create_task_directory(task_id)
        print(f"   - Created directory: {task_dir}")

        # Cleanup
        import shutil
        if task_dir.exists():
            shutil.rmtree(task_dir)

        print("   ✓ StorageService OK\n")
        return True
    except Exception as e:
        print(f"   ✗ Storage error: {e}\n")
        return False


def test_executor_command_building():
    """Test PMETExecutor command building (without execution)"""
    print("4. Testing PMETExecutor command building...")
    from pmet_backend.services.executor import PMETExecutor

    try:
        executor = PMETExecutor()

        # Test promoters_pre mode
        meta = {
            "task_id": "test-example.com_2024Jan01_1200",
            "mode": "promoters_pre",
            "email": "test@example.com",
            "ic_threshold": 24,
            "max_match": 5,
            "promoter_num": 5000,
            "fimo_threshold": 0.05,
            "genes_file": "results/app/test/0.txt",
            "premade_index": "data/precomputed_indexes/Arabidopsis_thaliana/Jaspar_plants",
            "result_link": "http://example.com/results/test.zip"
        }

        script_path = Path("pipeline/workflows/pair_only.sh")
        if script_path.exists():
            cmd = executor._build_promoters_pre_cmd(meta, script_path)
            print(f"   - promoters_pre command args: {len(cmd)}")
            print(f"   - Script: {cmd[0]}")
            print(f"   - Genes file arg: -g {cmd[6]}")
        else:
            print("   - Skipping command test (script not found)")

        print("   ✓ PMETExecutor OK\n")
        return True
    except Exception as e:
        print(f"   ✗ Executor error: {e}\n")
        return False


def test_fastapi_app():
    """Test FastAPI app creation"""
    print("5. Testing FastAPI app...")
    try:
        from pmet_backend.api.main import app
        print(f"   - App title: {app.title}")
        print(f"   - Routes: {[r.path for r in app.routes if hasattr(r, 'path')]}")
        print("   ✓ FastAPI app OK\n")
        return True
    except Exception as e:
        print(f"   ✗ FastAPI error: {e}\n")
        return False


def main():
    print("="*60)
    print("PMET Backend Verification")
    print("="*60 + "\n")

    results = []
    results.append(test_imports())
    results.append(test_task_model())
    results.append(test_storage_service())
    results.append(test_executor_command_building())
    results.append(test_fastapi_app())

    print("="*60)
    if all(results):
        print("All tests passed ✓")
        print("\nTo start the API:")
        print("  cd pmet_backend && uvicorn api.main:app --reload")
        print("\nTo start a Celery worker:")
        print("  cd pmet_backend && celery -A worker.celery_app worker --loglevel=info")
    else:
        print("Some tests failed ✗")
        sys.exit(1)
    print("="*60)


if __name__ == "__main__":
    main()
