#!/usr/bin/env python
"""Comprehensive system test for FireForm"""

import sys
import os

def test_imports():
    """Test all critical imports"""
    print("=== Testing Imports ===")
    try:
        from src.llm import LLM
        from src.filler import Filler
        from src.controller import Controller
        from src.file_manipulator import FileManipulator
        from api.main import app
        from api.schemas.forms import FormFill
        from api.schemas.templates import TemplateCreate
        print("✓ All imports successful")
        return True
    except Exception as e:
        print(f"✗ Import failed: {e}")
        return False

def test_llm():
    """Test LLM functionality"""
    print("\n=== Testing LLM ===")
    try:
        from src.llm import LLM
        
        # Test initialization
        llm = LLM(
            transcript_text="Employee John Doe works as Manager",
            target_fields={"name": "Employee name", "title": "Job title"}
        )
        print("✓ LLM initialization successful")
        
        # Test data retrieval
        data = llm.get_data()
        print(f"✓ LLM data retrieval successful: {type(data)}")
        
        return True
    except Exception as e:
        print(f"✗ LLM test failed: {e}")
        return False

def test_filler():
    """Test Filler functionality"""
    print("\n=== Testing Filler ===")
    try:
        from src.filler import Filler
        
        filler = Filler()
        print("✓ Filler initialization successful")
        
        # Test sanitization
        test_values = [
            "Normal text",
            "Text with <script>alert(1)</script>",
            "Text with special chars: ()[]{}",
            None,
            123
        ]
        
        for value in test_values:
            sanitized = filler.sanitize_pdf_value(value)
            print(f"✓ Sanitized: {repr(value)[:30]} -> {repr(sanitized)[:30]}")
        
        return True
    except Exception as e:
        print(f"✗ Filler test failed: {e}")
        return False

def test_controller():
    """Test Controller functionality"""
    print("\n=== Testing Controller ===")
    try:
        from src.controller import Controller
        
        controller = Controller()
        print("✓ Controller initialization successful")
        
        # Check attributes
        assert hasattr(controller, 'file_manipulator'), "Missing file_manipulator"
        print("✓ Controller has required attributes")
        
        return True
    except Exception as e:
        print(f"✗ Controller test failed: {e}")
        return False

def test_schemas():
    """Test Pydantic schemas"""
    print("\n=== Testing Schemas ===")
    try:
        from api.schemas.forms import FormFill
        from api.schemas.templates import TemplateCreate
        
        # Test FormFill
        form = FormFill(template_id=1, input_text="Test input text")
        print(f"✓ FormFill validation successful: template_id={form.template_id}")
        
        # Test TemplateCreate
        template = TemplateCreate(
            name="Test Template",
            pdf_path="src/test.pdf",
            fields={"field1": "value1", "field2": "value2"}
        )
        print(f"✓ TemplateCreate validation successful: name={template.name}")
        
        # Test validation errors
        try:
            bad_form = FormFill(template_id=-1, input_text="test")
            print("✗ Should have failed validation for negative template_id")
            return False
        except ValueError:
            print("✓ Validation correctly rejects negative template_id")
        
        return True
    except Exception as e:
        print(f"✗ Schema test failed: {e}")
        return False

def test_database():
    """Test database functionality"""
    print("\n=== Testing Database ===")
    try:
        from api.db.database import engine
        from api.db.models import SQLModel
        
        # Create tables
        SQLModel.metadata.create_all(engine)
        print("✓ Database tables created successfully")
        
        return True
    except Exception as e:
        print(f"✗ Database test failed: {e}")
        return False

def test_api():
    """Test FastAPI application"""
    print("\n=== Testing FastAPI App ===")
    try:
        from api.main import app
        from fastapi.testclient import TestClient
        
        client = TestClient(app)
        print(f"✓ FastAPI app loaded with {len(app.routes)} routes")
        
        # List routes
        for route in app.routes:
            if hasattr(route, 'path'):
                print(f"  - {route.path}")
        
        return True
    except Exception as e:
        print(f"✗ API test failed: {e}")
        return False

def test_file_system():
    """Test file system requirements"""
    print("\n=== Testing File System ===")
    
    required_files = [
        "src/inputs/file.pdf",
        "requirements.txt",
        "api/main.py",
        "src/llm.py",
        "src/filler.py",
        "src/controller.py"
    ]
    
    all_exist = True
    for file_path in required_files:
        exists = os.path.exists(file_path)
        status = "✓" if exists else "✗"
        print(f"{status} {file_path}: {'exists' if exists else 'MISSING'}")
        if not exists:
            all_exist = False
    
    return all_exist

def main():
    """Run all tests"""
    print("=" * 60)
    print("FIREFORM COMPREHENSIVE SYSTEM TEST")
    print("=" * 60)
    
    tests = [
        ("Imports", test_imports),
        ("LLM", test_llm),
        ("Filler", test_filler),
        ("Controller", test_controller),
        ("Schemas", test_schemas),
        ("Database", test_database),
        ("API", test_api),
        ("File System", test_file_system)
    ]
    
    results = {}
    for name, test_func in tests:
        try:
            results[name] = test_func()
        except Exception as e:
            print(f"\n✗ {name} test crashed: {e}")
            results[name] = False
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED! System is fully functional.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please review errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
