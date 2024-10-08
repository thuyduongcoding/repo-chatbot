import os
import warnings
from typing import Dict
from llama_index.llms.openai.utils import OpenAIToolCall
import json
import re

from openai import BadRequestError
from tqdm import tqdm
from llama_index.llms.openai import OpenAI
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.core import SimpleDirectoryReader, SummaryIndex, VectorStoreIndex
from llama_index.core.node_parser import CodeSplitter, SentenceSplitter, SemanticSplitterNodeParser
from llama_index.core.tools import QueryEngineTool
from llama_index.packs.code_hierarchy import CodeHierarchyKeywordQueryEngine, CodeHierarchyNodeParser

# Settings the warnings to be ignored 
warnings.filterwarnings('ignore') 

# Set up OpenAI API key and default models
with open('../API_key') as f:
    os.environ['OPENAI_API_KEY'] = f.read()

llm = OpenAI(model="gpt-4o-mini", api_key=os.getenv('OPENAI_API_KEY'))
embed_model = OpenAIEmbedding(model_name='text-embedding-ada-002', api_key=os.getenv('OPENAI_API_KEY'))
    
def create_summary_file(repo_file_list):
    """
    Create the summary of each file in the repository

    Args:    
    - repo_file_list (list): list of all files in the repository.

    Return:
    - repo_file_list (list): list of all files appended with the summary file created
    """
    print('Summarizing files...')
    summary_content = ""
    for i in tqdm(range(len(repo_file_list))):
        try:
            # Load data
            reader = SimpleDirectoryReader(input_files=[repo_file_list[i]])
            documents = reader.load_data()
            # Create summary index
            summary_index = SummaryIndex(documents)

            summary_engine = summary_index.as_query_engine()
            response = summary_engine.query("Give me the summary of the file")

            summary_content += f"Summary of {repo_file_list[i]}: {response}\n"
        
        # Leave out files that are not the code/text files
        except Exception:
            repo_file_list.remove(repo_file_list[i])
            i+=1
    print('Done summarizing')
    return summary_content

def list_all_files(root_dir):
    """
    List all the files in the repository

    Args:
    - root_dir: path to the repository
    """
    file_list = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Exclude .git directory
        if '.git' in dirnames:
            dirnames.remove('.git')

        # Add filepath to the list
        for filename in filenames:
            file_list.append(os.path.join(dirpath, filename))
    
    return file_list

def get_not_code_nodes(documents):
    """
    Using both SemanticSplitterNodeParser and SentenceSplitter to parse nodes from not-code files.
    Prevent BadRequestError from SemanticSplitterNodeParser 

    Args:
    - documents: documents that are not the code files
    
    Return:
    - all_nodes: nodes parsed from given documents

    """
    unsafe_splitter = SemanticSplitterNodeParser(
    buffer_size=5,
    embed_model=embed_model,
    show_progress=True,
    include_metadata=True,
)

    safe_splitter = SentenceSplitter(
        chunk_size=256,
        chunk_overlap=32,
        include_metadata=True,
    )

    all_nodes = []

    documents_count = len(documents)

    for i, document in enumerate(documents):
        print(f"Processing document {i} of {documents_count}.")
        nodes = []
        try:
            nodes = unsafe_splitter.get_nodes_from_documents([document])
        except BadRequestError:
            print("Parsing error: openai bad request. Parse by safe splitter.")
            nodes = safe_splitter.get_nodes_from_documents([document])

        all_nodes.extend(nodes)
    
    return all_nodes


def create_vector_index(repo_file_list):
    """
    Creating vector index from the list of repo files
    """
    print('Creating vector index...')

    # Separate code and non-code files
    code_files = [r for r in repo_file_list if r.endswith('.py')]
    not_code_files = [r for r in repo_file_list if r not in code_files]

    # Load code and non-code data 
    print('Start loading data...')
    reader_code = SimpleDirectoryReader(input_files=code_files)
    documents_code = reader_code.load_data()
    not_code_reader = SimpleDirectoryReader(input_files=not_code_files)
    documents_not_code = not_code_reader.load_data()
    print('Done loading data.')
    
    # Define the splitter method
    splitter_code = CodeSplitter(language='python', chunk_lines=200)
    splitter_not_code = SentenceSplitter(chunk_size=1024, chunk_overlap=200,include_metadata=True)
    
    # Create nodes from the documents
    print('Start chunking documents...')
    nodes_code = splitter_code.get_nodes_from_documents(documents_code, show_progress=True)
    print('Done chunking code files')
    nodes_not_code = splitter_not_code.get_nodes_from_documents(documents_not_code, show_progress=True)
    print('Done chunking non-code files.')

    # Create vector store index
    print('Creating vector store index...')
    
    # Integrate 2 types of nodes
    nodes = []
    for node in nodes_code:
        nodes.append(node)
    for node in nodes_not_code:
        nodes.append(node)

    vector_index = VectorStoreIndex(nodes)
    print('Done creating vector index.')

    return vector_index

def create_code_hierarchy_engine(repo_file_list):
    """ Create the engine specialize in navigating the code in the codebase"""
    documents = SimpleDirectoryReader(input_files=[r for r in repo_file_list if r.endswith(".py")],
                                      file_metadata=lambda x: {"filepath" : x}).load_data()
    split_nodes = CodeHierarchyNodeParser(language='python').get_nodes_from_documents(documents)

    code_query_engine = CodeHierarchyKeywordQueryEngine(nodes=split_nodes)

    code_query_tool = QueryEngineTool.from_defaults(query_engine=code_query_engine,
                                                      name = "search_code_implementation",
                                                      description="Useful for query the implementation of a function or class in the codebase, understand the structure of the codebase"
                                                                  "Use a function/class name as input to the tool")
    return code_query_engine, code_query_tool


def code_query_tool_call_parser(tool_call: OpenAIToolCall) -> Dict:
    """Parse tool calls that are not the function/class name"""
    arguments_str = tool_call.function.arguments
    if len(arguments_str.strip()) == 0:
    # OpenAI returns an empty string for functions containing no args
        return {}
    try:
        tool_call = json.loads(arguments_str)
        if not isinstance(tool_call, dict):
            raise ValueError("Tool call must be a dictionary")
        variable_name = list(tool_call.keys())[0]
        content = tool_call[variable_name]
        content = content.split("\\")[-1]
        return {variable_name:content}
    except json.JSONDecodeError as e:
        # pattern to match variable names and content within quotes
        pattern = r'([a-zA-Z_][a-zA-Z_0-9]*)\s*=\s*["\']+(.*?)["\']+'
        match = re.search(pattern, arguments_str)

        if match:
            variable_name = match.group(1)  # This is the variable name
            content = match.group(2)  # This is the content within the quotes
            content = content.split('\\')[-1]
            return {variable_name: content}
        raise ValueError(f"Invalid tool call: {e!s}")