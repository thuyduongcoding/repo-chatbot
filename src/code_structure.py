import os
import ast

def parse_python_file(file_path):
    """
    Parse a Python file to extract standalone functions and classes with their methods.

    Args:
    - file_path (str): Path to the Python file.

    Returns:
    - dict: A dictionary containing functions and classes with their methods in the file.
    """
    structure = {"classes": {}, "functions": []}

    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        file_content = f.read()

    try:
        tree = ast.parse(file_content, filename=file_path)
        
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                # Add the class to the structure
                structure["classes"][node.name] = {"methods": []}

                # Find methods within the class
                for class_node in node.body:
                    if isinstance(class_node, ast.FunctionDef):
                        structure["classes"][node.name]["methods"].append(class_node.name)

            elif isinstance(node, ast.FunctionDef):
                # Add standalone function to the structure
                structure["functions"].append(node.name)

    except SyntaxError as e:
        print(f"Error parsing {file_path}: {e}")

    return structure

def generate_repo_structure_markdown(repo_path):
    """
    Generate the structure of a code repository and save it to a Markdown file.

    Args:
    - repo_path (str): Path to the root of the repository.

    Returns:
    - str: The generated Markdown content representing the structure.
    """
    markdown_content = f"# Repository Structure: {os.path.basename(repo_path)}\n\n"
    
    for dirpath, dirnames, filenames in os.walk(repo_path):
        # Skip the .git directory to avoid unnecessary clutter
        if '.git' in dirpath:
            continue
        
        indent_level = dirpath.replace(repo_path, '').count(os.sep)
        indent = '  ' * indent_level
        markdown_content += f"{indent}- **`{os.path.basename(dirpath)}/`**\n"

        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            file_indent = '  ' * (indent_level + 1)
            
            if filename.endswith('.py'):
                # Process Python files to extract functions and classes
                file_structure = parse_python_file(file_path)
                markdown_content += f"{file_indent}- `{filename}`\n"
                
                for class_name, class_details in file_structure["classes"].items():
                    markdown_content += f"{file_indent}  - **Class**: `{class_name}`\n"
                    for method_name in class_details["methods"]:
                        markdown_content += f"{file_indent}    - **Method**: `{method_name}`\n"
                
                for function_name in file_structure["functions"]:
                    markdown_content += f"{file_indent}  - **Function**: `{function_name}`\n"
            else:
                # For non-Python files, just list the file
                markdown_content += f"{file_indent}- `{filename}`\n"
    
    return markdown_content

def save_markdown_to_file(markdown_content, output_file):
    """
    Save the generated Markdown content to a file.

    Args:
    - markdown_content (str): The Markdown content to save.
    - output_file (str): The output Markdown file path.
    """
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(markdown_content)
    print(f"Content saved to {output_file}")