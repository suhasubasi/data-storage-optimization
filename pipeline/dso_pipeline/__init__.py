"""Stream 3 pipeline package (SKELETON).

Contract: read ONE original (read-only), write derived files + ONE manifest.json into
data/derived/<asset_id>/. Never touch the database. NEVER delete or modify the original.
"""
__version__ = "0.1"
