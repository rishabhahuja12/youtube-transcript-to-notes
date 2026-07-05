"""Tests for the Knowledge Graph module."""
import json
from unittest.mock import patch, MagicMock
from src.knowledge_graph import extract_concepts, build_graph, render_html

class DummyProviderConfig:
    def __init__(self):
        self.provider = "dummy"
        self.endpoint_url = "http://dummy"
        self.api_key = "dummy"
        self.model_name = "dummy-model"

@patch("src.knowledge_graph.call_llm")
def test_extract_concepts_success(mock_call_llm):
    """Test successful extraction of concepts returning valid JSON."""
    mock_response = '''```json
{
  "nodes": [{"id": "Concept1", "label": "Concept One", "group": 1}],
  "edges": [{"source": "Concept1", "target": "Concept2", "label": "relates to"}]
}
```'''
    mock_call_llm.return_value = mock_response
    config = DummyProviderConfig()
    
    logs = []
    def on_log(msg):
        logs.append(msg)
        
    result = extract_concepts("Some markdown text", config, on_log)
    
    assert "nodes" in result
    assert "edges" in result
    assert result["nodes"][0]["id"] == "Concept1"
    assert result["edges"][0]["source"] == "Concept1"

def test_build_graph():
    """Test graph building logic and missing node creation."""
    graph_data = {
        "nodes": [{"id": "Concept1", "label": "Concept One", "group": 1}],
        "edges": [{"source": "Concept1", "target": "Concept2", "label": "relates to"}]
    }
    
    valid_graph = build_graph(graph_data)
    
    # Should create Concept2 node automatically
    assert len(valid_graph["nodes"]) == 2
    assert any(n["id"] == "Concept2" for n in valid_graph["nodes"])
    assert "links" in valid_graph
    assert len(valid_graph["links"]) == 1

def test_render_html():
    """Test HTML rendering contains necessary components."""
    graph_data = {
        "nodes": [{"id": "Concept1", "label": "Concept One", "group": 1}],
        "edges": [{"source": "Concept1", "target": "Concept2", "label": "relates to"}]
    }
    
    html = render_html(graph_data)
    
    assert "mermaid" in html.lower()
    assert "Concept1" in html
    assert "Concept2" in html
    assert "relates to" in html

@patch("src.knowledge_graph.call_llm")
def test_extract_concepts_error(mock_call_llm):
    """Test extraction of concepts gracefully handles exceptions."""
    mock_call_llm.side_effect = Exception("API rate limit exceeded")
    config = DummyProviderConfig()
    
    logs = []
    def on_log(msg):
        logs.append(msg)
        
    import pytest
    with pytest.raises(Exception, match="API rate limit exceeded"):
        extract_concepts("Some markdown text", config, on_log)
        
    assert len(logs) > 0
    assert "API rate limit exceeded" in logs[-1]
