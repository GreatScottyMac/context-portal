# ConPort MCP Server Schema Fix for OpenAI Compatibility

## Problem

OpenAI's strict mode (typically required for agentic workflows or gpt-5.x) enforces `additionalProperties: false` on all JSON objects in the schema. This conflicts with `Dict[str, Any]` fields used in ConPort (e.g., `content`, `patch_content`), which by definition allow arbitrary properties.

The previous proposed "fix" of forcing `additionalProperties: false` on these dictionary fields effectively **breaks them**, making it impossible to pass any actual content (since any key would be considered an forbidden "additional property").

## Solution: Use Pydantic's `Json` Type

The robust solution is to change the field type from `Dict[str, Any]` to `Json[Dict[str, Any]]`. 

This tells Pydantic to expect a **JSON-encoded string** as input, which it will automatically parse into a dictionary.
- **Schema:** The generated JSON Schema type becomes `"string"`.
- **Strict Mode:** Strings do not require `additionalProperties: false` validation, so this passes OpenAI's check.
- **Functionality:** Clients can still pass arbitrary complex objects, they just need to serialized them to a string first.

### Code Fix

Modify `src/context_portal_mcp/db/models.py`:

```python
from pydantic import BaseModel, Field, Json, model_validator
from typing import Optional, Dict, Any

class UpdateContextArgs(BaseArgs):
    """Arguments for updating product or active context.
    Provide either 'content' for a full update or 'patch_content' for a partial update.
    """
    # Change type to Json[Dict[str, Any]]
    content: Optional[Json[Dict[str, Any]]] = Field(None, description="The full new context content as a JSON string. Overwrites existing.")
    patch_content: Optional[Json[Dict[str, Any]]] = Field(None, description="A JSON string of changes to apply to the existing context (add/update keys).")

    @model_validator(mode='before')
    @classmethod
    def check_content_or_patch(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        content, patch_content = values.get('content'), values.get('patch_content')
        if content is None and patch_content is None:
            raise ValueError("Either 'content' or 'patch_content' must be provided.")
        if content is not None and patch_content is not None:
            raise ValueError("Provide either 'content' for a full update or 'patch_content' for a partial update, not both.")
        return values
```

You should also apply this pattern to any other model using `Dict[str, Any]` (e.g., `LogCustomDataArgs`).

### Impact on Clients

This is a **breaking change** for clients, but a necessary one for Strict Mode support.
- **Old Usage:** `update_product_context(content={"goals": "..."})`
- **New Usage:** `update_product_context(content='{"goals": "..."}')`

Most MCP clients and LLMs handle this gracefully. The schema description explicitly states it expects a JSON string.

## Verification

The generated schema for `content` will look like:
```json
{
  "title": "Content", 
  "description": "The full new context content as a JSON string...", 
  "default": null, 
  "type": "string"
}
```
This is fully compatible with OpenAI Strict Mode.
