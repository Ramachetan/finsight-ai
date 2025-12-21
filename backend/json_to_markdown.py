#!/usr/bin/env python3
"""
Convert JSON to Markdown format with key separators.
"""

import json
import sys
from pathlib import Path


def format_value(value, indent_level=0):
    """Format a value for markdown display."""
    indent = "  " * indent_level
    
    if isinstance(value, dict):
        if not value:
            return "{}"
        lines = [""]
        for k, v in value.items():
            formatted = format_value(v, indent_level + 1)
            lines.append(f"{indent}  **{k}**: {formatted}")
        return "\n".join(lines)
    elif isinstance(value, list):
        if not value:
            return "[]"
        lines = [""]
        for i, item in enumerate(value, 1):
            formatted = format_value(item, indent_level + 1)
            lines.append(f"{indent}  {i}. {formatted}")
        return "\n".join(lines)
    elif isinstance(value, str):
        # Check if it's very long text
        if len(value) > 200:
            return f"```\n{value}\n```"
        return str(value)
    elif isinstance(value, bool):
        return "Yes" if value else "No"
    elif value is None:
        return "—"
    else:
        return str(value)


def json_to_markdown(json_data, title="Document"):
    """Convert JSON data to markdown format."""
    markdown_lines = [
        f"# {title}",
        "",
    ]
    
    if isinstance(json_data, dict):
        for i, (key, value) in enumerate(json_data.items(), 1):
            # Add key as heading
            markdown_lines.append(f"## {key}")
            markdown_lines.append("")
            
            # Format the value
            formatted_value = format_value(value, indent_level=0)
            markdown_lines.append(formatted_value)
            markdown_lines.append("")
            
            # Add separator (except for last item)
            if i < len(json_data):
                markdown_lines.append("---")
                markdown_lines.append("")
    
    return "\n".join(markdown_lines)


def convert_json_to_markdown(json_file: str, output_file: str = None) -> None:
    """
    Convert a JSON file to Markdown format.
    
    Args:
        json_file: Path to the input JSON file
        output_file: Path to the output markdown file
    """
    try:
        # Read JSON file
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Determine output path
        if output_file is None:
            p = Path(json_file)
            output_file = str(p.parent / f"{p.stem}.md")
        
        # Get title from filename
        title = Path(json_file).stem.replace('-', ' ').title()
        
        # Convert to markdown
        markdown_content = json_to_markdown(data, title)
        
        # Write markdown file
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        
        print(f"✓ Converted to Markdown: {output_file}")
        
        # Print stats
        file_size = Path(output_file).stat().st_size
        line_count = len(markdown_content.split('\n'))
        print(f"  File size: {file_size:,} bytes")
        print(f"  Lines: {line_count}")
        
    except json.JSONDecodeError as e:
        print(f"✗ Error: Invalid JSON - {e}")
        sys.exit(1)
    except FileNotFoundError:
        print(f"✗ Error: File not found - {json_file}")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python json_to_markdown.py <json_file> [output_file]")
        print("\nExample:")
        print("  python json_to_markdown.py data.json")
        print("  python json_to_markdown.py data.json output.md")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    convert_json_to_markdown(input_file, output_file)
