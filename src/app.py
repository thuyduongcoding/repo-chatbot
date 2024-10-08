import os
import subprocess
import openai
from openai import OpenAI

# llama_index library
from llama_index.llms.openai import OpenAI
from llama_index.core.tools import FunctionTool
from llama_index.core import Settings, StorageContext,load_index_from_storage
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.core.agent import AgentRunner
from llama_index.agent.openai import advanced_tool_call_parser, OpenAIAgentWorker

from utils import create_code_hierarchy_engine, list_all_files,create_vector_index 
from code_structure import generate_repo_structure_markdown, save_markdown_to_file
from code_search import search_code

import gradio as gr
import time

openai.api_key = input("Please input your OPENAI_API_KEY: ")

# Specify the URL of the repository you want to clone
repo_url = input("Please give me the github repository link you want to chat with: ")

ts = time.time()
# Specify the directory where you want to clone the repository
clone_dir = repo_url.split('/')[-1].split('.git')[0]

# Use subprocess to run the git clone command
try:
    if not(clone_dir in os.listdir('.')):  
        print('This is a new repository. Start cloning now...')
        subprocess.run(['git', 'clone', repo_url], check=True)
        print(f'Repository cloned to {clone_dir}')
    else:
        print('This repository has already been cloned.')
except subprocess.CalledProcessError as e:
    print(f'Error occurred while cloning the repository: {e}')

# Define LLM and embedding model
Settings.llm = OpenAI(model="gpt-4o-mini", api_key=openai.api_key)
Settings.embed_model = OpenAIEmbedding(model_name='text-embedding-3-small', api_key=openai.api_key)

# Specify the directory you want to list
root_dir = clone_dir

# List all files and directories in the repository
repo_file_list = list_all_files(root_dir)

if "repo_structure.md" not in os.listdir(root_dir):
    markdown_content = generate_repo_structure_markdown(root_dir)
    save_markdown_to_file(markdown_content, f"{root_dir}/repo_structure.md")
    repo_file_list.append(f"{root_dir}/repo_structure.md")
else:
    print("repo_structure.md is already existed")

vector_storage_path = f'{clone_dir}/vector_store'
if not (os.path.exists(vector_storage_path)):   
    # Create the vector index
    vector_index = create_vector_index(repo_file_list)

    # Store the vector and summary indexes
    print("Start to store the indexes...")
    vector_index.storage_context.persist(persist_dir=vector_storage_path)
    print('Store the vector index')
    print('---')
else:
    print('Already created indexes. Loading index from storage...')
    # Load the vector and summary store index
    vector_storage = StorageContext.from_defaults(persist_dir=vector_storage_path)
    vector_index = load_index_from_storage(vector_storage)

    print('Loaded indexes from storage')
    print('---')


def vector_query(query: str) -> dict:
    """Perform a vector search over an index.
    
    Args:
    - query (str): the string query to be embedded.
    """
    query_engine = vector_index.as_query_engine(
        similarity_top_k=5
        )
    response = query_engine.query(query)

    reference = set()
    for i in range(5):
        reference.add(response.source_nodes[i].metadata["file_path"])
    
    return [str(response), reference]
    

vector_query_engine = vector_index.as_query_engine(similarity_top_k=5)
vector_query_tool = FunctionTool.from_defaults(name="vector_tool",
                                               description="Useful in answering questions that cannot be found in the .py files",
                                               fn = vector_query)

code_query_engine, code_query_tool = create_code_hierarchy_engine(repo_file_list)
search_code_tool = FunctionTool.from_defaults(fn=search_code,
                                              name = "search_code_usage",
                                              description="Useful for searching a term or pattern in all files within a directory, \
                                                            such as to find where the function is used within the repository"
                                                            "Use a plain text word as input into the tool.")

system_prompt = (
    "You are a chatbot designed to assist users with questions related to a specific code repository. "
    "Your capabilities include, but are not limited to:\n\n"
    "## 1. Code Navigation\n"
    "   - Help users find implementations of functions or classes.\n"
    "   - Identify where specific functions or classes are used within the codebase.\n"
    f"  - If using the search_code_implementation tool, use this instruction: {code_query_engine.get_tool_instructions()}\n\n"
    "## 2. Documentation Assistance\n"
    "   - Read and summarize documentation and configuration files.\n\n"
    "## 3. File Comparison\n"
    "   - Compare files and highlight differences or similarities.\n\n"
    "## 4. Tool Utilization\n"
    "   - Always utilize the provided tools to answer questions. Do not rely on prior knowledge or assumptions.\n"
    "   - If the selected tools cannot provide an answer, feel free to use additional tools as necessary.\n\n"
    "## 5. Handling Non-Python Files\n"
    "   - For information retrieval from files that are not Python files (.py), use the `vector_query_tool` to assist in obtaining the required data.\n"
    "Besides, for any answers, please give the full path reference for the information retrieved from the answer if possible. Do not use hyperlink.\n"
    "If the answer includes the code, please give the ful path reference for the file giving the code if possible. Do not use hyperlink."
)

agent_worker = OpenAIAgentWorker.from_tools(
    tools = [vector_query_tool, code_query_tool,search_code_tool], 
    llm=Settings.llm, 
    verbose=True,
    system_prompt=system_prompt, 
    tool_call_parser=advanced_tool_call_parser
)
agent = AgentRunner(agent_worker)

print("Time to create the chatbot: (in seconds)", time.time() - ts)

def get_agent_response(message, history=[]): 
    # We need to have the history parameter here because ChatInterface requires it
    response = agent.chat(
        message
    )
    return (str(response))

# Create the Gradio interface
chatbot_interface = gr.ChatInterface(
    fn=get_agent_response, 
    title="Chat-with-repo Chatbot",
    description="Ask questions about the any Github repository "
)

# Launch the interface
chatbot_interface.launch()