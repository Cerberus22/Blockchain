# Mutable global state shared across all modules.
from custom_types import Block

genesis_block = Block().genesis()
blockchain: list = [genesis_block]
mempool: set = set()
difficulty: int = 20
do_mine: bool = True
new_chain: dict = {}

server_peer = None
ME_PUBLIC_KEY = None

FETCH_TIMEOUT = 10  # seconds before an in-progress chain-fetch is considered stale
