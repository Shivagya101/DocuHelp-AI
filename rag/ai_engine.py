import os
from typing import List, Tuple

# HTML & Text Processing
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import cohere
from langchain_cohere import CohereEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter, MarkdownHeaderTextSplitter, Language
import markdownify
    
from utils.llm_provider import llm

load_dotenv()

# Initialize raw Cohere client for Re-Ranking
cohere_async_client = cohere.AsyncClientV2(api_key=os.getenv("COHERE_API_KEY"))
# Initialize Cohere cloud embedding model (1024-dimension vectors)
print("Initializing Cohere embeddings model...")
embedding_model = CohereEmbeddings(model="embed-english-v3.0")

def clean_html(raw_html: str) -> str:
    """
    Strips HTML tags, scripts, and styles to leave only readable text.
    Uses BeautifulSoup to extract main content and markdownify to convert to Markdown.
    """
    
    soup = BeautifulSoup(raw_html, "html.parser")
    
    # Remove junk tags aggressively to ensure we don't scrape sidebars and footers
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "meta", "aside", "svg", "iframe"]):
        tag.decompose()
        
    # We no longer strictly look for <main>. We just take the whole <body> since we already deleted the junk!
    # This prevents us from missing documentation on poorly structured sites like bhailang.js.org
    main_content = soup.find("body") or soup
    
    # Convert to Markdown
    md_text = markdownify.markdownify(str(main_content), heading_style="ATX")
    
    # Clean up excessive blank lines
    clean_lines = []
    blank_count = 0
    for line in md_text.splitlines():
        line = line.strip()
        if not line:
            blank_count += 1
            if blank_count <= 2:
                clean_lines.append("")
        else:
            blank_count = 0
            clean_lines.append(line)
            
    return "\n".join(clean_lines)


def generate_chunks(policy_text: str) -> List[Tuple[str, str]]:
    """
    Implements Markdown Header chunking combined with Parent-Child chunking.
    Splits text along logical Markdown headers, then splits those into tiny Child chunks.
    Returns just the raw text chunks: (child_text, parent_text).
    """
    if not policy_text:
        return []
        
    print(f"[CHUNK] Chunking policy text ({len(policy_text)} chars) using Markdown Header strategy...")
    
    headers_to_split_on = [
        ("#", "H1"),
        ("##", "H2"),
        ("###", "H3"),
    ]
    markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
    
    # 1. Split by Markdown Headers to create semantic Parent sections
    md_header_splits = markdown_splitter.split_text(policy_text)
    
    # 2. Safety Net: Ensure no single section exceeds LLM limits, but respect code blocks
    parent_fallback_splitter = RecursiveCharacterTextSplitter.from_language(
        language=Language.MARKDOWN, chunk_size=2000, chunk_overlap=200, keep_separator=True
    )
    parent_chunks_docs = parent_fallback_splitter.split_documents(md_header_splits)
    
    # 3. Precision Splitter for Vector Search (Also code-aware)
    child_splitter = RecursiveCharacterTextSplitter.from_language(
        language=Language.MARKDOWN, chunk_size=400, chunk_overlap=40, keep_separator=True
    )
    
    all_children = []
    child_to_heading_map = []
    child_to_parent_map = []
    
    for doc in parent_chunks_docs:
        # Reconstruct the headers so the LLM has context of where this chunk came from
        headers = " > ".join(doc.metadata.values())
        heading_string = f"Section: {headers}" if headers else "Root Document"
        parent_text = f"{heading_string}\n\n{doc.page_content}"
        
        # Break parent into tiny children for precise embedding
        children = child_splitter.split_text(parent_text)
        for child in children:
            all_children.append(child)
            child_to_heading_map.append(heading_string)
            child_to_parent_map.append(parent_text)
            
    print(f"[CALC] Generated {len(all_children)} text chunks. Passing to deduplication gate...")
    return list(zip(all_children, child_to_heading_map, child_to_parent_map))





