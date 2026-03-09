#!/usr/bin/env python3
"""
Simple test script for the Department Profile System
Run with: python3 tests/test_profiles_simple.py
"""

from src.profiles import ProfileLoader

def test_list_profiles():
    print("Testing list_profiles()...")
    profiles = ProfileLoader.list_profiles()
    print(f"✓ Found {len(profiles)} profiles: {profiles}")
    assert 'fire_department' in profiles
    assert 'police_report' in profiles
    assert 'ems_medical' in profiles
    print("✓ All expected profiles present\n")

def test_load_profiles():
    print("Testing load_profile()...")
    profiles = ['fire_department', 'police_report', 'ems_medical']
    
    for profile_name in profiles:
        profile = ProfileLoader.load_profile(profile_name)
        print(f"✓ Loaded {profile_name}")
        print(f"  Department: {profile['department']}")
        print(f"  Fields: {len(profile['fields'])}")
        
        assert 'department' in profile
        assert 'description' in profile
        assert 'fields' in profile
        assert 'example_transcript' in profile
        assert len(profile['fields']) >= 10
    
    print("✓ All profiles loaded successfully\n")

def test_field_mappings():
    print("Testing get_field_mapping()...")
    
    # Test fire department
    fire_mapping = ProfileLoader.get_field_mapping('fire_department')
    print(f"✓ Fire Department has {len(fire_mapping)} fields")
    assert 'Officer Name' in fire_mapping
    assert 'Badge Number' in fire_mapping
    assert fire_mapping['Officer Name'] == 'textbox_0_0'
    
    # Test police report
    police_mapping = ProfileLoader.get_field_mapping('police_report')
    print(f"✓ Police Report has {len(police_mapping)} fields")
    assert 'Case Number' in police_mapping
    
    # Test EMS
    ems_mapping = ProfileLoader.get_field_mapping('ems_medical')
    print(f"✓ EMS Medical has {len(ems_mapping)} fields")
    assert 'Patient Name' in ems_mapping
    
    print("✓ All field mappings valid\n")

def test_profile_info():
    print("Testing get_profile_info()...")
    
    info = ProfileLoader.get_profile_info('fire_department')
    print(f"✓ Fire Department info:")
    print(f"  Department: {info['department']}")
    print(f"  Description: {info['description'][:50]}...")
    print(f"  Example transcript length: {len(info['example_transcript'])} chars")
    
    assert info['department'] == 'Fire Department'
    assert len(info['description']) > 0
    assert len(info['example_transcript']) > 0
    
    print("✓ Profile info retrieved successfully\n")

def test_nonexistent_profile():
    print("Testing error handling for nonexistent profile...")
    
    try:
        ProfileLoader.load_profile('nonexistent_profile')
        print("✗ Should have raised FileNotFoundError")
        assert False
    except FileNotFoundError as e:
        print(f"✓ Correctly raised FileNotFoundError: {e}")
    
    print()

if __name__ == '__main__':
    print("=" * 60)
    print("Department Profile System Tests")
    print("=" * 60)
    print()
    
    try:
        test_list_profiles()
        test_load_profiles()
        test_field_mappings()
        test_profile_info()
        test_nonexistent_profile()
        
        print("=" * 60)
        print("✓ ALL TESTS PASSED")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
