import pytest
from pydantic import ValidationError
from context_portal_mcp.db.models import UpdateContextArgs, LogCustomDataArgs, BatchLogItemsArgs

def test_fields_are_json_strings():
    """Verify that complex fields are exposed as strings in the JSON schema for strict mode compatibility."""
    
    # 1. UpdateContextArgs.content
    schema = UpdateContextArgs.model_json_schema()
    prop = schema['properties']['content']
    # Checking for 'anyOf' containing a string type or direct string type
    is_any_of = 'anyOf' in prop
    types = [x.get('type') for x in prop.get('anyOf', [])] if is_any_of else [prop.get('type')]
    assert 'string' in types, "UpdateContextArgs.content schema must allow string type"

    # 2. LogCustomDataArgs.value
    schema = LogCustomDataArgs.model_json_schema()
    prop = schema['properties']['value']
    # Json[Any] typically results in type: string
    assert prop.get('type') == 'string', "LogCustomDataArgs.value schema must be string"

    # 3. BatchLogItemsArgs.items
    schema = BatchLogItemsArgs.model_json_schema()
    prop = schema['properties']['items']
    assert prop.get('type') == 'string', "BatchLogItemsArgs.items schema must be string"

def test_json_string_parsing():
    """Verify that Pydantic correctly parses JSON strings into their target Python types."""
    
    # 1. UpdateContextArgs
    obj = UpdateContextArgs(workspace_id="test", content='{"foo": "bar"}')
    assert isinstance(obj.content, dict)
    assert obj.content == {"foo": "bar"}

    # 2. LogCustomDataArgs
    obj = LogCustomDataArgs(workspace_id="test", category="c", key="k", value='[1, 2, 3]')
    assert isinstance(obj.value, list)
    assert obj.value == [1, 2, 3]

    # 3. BatchLogItemsArgs
    json_list = '[{"summary": "item1"}, {"summary": "item2"}]'
    obj = BatchLogItemsArgs(workspace_id="test", item_type="decision", items=json_list)
    assert isinstance(obj.items, list)
    assert len(obj.items) == 2
    assert obj.items[0]["summary"] == "item1"
