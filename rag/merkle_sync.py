import hashlib
from typing import List, Tuple, Dict, Set

def hash_string(s: str) -> str:
    """Returns the SHA-256 hash of a given string."""
    return hashlib.sha256(s.encode('utf-8')).hexdigest()

class MerkleTree:
    """
    A 3-Level Semantic Merkle Tree designed specifically for Parent-Child Document Chunks.
    - Level 3 (Leaves): Hash of each Child Chunk text.
    - Level 2 (Branches): Hash of Heading String + concatenated Hashes of all its Children.
    - Level 1 (Root): Hash of concatenated Branch Hashes.
    """
    def __init__(self, chunks: List[Tuple[str, str, str]]):
        # chunks is a list of (child_text, heading_string, full_parent_text)
        self.root_hash: str = ""
        self.parents: Dict[str, str] = {}  # heading_string -> parent_hash
        self.children: Dict[str, List[Tuple[str, str, str]]] = {}  # heading_string -> list of (child_text, child_hash, full_parent_text)
        
        if chunks:
            self._build_tree(chunks)

    def _build_tree(self, chunks: List[Tuple[str, str, str]]):
        # 1. Group children by heading_string
        grouped = {}
        for child_text, heading_string, full_parent_text in chunks:
            if heading_string not in grouped:
                grouped[heading_string] = []
            grouped[heading_string].append((child_text, full_parent_text))

        parent_hashes = []
        
        # 2. Build Level 3 (Leaves) and Level 2 (Branches)
        for heading_string, child_data in grouped.items():
            # Hash each child
            child_nodes = [(c_text, hash_string(c_text), p_text) for c_text, p_text in child_data]
            self.children[heading_string] = child_nodes
            
            # Hash the parent (heading_string + concatenated child hashes)
            sorted_child_hashes = sorted([h for _, h, _ in child_nodes])
            combined_parent_string = heading_string + "".join(sorted_child_hashes)
            p_hash = hash_string(combined_parent_string)
            
            self.parents[heading_string] = p_hash
            parent_hashes.append(p_hash)
            
        # 3. Build Level 1 (Root)
        self.root_hash = hash_string("".join(sorted(parent_hashes)))

def diff_trees(old_tree: MerkleTree, new_tree: MerkleTree) -> Tuple[List[str], List[Tuple[str, str]], List[Tuple[str, str]]]:
    """
    Recursively walks down two Merkle Trees to find exact differences.
    Returns:
        - chunks_to_delete: list of old child_texts to remove from DB.
        - chunks_to_add: list of new (child_text, full_parent_text) tuples to add to DB.
        - to_update_parents: list of (old_parent_text, new_parent_text) to trigger Sibling Updates.
    """
    to_delete = []
    to_add = []
    to_update_parents = []
    
    # 1. Root Check (O(1) exit)
    if old_tree.root_hash == new_tree.root_hash:
        return [], [], []

    old_parents = set(old_tree.parents.keys())
    new_parents = set(new_tree.parents.keys())

    # 2. Deleted Parents (Entire sections removed)
    for p in old_parents - new_parents:
        to_delete.extend([c[0] for c, _, _ in old_tree.children[p]])
        
    # 3. New Parents (Entire sections added)
    for p in new_parents - old_parents:
        for c_text, _, p_text in new_tree.children[p]:
            to_add.append((c_text, p_text))

    # 4. Existing Parents (Sections modified)
    for p in old_parents.intersection(new_parents):
        # O(1) Branch Check
        if old_tree.parents[p] != new_tree.parents[p]:
            # The section changed, we must drill down to the Leaves
            old_c_map = {h: (c, p_text) for c, h, p_text in old_tree.children[p]}
            new_c_map = {h: (c, p_text) for c, h, p_text in new_tree.children[p]}
            
            old_h = set(old_c_map.keys())
            new_h = set(new_c_map.keys())
            
            # Drill-down: Find exact leaves deleted
            for h in old_h - new_h:
                to_delete.append(old_c_map[h][0])
                
            # Drill-down: Find exact leaves added
            for h in new_h - old_h:
                to_add.append((new_c_map[h][0], new_c_map[h][1]))
                
            # Sibling Update Magic
            if (len(old_h - new_h) > 0 or len(new_h - old_h) > 0):
                if len(old_tree.children[p]) > 0 and len(new_tree.children[p]) > 0:
                    old_parent_text = old_tree.children[p][0][2]
                    new_parent_text = new_tree.children[p][0][2]
                    if old_parent_text != new_parent_text:
                        to_update_parents.append((old_parent_text, new_parent_text))

    return to_delete, to_add, to_update_parents
