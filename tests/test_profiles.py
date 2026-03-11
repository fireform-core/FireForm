"""
Tests for the Department Profile System
"""
import pytest
from src.profiles import ProfileLoader


class TestProfileLoader:
    """Test suite for ProfileLoader functionality"""
    
    def test_list_profiles(self):
        """Test that all expected profiles are available"""
        profiles = ProfileLoader.list_profiles()
        
        assert isinstance(profiles, list)
        assert len(profiles) >= 3
        assert 'fire_department' in profiles
        assert 'police_report' in profiles
        assert 'ems_medical' in profiles
    
    def test_load_fire_department_profile(self):
        """Test loading the fire department profile"""
        profile = ProfileLoader.load_profile('fire_department')
        
        assert profile['department'] == 'Fire Department'
        assert 'description' in profile
        assert 'fields' in profile
        assert 'example_transcript' in profile
        
        # Check key fields exist
        fields = profile['fields']
        assert 'Officer Name' in fields
        assert 'Badge Number' in fields
        assert 'Incident Location' in fields
        assert 'Incident Date' in fields
    
    def test_load_police_report_profile(self):
        """Test loading the police report profile"""
        profile = ProfileLoader.load_profile('police_report')
        
        assert profile['department'] == 'Police Department'
        assert 'fields' in profile
        
        fields = profile['fields']
        assert 'Officer Name' in fields
        assert 'Badge Number' in fields
        assert 'Case Number' in fields
        assert 'Suspect Name' in fields
    
    def test_load_ems_medical_profile(self):
        """Test loading the EMS medical profile"""
        profile = ProfileLoader.load_profile('ems_medical')
        
        assert profile['department'] == 'Emergency Medical Services'
        assert 'fields' in profile
        
        fields = profile['fields']
        assert 'Paramedic Name' in fields
        assert 'Certification Number' in fields
        assert 'Patient Name' in fields
        assert 'Chief Complaint' in fields
    
    def test_load_nonexistent_profile(self):
        """Test that loading a non-existent profile raises FileNotFoundError"""
        with pytest.raises(FileNotFoundError) as exc_info:
            ProfileLoader.load_profile('nonexistent_profile')
        
        assert 'not found' in str(exc_info.value).lower()
    
    def test_get_field_mapping(self):
        """Test getting field mapping from a profile"""
        mapping = ProfileLoader.get_field_mapping('fire_department')
        
        assert isinstance(mapping, dict)
        assert len(mapping) > 0
        assert 'Officer Name' in mapping
        assert mapping['Officer Name'] == 'textbox_0_0'
    
    def test_get_profile_info(self):
        """Test getting profile metadata"""
        info = ProfileLoader.get_profile_info('fire_department')
        
        assert 'department' in info
        assert 'description' in info
        assert 'example_transcript' in info
        assert info['department'] == 'Fire Department'
        assert len(info['example_transcript']) > 0
    
    def test_all_profiles_have_required_fields(self):
        """Test that all profiles have the required schema fields"""
        profiles = ProfileLoader.list_profiles()
        
        for profile_name in profiles:
            profile = ProfileLoader.load_profile(profile_name)
            
            # Check required top-level keys
            assert 'department' in profile, f"{profile_name} missing 'department'"
            assert 'description' in profile, f"{profile_name} missing 'description'"
            assert 'fields' in profile, f"{profile_name} missing 'fields'"
            assert 'example_transcript' in profile, f"{profile_name} missing 'example_transcript'"
            
            # Check that fields is a non-empty dict
            assert isinstance(profile['fields'], dict), f"{profile_name} 'fields' is not a dict"
            assert len(profile['fields']) > 0, f"{profile_name} has no fields"
            
            # Check that all field values are strings
            for label, field_id in profile['fields'].items():
                assert isinstance(label, str), f"{profile_name} has non-string label"
                assert isinstance(field_id, str), f"{profile_name} has non-string field_id"
    
    def test_profile_field_count(self):
        """Test that profiles have a reasonable number of fields"""
        profiles = ProfileLoader.list_profiles()
        
        for profile_name in profiles:
            mapping = ProfileLoader.get_field_mapping(profile_name)
            # Each profile should have at least 10 fields
            assert len(mapping) >= 10, f"{profile_name} has too few fields: {len(mapping)}"
