#!/usr/bin/env python3
"""
Example: Using Department Profiles with FireForm

This example demonstrates how to use pre-built department profiles
to improve LLM extraction accuracy for common first responder forms.
"""

from src.profiles import ProfileLoader

def example_1_list_profiles():
    """Example 1: List all available profiles"""
    print("=" * 60)
    print("Example 1: List Available Profiles")
    print("=" * 60)
    
    profiles = ProfileLoader.list_profiles()
    print(f"\nAvailable profiles: {len(profiles)}")
    for profile in profiles:
        info = ProfileLoader.get_profile_info(profile)
        print(f"\n  • {profile}")
        print(f"    Department: {info['department']}")
        print(f"    Description: {info['description'][:60]}...")
    print()


def example_2_view_profile_fields():
    """Example 2: View fields in a profile"""
    print("=" * 60)
    print("Example 2: View Profile Fields")
    print("=" * 60)
    
    profile_name = 'fire_department'
    mapping = ProfileLoader.get_field_mapping(profile_name)
    
    print(f"\nFire Department Profile has {len(mapping)} fields:")
    for i, (label, field_id) in enumerate(mapping.items(), 1):
        print(f"  {i:2d}. {label:30s} → {field_id}")
    print()


def example_3_compare_with_without_profile():
    """Example 3: Compare extraction with and without profile"""
    print("=" * 60)
    print("Example 3: Profile Impact on Field Names")
    print("=" * 60)
    
    # Sample transcript
    transcript = """
    Officer Smith, badge 4421, responding to structure fire at 
    742 Evergreen Terrace on March 8th at 14:30. Two victims on scene: 
    Homer Simpson and Marge Simpson. Electrical fire in kitchen area.
    """
    
    print("\nSample Transcript:")
    print(transcript.strip())
    
    print("\n--- WITHOUT PROFILE ---")
    print("LLM receives generic field names:")
    print("  • textbox_0_0")
    print("  • textbox_0_1")
    print("  • textbox_0_2")
    print("Result: LLM has no context → null values or hallucinations")
    
    print("\n--- WITH FIRE DEPARTMENT PROFILE ---")
    print("LLM receives human-readable labels:")
    mapping = ProfileLoader.get_field_mapping('fire_department')
    for label in list(mapping.keys())[:5]:
        print(f"  • {label}")
    print("Result: LLM understands context → accurate extraction")
    print()


def example_4_profile_usage_in_code():
    """Example 4: Using profiles in code"""
    print("=" * 60)
    print("Example 4: Using Profiles in Code")
    print("=" * 60)
    
    print("\nCode example:")
    print("""
    from src.controller import Controller
    
    controller = Controller()
    
    # Fill form WITH profile (recommended for common forms)
    output_path = controller.fill_form(
        user_input="Officer Smith, badge 4421...",
        fields={},  # Can be empty when using profile
        pdf_form_path="path/to/fire_report.pdf",
        profile_name="fire_department"  # ← Use profile
    )
    
    # Fill form WITHOUT profile (for custom forms)
    output_path = controller.fill_form(
        user_input="Employee John Doe...",
        fields=["Employee Name", "Job Title", "Department"],
        pdf_form_path="path/to/custom_form.pdf",
        profile_name=None  # ← No profile
    )
    """)
    print()


def example_5_api_usage():
    """Example 5: Using profiles via API"""
    print("=" * 60)
    print("Example 5: Using Profiles via API")
    print("=" * 60)
    
    print("\nAPI Endpoints:")
    print("""
    # List all profiles
    GET /profiles/
    Response: ["ems_medical", "fire_department", "police_report"]
    
    # Get profile details
    GET /profiles/fire_department
    Response: {
      "department": "Fire Department",
      "description": "...",
      "fields": {...},
      "example_transcript": "..."
    }
    
    # Fill form with profile
    POST /forms/fill
    {
      "template_id": 1,
      "input_text": "Officer Smith, badge 4421...",
      "profile_name": "fire_department"
    }
    """)
    print()


def example_6_when_to_use_profiles():
    """Example 6: When to use profiles"""
    print("=" * 60)
    print("Example 6: When to Use Profiles")
    print("=" * 60)
    
    print("\n✓ USE PROFILES when:")
    print("  • Filling Cal Fire incident reports")
    print("  • Filling standard police incident forms")
    print("  • Filling EMS patient care reports")
    print("  • Using common first responder forms")
    print("  • You want accurate extraction out-of-the-box")
    
    print("\n✗ DON'T USE PROFILES when:")
    print("  • Using custom department-specific forms")
    print("  • PDF fields don't match profile structure")
    print("  • You need custom field mappings")
    print("  • Form has unique fields not in profile")
    
    print("\n💡 TIP: For custom forms, use the Field Mapping Wizard (Issue #111)")
    print()


if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("FireForm Department Profile System - Usage Examples")
    print("=" * 60 + "\n")
    
    example_1_list_profiles()
    example_2_view_profile_fields()
    example_3_compare_with_without_profile()
    example_4_profile_usage_in_code()
    example_5_api_usage()
    example_6_when_to_use_profiles()
    
    print("=" * 60)
    print("For more information, see docs/profiles.md")
    print("=" * 60 + "\n")