async def chat_with_policy_async(query: str, context: str, history: List[dict] = None) -> str:
    """
    Directly answers user's questions about the policy using the provided chunk context.
    """
    if not context:
        yield "Error: Relevant policy chunks not found."
        return

    history_str = ""
    if history:
        history_str = "\n".join([f"{msg['role'].capitalize()}: {msg['content']}" for msg in history])

    print(f"[CHAT] Answering chat question asynchronously using RAG context...")
    
    prompt = f"""
    You are an expert AI assistant answering questions based on the provided software documentation.
    
    Instructions:
    - Answer ONLY using the information found in the context.
    - Do NOT add outside knowledge.
    - Provide a concise, structured answer.
    - If multiple parts of the answer exist, summarize them clearly.
    - If the answer is not found, say:
      "Hehe, I cannot find that information in the policy."
    - IMPORTANT: If you output any code snippets, CLI commands, or JSON responses, you MUST wrap them in Markdown code blocks (e.g., ```json or ```bash) so they render properly.
    - IMPORTANT: If you use information from a specific context source, you MUST append its source number at the end of the relevant sentence or paragraph. For example: "The company stores data for 30 days [1]."

    Context:
    {context}
    
    Previous Chat History:
    {history_str}

    Question:
    {query}

    Answer:
    """
    try:
        async for chunk in llm.astream(prompt):
            yield chunk.content
    except Exception as e:
        yield f"AI Error: {str(e)}"

async def expand_query_async(query: str, history: List[dict] = None) -> str:
    """
    Supercharges the user's query by generating synonyms and legal jargon using an LLM.
    Also acts as a standalone question generator using chat history.
    This creates a dense, highly relevant query for vector search.
    """
    print(f"[SEARCH] Expanding query for better retrieval: '{query}'")
    
    history_str = ""
    if history:
        history_str = "\n".join([f"{msg['role'].capitalize()}: {msg['content']}" for msg in history])

    prompt = f"""
    You are an expert search term generator for software documentation and API references.
    The user is asking a question. Your goal is to rewrite and expand the user's question to be standalone and highly optimized for a vector database search.
    
    Instructions:
    1. Look at the Previous Chat History (if provided) to understand the context of the user's latest question. 
    2. If the user's question is a follow-up (e.g., uses pronouns like "it", "they", "this"), resolve the pronouns using the history so the question stands alone.
    3. If the user's question is a completely new, unrelated topic, IGNORE the history entirely to prevent noise.
    4. Finally, expand the standalone question by adding highly relevant synonyms, jargon, and related terms that are likely to appear in documentation.
    
    Return ONLY the expanded query string. Do not answer the question. Do not include quotes or conversational filler.

    Previous Chat History:
    {history_str}

    User: "{query}"
    Expanded:
    """
    try:
        response = await llm.ainvoke(prompt)
        expanded = response.content.strip()
        print(f"[MAGIC] Expanded Query: '{expanded}'")
        return expanded
    except Exception as e:
        print(f"Error expanding query, falling back to original: {e}")
        return query

async def rerank_chunks(query: str, chunks: List[dict], top_n: int = 5) -> List[dict]:
    """
    Passes a large batch of chunks to Cohere's Cross-Encoder to mathematically sort them
    and returns only the most highly relevant chunks.
    Expects chunks to be a list of dicts: [{"text": "...", "url": "..."}]
    """
    if not chunks:
        return []
        
    print(f"[RANK] Re-Ranking {len(chunks)} chunks with Cohere Cross-Encoder...")
    
    # Extract just the text for Cohere
    documents = [c["text"] for c in chunks]
    
    try:
        response = await cohere_async_client.rerank(
            model="rerank-english-v3.0",
            query=query,
            documents=documents,
            top_n=top_n
        )
        
        # response.results is a list of objects containing the index and relevance_score
        ranked_chunks = [chunks[res.index] for res in response.results]
        print(f"[SUCCESS] Re-Ranking complete. Returning top {len(ranked_chunks)} chunks.")
        return ranked_chunks
        
    except Exception as e:
        print(f"Error re-ranking chunks, falling back to original order: {e}")
        # Fallback: just return the top_n chunks as they were originally sorted
        return chunks[:top_n]