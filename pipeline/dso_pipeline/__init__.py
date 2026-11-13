"""Stream 3 pipeline package.

Contract: read ONE original (read-only), write derived files + ONE manifest.json into
data/derived/<asset_id>/. Never touch the database. NEVER delete or modify the original.
Processing a file does not save storage by itself; it only ADDS derived bytes.
"""
__version__ = "0.1.0"
