"""
Knowledge Graph generation module.
"""
import json
import html
from src.llm_client import call_llm
from src.provider_pool import ProviderConfig

def extract_concepts(markdown_text: str, provider_config: ProviderConfig, on_log: callable) -> dict:
    """Extract concepts and relationships from markdown text to build a Knowledge Graph.
    
    Args:
        markdown_text: The markdown text to extract concepts from.
        provider_config: The provider configuration to use.
        on_log: Callback for logging messages.
        
    Returns:
        dict: A dictionary containing 'nodes' and 'edges' for the graph.
    """
    user_prompt = (
        "Extract key concepts and their relationships from the following text to "
        "build a Knowledge Graph.\n\n"
        "Return a JSON object with this exact structure:\n"
        "{\n"
        '  "nodes": [{"id": "Concept", "label": "Concept Name", "group": "Chapter Name", '
        '"definition": "Short definition", "section_anchor": "#anchor-link"}],\n'
        '  "edges": [{"source": "Concept1", "target": "Concept2", "label": "relationship"}]\n'
        "}\n\n"
        "The 'group' should be the topic or chapter name.\n"
        "The 'definition' should be a concise definition for tooltips.\n"
        "The 'section_anchor' should be the exact markdown anchor link (e.g. #1-chapter-name).\n"
        "Keep the graph concise but comprehensive (max 30-50 nodes).\n"
        "Text to process:\n"
        "---\n"
        f"{markdown_text[:30000]}\n"  # Limit to avoid huge context sizes
        "---\n"
    )

    system_prompt = "You are an expert knowledge extractor. You output valid JSON only."

    try:
        response = call_llm(
            provider=provider_config.provider,
            endpoint_url=provider_config.endpoint_url,
            api_key=provider_config.api_key,
            model_name=provider_config.model_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format="json_object"
        )
        # LLM might return JSON wrapped in markdown
        if response.startswith("```json"):
            response = response.strip("```json").strip("```")
        elif response.startswith("```"):
            response = response.strip("```")
            
        data = json.loads(response.strip())
        return data
    except Exception as e:
        on_log(f"Failed to extract concepts: {e}")
        raise

def build_graph(graph_data: dict) -> dict:
    """Validate and build the graph data structure.
    
    Args:
        graph_data: The extracted graph data.
        
    Returns:
        dict: The validated graph data.
    """
    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])
    
    # Ensure all targets and sources in edges exist in nodes
    node_ids = {n.get("id") for n in nodes}
    valid_edges = []
    
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if source not in node_ids:
            nodes.append({"id": source, "label": source, "group": "Other"})
            node_ids.add(source)
        if target not in node_ids:
            nodes.append({"id": target, "label": target, "group": "Other"})
            node_ids.add(target)
        valid_edges.append(edge)
        
    return {"nodes": nodes, "edges": valid_edges}

def render_html(graph_data: dict) -> str:
    """Render the graph data into an HTML string using Mermaid.js CDN.
    
    Args:
        graph_data: The validated graph data.
        
    Returns:
        str: The HTML content.
    """
    valid_graph = build_graph(graph_data)
    nodes = valid_graph.get("nodes", [])
    edges = valid_graph.get("edges", [])
    
    mermaid_lines = ["graph TD;"]
    
    # Group nodes by their 'group' property
    from collections import defaultdict
    groups = defaultdict(list)
    for node in nodes:
        group = node.get("group", "Other")
        groups[group].append(node)
        
    for group, group_nodes in groups.items():
        if group != "Other":
            # Sanitize group name for subgraph id
            group_id = str(group).replace(' ', '_').replace('"', '').replace('(', '').replace(')', '')
            group_label = html.escape(str(group).replace(chr(34), ""))
            mermaid_lines.append(f'    subgraph {group_id} ["{group_label}"]')
            
        for node in group_nodes:
            node_id = str(node.get("id")).replace('"', '').replace("(", "").replace(")", "").replace(" ", "_")
            node_label = html.escape(str(node.get("label", node_id)).replace('"', '').replace("(", "").replace(")", ""))
            # Node definition
            if group != "Other":
                mermaid_lines.append(f'        {node_id}["{node_label}"];')
            else:
                mermaid_lines.append(f'    {node_id}["{node_label}"];')
                
            # Interactivity (Click directive)
            anchor = html.escape(str(node.get("section_anchor", "#")))
            if anchor and not anchor.startswith("#"):
                anchor = "#" + anchor
            definition = html.escape(str(node.get("definition", "")).replace('"', "'"))
            
            # Click syntax: click nodeId "link" "tooltip"
            if group != "Other":
                if definition:
                    mermaid_lines.append(f'        click {node_id} "{anchor}" "{definition}"')
                else:
                    mermaid_lines.append(f'        click {node_id} "{anchor}"')
            else:
                if definition:
                    mermaid_lines.append(f'    click {node_id} "{anchor}" "{definition}"')
                else:
                    mermaid_lines.append(f'    click {node_id} "{anchor}"')

        if group != "Other":
            mermaid_lines.append("    end")
            
    # Add edges
    for link in edges:
        source = str(link.get("source")).replace('"', '').replace("(", "").replace(")", "").replace(" ", "_")
        target = str(link.get("target")).replace('"', '').replace("(", "").replace(")", "").replace(" ", "_")
        label = html.escape(str(link.get("label", "")).replace('"', '').replace("(", "").replace(")", ""))
        if label:
            mermaid_lines.append(f'    {source} -->|"{label}"| {target};')
        else:
            mermaid_lines.append(f'    {source} --> {target};')
            
    mermaid_content = "\n".join(mermaid_lines)
    
    html_output = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Knowledge Graph Data</title>
    <style>
        body {{ margin: 0; padding: 20px; font-family: sans-serif; background-color: #ffffff; }}
        #graph-container {{ width: 100%; height: 100%; display: flex; justify-content: center; }}
        pre.mermaid {{ background: #f4f4f4; padding: 15px; border-radius: 5px; }}
    </style>
</head>
<body>
    <h2>Knowledge Graph Data (Raw Mermaid)</h2>
    <div id="graph-container">
        <pre class="mermaid">
{mermaid_content}
        </pre>
    </div>
</body>
</html>"""
    return html_output
