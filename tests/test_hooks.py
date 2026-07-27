"""
Unit tests for Lifecycle Hook Manager (src/hooks.py).
"""
import json
import pytest
from unittest.mock import MagicMock
from src.hooks import HookManager, load_hooks_config, resolve_handler_string, get_hook_manager


def test_load_hooks_config_valid(tmp_path):
    """Test loading valid hooks.json file."""
    config_file = tmp_path / "hooks.json"
    data = {
        "version": "1.0.0",
        "hooks": {
            "on_log": {"name": "on_log", "event": "pipeline_log"}
        }
    }
    config_file.write_text(json.dumps(data), encoding="utf-8")
    config = load_hooks_config(str(config_file))
    assert config["version"] == "1.0.0"
    assert "on_log" in config["hooks"]


def test_load_hooks_config_fallback():
    """Test fallback when config file is missing."""
    config = load_hooks_config("non_existent_file.json")
    assert "version" in config
    assert "hooks" in config


def test_resolve_handler_string():
    """Test dynamic resolution of module:function handler strings."""
    fn = resolve_handler_string("src.hooks:get_hook_manager")
    assert fn == get_hook_manager
    
    invalid_fn = resolve_handler_string("non_existent_module:invalid_fn")
    assert invalid_fn is None


def test_hook_manager_registration_and_execution():
    """Test registering and executing hooks in HookManager."""
    mgr = HookManager(config_path="non_existent.json")
    log_calls = []

    def custom_log(msg: str) -> None:
        log_calls.append(msg)

    mgr.register("on_log", custom_log)
    mgr.trigger_on_log("Hello Test")
    assert log_calls == ["Hello Test"]

    mgr.unregister("on_log", custom_log)
    mgr.trigger_on_log("Hello Again")
    assert log_calls == ["Hello Test"]


def test_hook_manager_lifecycle_triggers():
    """Test pre_pipeline and post_pipeline triggers."""
    mgr = HookManager(config_path="non_existent.json")
    pre_context = {}
    post_context = {}

    def on_pre(ctx):
        nonlocal pre_context
        pre_context = ctx

    def on_post(ctx):
        nonlocal post_context
        post_context = ctx

    mgr.register("pre_pipeline", on_pre)
    mgr.register("post_pipeline", on_post)

    mgr.pre_pipeline({"start": True})
    assert pre_context == {"start": True}

    mgr.post_pipeline({"success": True})
    assert post_context == {"success": True}


def test_hook_manager_error_resilience():
    """Test that a failing handler does not prevent subsequent handlers from executing."""
    mgr = HookManager(config_path="non_existent.json")
    executed = []

    def failing_handler(msg):
        raise ValueError("Simulated failure")

    def working_handler(msg):
        executed.append(msg)

    mgr.register("on_log", failing_handler)
    mgr.register("on_log", working_handler)

    mgr.trigger_on_log("Resilience Test")
    assert executed == ["Resilience Test"]
