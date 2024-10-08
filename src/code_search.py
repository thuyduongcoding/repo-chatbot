import os
import re

def find_files(directory, file_extension=".py"):
    """
    Recursively find all files with a given extension in a directory.
    """
    files = []
    for root, dirs, file_list in os.walk(directory):
        for file_name in file_list:
            if file_name.endswith(file_extension):
                files.append(os.path.join(root, file_name))
    return files

def search_code(directory, search_term, regex=False, context_lines=2):
    """
    Search for a term or pattern in all files within a directory.

    :param directory: The root directory to search.
    :param search_term: The term or pattern to search for.
    :param regex: Whether to treat the search term as a regex pattern.
    :param context_lines: Number of lines to show before and after the match for context.
    :return: A dictionary with file paths as keys and list of matching lines with context as values.
    """
    results = {}
    files = find_files(directory)

    for file_path in files:
        with open(file_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()

        for i, line in enumerate(lines):
            if (regex and re.search(search_term, line)) or (not regex and search_term in line):
                start = max(i - context_lines, 0)
                end = min(i + context_lines + 1, len(lines))
                context = lines[start:end]
                results.setdefault(file_path, []).append((i + 1, context))

    return results

def display_search_results(results):
    """
    Display search results with context.

    :param results: A dictionary with search results.
    """
    for file_path, matches in results.items():
        print(f"\nIn file: {file_path}")
        for line_number, context in matches:
            print(f"Line {line_number}:")
            for context_line in context:
                print(context_line, end='')
            print("-" * 40)