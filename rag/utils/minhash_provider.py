import os
import re
from datasketch import MinHash, MinHashLSH
from dotenv import load_dotenv

load_dotenv()

# We configure 256 permutations for Enterprise-grade 6% error estimation.
NUM_PERM = 256
# The threshold the user explicitly requested for duplicate detection.
SIMILARITY_THRESHOLD = 0.90

def get_redis_config():
    """Extract host and port from REDIS_URL for datasketch."""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    # Basic parsing for redis://host:port/db
    host = "localhost"
    port = 6379
    match = re.search(r"redis://(.*?):(\d+)", redis_url)
    if match:
        host = match.group(1)
        port = int(match.group(2))
    return {"host": host, "port": port}

def get_lsh() -> MinHashLSH:
    """
    Returns a Redis-backed MinHash LSH index.
    This provides horizontal scalability across distributed workers.
    """
    redis_config = get_redis_config()
    
    # We use a unique basename so multiple projects don't collide in the same Redis instance.
    return MinHashLSH(
        threshold=SIMILARITY_THRESHOLD,
        num_perm=NUM_PERM,
        storage_config={
            'type': 'redis',
            'redis': redis_config,
            'basename': b'policy_rag_lsh'
        }
    )

def generate_minhash(text: str) -> MinHash:
    """
    Generates a fixed-size mathematical signature (256 integers) for any document.
    """
    m = MinHash(num_perm=NUM_PERM)
    
    # Simple tokenization: lowercase and extract alphabetic words
    tokens = re.findall(r'[a-z]+', text.lower())
    
    # To improve accuracy, we generate 3-grams of tokens (words, not characters)
    for i in range(len(tokens) - 2):
        shingle = f"{tokens[i]} {tokens[i+1]} {tokens[i+2]}"
        m.update(shingle.encode('utf8'))
        
    # If the document is extremely short (less than 3 words)
    if len(tokens) <= 2:
        for token in tokens:
            m.update(token.encode('utf8'))
            
    return m
