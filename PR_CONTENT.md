# Pull Request: Fix Exception Handler Registration

## Title
fix: register custom exception handlers in FastAPI app

---

## Description (Copy below)

### What's the problem?

While exploring the FireForm codebase, I noticed that the custom error handling system wasn't working as intended. The `AppError` exception class and its handler exist in the codebase (`api/errors/base.py` and `api/errors/handlers.py`), but they were never actually connected to the FastAPI application.

This means when code like this runs:
```python
raise AppError("Template not found", status_code=404)
```

Instead of returning a clean **404 Not Found** response, the API returns a generic **500 Internal Server Error** - which is confusing for API consumers and makes debugging harder.

### The Fix

A simple 2-line addition to `api/main.py`:

```python
from api.errors.handlers import register_exception_handlers

app = FastAPI()
register_exception_handlers(app)  # This was missing!
```

### What I Changed

| File | Change |
|------|--------|
| `api/main.py` | Added import and called `register_exception_handlers(app)` |
| `tests/test_error_handlers.py` | New test file with 4 comprehensive test cases |

### Testing

I added tests that verify:
- `AppError` with `status_code=404` actually returns 404 (not 500)
- `AppError` with default status code returns 400
- Error messages are properly included in JSON response
- Exception handlers are correctly registered in the main app

### Before & After

| Scenario | Before | After |
|----------|--------|-------|
| `raise AppError("Not found", 404)` | ❌ Returns 500 | ✅ Returns 404 |
| `raise AppError("Bad request")` | ❌ Returns 500 | ✅ Returns 400 |
| Error message in response | ❌ Generic error | ✅ `{"error": "Not found"}` |

### Why This Matters

This fix ensures that:
1. API consumers get meaningful error codes they can handle programmatically
2. The existing error handling code actually works as designed
3. Debugging becomes easier with proper status codes

Fixes #295

---

*Happy to make any changes if needed!*
