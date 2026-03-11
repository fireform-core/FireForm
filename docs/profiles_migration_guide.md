# Migration Guide: Using Department Profiles

## For Existing FireForm Users

If you're already using FireForm, this guide will help you start using department profiles to improve extraction accuracy.

## What Changed?

### New Feature (Backward Compatible)
- Added optional `profile_name` parameter to form filling
- Your existing code continues to work without changes
- Profiles are opt-in for better accuracy

### No Breaking Changes
- All existing APIs work exactly as before
- Default behavior unchanged when `profile_name` is not provided
- Existing PDFs and templates continue to work

## Quick Migration

### Before (Still Works)
```python
from src.controller import Controller

controller = Controller()
output = controller.fill_form(
    user_input="Officer Smith, badge 4421...",
    fields=["textbox_0_0", "textbox_0_1", "textbox_0_2"],
    pdf_form_path="fire_report.pdf"
)
```

### After (Recommended for Common Forms)
```python
from src.controller import Controller

controller = Controller()
output = controller.fill_form(
    user_input="Officer Smith, badge 4421...",
    fields={},  # Can be empty when using profile
    pdf_form_path="fire_report.pdf",
    profile_name="fire_department"  # ← Add this line
)
```

## When Should You Migrate?

### ✅ Migrate to Profiles If:
1. You're using Cal Fire incident report forms
2. You're using standard police incident forms
3. You're using EMS patient care reports
4. You're experiencing null values in filled PDFs
5. You're seeing repeated/hallucinated values across fields

### ❌ Keep Current Approach If:
1. You're using custom department-specific forms
2. Your forms don't match standard Fire/Police/EMS structure
3. You've already created custom field mappings that work well
4. Your forms have unique fields not in profiles

## API Migration

### REST API - Before
```bash
POST /forms/fill
{
  "template_id": 1,
  "input_text": "Officer Smith, badge 4421..."
}
```

### REST API - After
```bash
POST /forms/fill
{
  "template_id": 1,
  "input_text": "Officer Smith, badge 4421...",
  "profile_name": "fire_department"  # ← Add this field
}
```

## Testing Your Migration

### Step 1: Test Without Profile (Baseline)
```python
# Fill form without profile
output_old = controller.fill_form(
    user_input=transcript,
    fields=your_fields,
    pdf_form_path="form.pdf"
)
# Check output_old for accuracy
```

### Step 2: Test With Profile
```python
# Fill same form with profile
output_new = controller.fill_form(
    user_input=transcript,
    fields={},
    pdf_form_path="form.pdf",
    profile_name="fire_department"
)
# Compare output_new with output_old
```

### Step 3: Compare Results
- Open both PDFs side by side
- Check for null values (should be reduced/eliminated)
- Check for repeated values (should be fixed)
- Verify field accuracy improved

## Gradual Migration Strategy

### Phase 1: Test (Week 1)
- Test profiles on non-critical forms
- Compare results with existing approach
- Verify accuracy improvements

### Phase 2: Pilot (Week 2-3)
- Use profiles for new form submissions
- Keep existing approach for critical forms
- Monitor for issues

### Phase 3: Full Adoption (Week 4+)
- Migrate all Fire/Police/EMS forms to profiles
- Update documentation and training
- Keep custom approach for non-standard forms

## Troubleshooting

### Issue: Profile doesn't match my form
**Solution:** Continue using your current approach or create a custom profile

### Issue: Some fields still null
**Solution:** Check if your transcript includes all required information

### Issue: Profile not found error
**Solution:** Verify profile name is one of: `fire_department`, `police_report`, `ems_medical`

### Issue: Want to use profiles in Docker
**Solution:** Profiles are automatically included - just use `profile_name` parameter

## Creating Custom Profiles

If standard profiles don't match your forms:

1. Create `src/profiles/my_department.json`:
```json
{
  "department": "My Department",
  "description": "Custom form description",
  "fields": {
    "Field Label 1": "textbox_0_0",
    "Field Label 2": "textbox_0_1"
  },
  "example_transcript": "Example text..."
}
```

2. Use your custom profile:
```python
output = controller.fill_form(
    user_input=transcript,
    fields={},
    pdf_form_path="form.pdf",
    profile_name="my_department"
)
```

## Getting Help

- **Documentation**: See `docs/profiles.md` for full details
- **Examples**: Run `python3 examples/profile_usage_example.py`
- **Tests**: Run `python3 tests/test_profiles_simple.py`
- **Issues**: Report problems on GitHub issue tracker

## Benefits of Migration

1. **Improved Accuracy** - LLM understands field context
2. **No Null Values** - Proper extraction for all fields
3. **No Hallucination** - Each field gets correct value
4. **Faster Setup** - No need to manually map fields
5. **Standardization** - Consistent behavior across departments

## Rollback Plan

If you need to rollback:

1. Simply remove the `profile_name` parameter
2. Your code returns to previous behavior
3. No data loss or corruption
4. Profiles can be disabled without uninstalling

## Summary

- ✅ Profiles are backward compatible
- ✅ Migration is optional and gradual
- ✅ Existing code continues to work
- ✅ Easy to test and compare results
- ✅ Simple rollback if needed

Start with testing on non-critical forms, then gradually adopt profiles for improved accuracy on Fire/Police/EMS forms.
