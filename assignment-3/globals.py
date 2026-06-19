from custom_types import Block
from constants import AISTE_PUBLIC_KEY, AYKUT_PUBLIC_KEY, YURIAN_PUBLIC_KEY

ME_PUBLIC_KEY = None

# Global references
server_peer = None
team_peers = [None, None, None]
team_keys = [AISTE_PUBLIC_KEY, AYKUT_PUBLIC_KEY, YURIAN_PUBLIC_KEY]
group_id = bytes.fromhex("4687205acec0b3c4")
mempool = set()
difficulty = 8  # in bits
do_mine = True
new_chain = {}
FETCH_TIMEOUT = 10  # seconds before a fetch is considered stale

genesis_block = Block().genesis()
blockchain = [genesis_block]
