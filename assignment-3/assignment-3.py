import sys
import time
import hashlib
import argparse
import random
import threading
import asyncio
from messages import *
from ipv8.peer import Peer
from custom_types import *
from ipv8_service import IPv8
from dataclasses import dataclass
from ipv8.util import run_forever
from ipv8.lazy_community import lazy_wrapper
from ipv8.peerdiscovery.network import PeerObserver
from asyncio import run, to_thread, sleep, create_task
from ipv8.community import Community, CommunitySettings
from ipv8.messaging.payload_dataclass import DataClassPayload, type_from_format
from ipv8.configuration import (
    ConfigBuilder,
    Strategy,
    WalkerDefinition,
    default_bootstrap_defs,
)

CHAIN_COMMUNITY_ID = bytes.fromhex("abcdef1234abcdef1234abcdef1234abcdef1234")
SERVER_COMMUNITY_ID = bytes.fromhex("4c616233426c6f636b636861696e323032365057")
SERVER_PUBLIC_KEY = bytes.fromhex(
    "4c69624e61434c504b3ae3fc099fb56ca3b5e1de9a1c843387f2acdbb78b1bd4350ffde518068a0d246344b10d0d8c355fd0d76873e7d7f7838f3715e025af08f791324495e083331ce6"
)
AISTE_PUBLIC_KEY = bytes.fromhex(
    "4c69624e61434c504b3a2513a65668a4c90fecaab284db8c782ed99a4bcab0284902e50127c9bcafda4998739097897c8ea911a9dff86f6ca2b71d3fd9086b1c4775d6bd3d5c00c818f9"
)
AYKUT_PUBLIC_KEY = bytes.fromhex(
    "4c69624e61434c504b3ad8e3c43d2221dcef7f94eb20d566afeba009e90eb999d69511ebcbf369a3303895c92c299356298f6f115c26fb14ad994347b8447ac028640344b0abc34221cd"
)
YURIAN_PUBLIC_KEY = bytes.fromhex(
    "4c69624e61434c504b3afbc497359b4d8bc2d70fc55a3261ad831872055bd13bca87379be73cf9246e1611d4b25ac771d74cc8628d2c44c85f5de40aa9c79f2d6e9901a967063b621fc4"
)
ME_PUBLIC_KEY = None


# Parse arguments
keyfile = sys.argv[1] if len(sys.argv) > 1 else "yurian"

# Response compilations
_ = RegisterBlockchainResponse(False, "")
_ = SubmitTransactionRequest(b"", b"", 0, b"")
_ = SubmitTransactionResponse(False, b"", "")
_ = GetChainHeigthRequest(0)
_ = GetBlockRequest(0)
_ = GetChainHeigthResponse(0, 0, b"")
_ = GetBlockResponse(0, b"", b"", 0, 0, 0, b"", b"")
_ = ChangedDifficultyMessage(0)
_ = BlockAnnouncementMessage(0, b"")
_ = EntireChainRequest(0, 0)
_ = EntireChainResponse(0, 0, 0, b"")

# Global references
server_peer = None
team_peers = [None, None, None]
team_keys = [AISTE_PUBLIC_KEY, AYKUT_PUBLIC_KEY, YURIAN_PUBLIC_KEY]
group_id = bytes.fromhex("4687205acec0b3c4")
mempool = set()
difficulty = 20  # in bits
do_mine = True
new_chain = {}
FETCH_TIMEOUT = 10  # seconds before a fetch is considered stale

genesis_block = Block().genesis()
blockchain = [genesis_block]


# Small helpertje
async def async_input(prompt: str = "") -> str:
    return await to_thread(input, prompt)


def leading_zero_bits(data: bytes) -> int:
    zero_bits = 0
    for byte in data:
        if byte == 0:
            zero_bits += 8
            continue
        zero_bits += 8 - byte.bit_length()
        break
    return zero_bits


def validate_block(block: Block, prev_hash: bytes, do_print=False) -> bool:
    computed_hash = hashlib.sha256(block.get_tx_hashes()).digest()
    if block.txs_hash != computed_hash:
        if do_print:
            print(
                f"Invalid txs_hash ({block.height}): {block.txs_hash.hex()}, expected {computed_hash.hex()}"
            )
            print("Debug: individual tx hashes:")
            for i, tx in enumerate(block.txs):
                print(f"  tx[{i}]: {tx.hash().hex()}")
            print(block)
            print(block.txs)
        return False
    if block.prev_hash != prev_hash:
        if do_print:
            print(
                f"Invalid prev_hash ({block.height}): {block.prev_hash.hex()}, expected {prev_hash.hex()}"
            )
        return False
    if leading_zero_bits(block.hash()) < block.difficulty:
        if do_print:
            print(
                f"Invalid difficulty ({block.height}): {leading_zero_bits(block.hash())}, expected {block.difficulty}"
            )
        return False
    return True


def mine_block(candidate: Block) -> Block:
    nonce = 0
    while True:
        candidate.nonce = nonce
        if leading_zero_bits(candidate.hash()) >= candidate.difficulty:
            return candidate
        nonce = random.randint(0, 2**32 - 1)
        time.sleep(0)


class BlockchainCommunity(Community):
    community_id = CHAIN_COMMUNITY_ID

    def __init__(self, settings: CommunitySettings) -> None:
        super().__init__(settings)
        self.add_message_handler(
            SubmitTransactionRequest, self.on_submit_transaction_request
        )
        self.add_message_handler(
            SubmitTransactionResponse, self.on_submit_transaction_response
        )
        self.add_message_handler(GetBlockResponse, self.on_get_block_response)
        self.add_message_handler(
            GetChainHeigthResponse, self.on_get_chain_height_response
        )
        self.add_message_handler(BlockAnnouncementMessage, self.on_block_announcement)
        self.add_message_handler(ChangedDifficultyMessage, self.on_changed_difficulty)
        self.add_message_handler(
            GetChainHeigthRequest, self.on_get_chain_height_request
        )
        self.add_message_handler(GetBlockRequest, self.on_get_block_request)
        self.add_message_handler(EntireChainRequest, self.on_entire_chain_request)
        self.add_message_handler(EntireChainResponse, self.on_entire_chain_response)

    # === RESPONSE HANDLERS ===
    @lazy_wrapper(GetBlockResponse)
    def on_get_block_response(self, peer: Peer, payload: GetBlockResponse) -> None:
        print(
            f"Get Block Response from {peer}:"
            f"\n\theight={payload.height}"
            f"\n\tprev_hash={payload.prev_hash.hex()}"
            f"\n\ttxs_hash={payload.txs_hash.hex()}"
            f"\n\ttimestamp={payload.timestamp}"
            f"\n\tdifficulty={payload.difficulty}"
            f"\n\tnonce={payload.nonce}"
            f"\n\tblock_hash={payload.block_hash.hex()}"
            f"\n\ttx_hashes={payload.tx_hashes.hex()}"
        )
        block = Block()
        block.height = payload.height
        block.prev_hash = payload.prev_hash
        block.txs_hash = payload.txs_hash
        block.timestamp = payload.timestamp
        block.difficulty = payload.difficulty
        block.nonce = payload.nonce
        block.txs = []
        while len(blockchain) <= payload.height:
            blockchain.append(None)
        blockchain[payload.height] = block

    @lazy_wrapper(GetBlockRequest)
    def on_get_block_request(self, peer: Peer, payload: GetBlockRequest) -> None:
        print(f"Returning block {payload.height}")
        if payload.height < 0 or payload.height >= len(blockchain):
            return

        block = blockchain[payload.height]
        self._safe_ez_send(
            peer,
            GetBlockResponse(
                height=payload.height,
                prev_hash=block.prev_hash,
                txs_hash=block.txs_hash,
                timestamp=block.timestamp,
                difficulty=block.difficulty,
                nonce=block.nonce,
                block_hash=block.hash(),
                tx_hashes=block.get_tx_hashes(),
            ),
        )

    @lazy_wrapper(GetChainHeigthResponse)
    def on_get_chain_height_response(
        self, peer: Peer, payload: GetChainHeigthResponse
    ) -> None:
        print(
            f"Get Chain Height Response from {peer}:"
            f"\n\trequest_id={payload.request_id}"
            f"\n\theight={payload.height}"
            f"\n\ttip_hash={payload.tip_hash.hex()}"
        )

    @lazy_wrapper(GetChainHeigthRequest)
    def on_get_chain_height_request(
        self, peer: Peer, payload: GetChainHeigthRequest
    ) -> None:
        tip = blockchain[-1]
        self._safe_ez_send(
            peer,
            GetChainHeigthResponse(
                request_id=payload.request_id,
                height=len(blockchain) - 1,
                tip_hash=tip.hash(),
            ),
        )

    @lazy_wrapper(SubmitTransactionResponse)
    def on_submit_transaction_response(
        self, peer: Peer, payload: SubmitTransactionResponse
    ) -> None:
        print(
            f"Submit Transaction Response from {peer}:"
            f"\n\tsuccess={payload.success}"
            f"\n\ttx_hash={payload.tx_hash.hex()}"
            f"\n\tmessage={payload.message}"
        )

    @lazy_wrapper(SubmitTransactionRequest)
    def on_submit_transaction_request(
        self, peer: Peer, payload: SubmitTransactionRequest
    ):
        t = Transaction()
        t.sender_key = payload.sender_key
        t.data = payload.data
        t.timestamp = payload.timestamp
        t.signature = payload.signature

        success = True
        message = "Transaction accepted"

        if not t.verify_signature():
            print("Invalid signature for transaction from", peer)
            success = False
            message = "Invalid signature"

        if t in mempool:
            print("Duplicate transaction from", peer)
            success = False
            message = "Duplicate transaction (not re-added)"

        if success:
            mempool.add(t)
            print(
                f"Added transaction from {peer} to mempool. Mempool size: {len(mempool)}"
            )

        message = SubmitTransactionResponse(
            success=success,
            tx_hash=t.hash(),
            message=message,
        )
        self._safe_ez_send(peer, message)

    @lazy_wrapper(ChangedDifficultyMessage)
    def on_changed_difficulty(
        self, peer: Peer, payload: ChangedDifficultyMessage
    ) -> None:
        global difficulty
        difficulty = payload.new_difficulty
        print(f"Difficulty changed to {difficulty}")

    @lazy_wrapper(BlockAnnouncementMessage)
    async def on_block_announcement(
        self, peer: Peer, payload: BlockAnnouncementMessage
    ) -> None:
        global do_mine
        # If blockchain is short, inform other node we have a longer chain
        if payload.height < len(blockchain) - 1:
            print(
                f"Ignored block announcement from {peer} with height {payload.height} (expected {len(blockchain)})"
            )
            message = BlockAnnouncementMessage(
                height=len(blockchain) - 1,
                block=blockchain[-1].to_bytes(),
            )
            self._safe_ez_send(peer, message)
            return

        # If blockchain is long, request missing blocks
        if payload.height > len(blockchain):
            print(f"{peer} has longer chain of {payload.height}")
            peerkey = peer.public_key.key_to_bin().hex()

            # If we're already catching up from this peer, check for staleness
            if peerkey in new_chain:
                age = time.time() - new_chain[peerkey].get("ts", 0)
                if age < FETCH_TIMEOUT:
                    print(
                        f"Already catching up from {peer}; ignoring new announcement for {payload.height}"
                    )
                    return
                else:
                    print(
                        f"Fetch from {peer} stale (age={int(age)}s); restarting catch-up"
                    )
                    new_chain.pop(peerkey)

            new_chain[peerkey] = {
                "remote_tip_height": payload.height,
                "blocks": [],  # collected in reverse order (tip first)
                "common_ancestor_found": False,
                "ts": time.time(),
            }
            do_mine = False

            # request the tip first and then work backwards
            message = EntireChainRequest(request_id=0, height=payload.height)
            self._safe_ez_send(peer, message)
            print(f"Requested block {payload.height} from {peer} (working backwards)")
            return

        block = Block.from_bytes(payload.block)
        block.height = payload.height

        if not validate_block(block, blockchain[-1].hash()):
            print(
                f"Ignored invalid block announcement from {peer} with height {payload.height}"
            )
            return

        blockchain.append(block)
        for tx in block.txs:
            mempool.discard(tx)
        print(
            f"Accepted block {payload.height} from {peer}. Chain height is now {len(blockchain) - 1}"
        )

    @lazy_wrapper(EntireChainRequest)
    def on_entire_chain_request(self, peer: Peer, payload: EntireChainRequest) -> None:
        print(f"Request received for height {payload.height}")
        if payload.height < 0 or payload.height >= len(blockchain):
            message = EntireChainResponse(
                request_id=payload.request_id,
                total_height=0,
                height=0,
                block=b"",
            )
            self.ez_send(peer, message)
            return
        message = EntireChainResponse(
            request_id=payload.request_id,
            total_height=len(blockchain) - 1,
            height=payload.height,
            block=blockchain[payload.height].to_bytes(),
        )
        self._safe_ez_send(peer, message)

    @lazy_wrapper(EntireChainResponse)
    def on_entire_chain_response(
        self, peer: Peer, payload: EntireChainResponse
    ) -> None:
        global blockchain, do_mine

        if payload.total_height == 0:
            do_mine = True
            return

        peerkey = peer.public_key.key_to_bin().hex()

        if peerkey not in new_chain:
            return

        try:
            block = Block.from_bytes(payload.block)
            block.height = payload.height
            new_chain[peerkey]["blocks"].append(block)
            new_chain[peerkey]["ts"] = time.time()
        except Exception as e:
            print(f"ERROR deserializing block {payload.height}: {e}")
            import traceback

            traceback.print_exc()
            do_mine = True
            new_chain.pop(peerkey, None)
            return

        # If this block's height exists in our local chain, check for common ancestor
        if payload.height < len(blockchain):
            if block.hash() == blockchain[payload.height].hash():
                # found common ancestor at payload.height
                all_rev = list(reversed(new_chain[peerkey]["blocks"]))
                # Exclude the ancestor block itself (height == payload.height)
                fetched_blocks = [b for b in all_rev if b.height > payload.height]

                # Assign correct heights to fetched blocks (ancestor+1 .. tip)
                for i, b in enumerate(fetched_blocks):
                    b.height = payload.height + 1 + i

                # Build candidate chain: our chain up to ancestor + fetched blocks
                candidate_chain = blockchain[: payload.height + 1] + fetched_blocks
                chain_correct = self.validate_chain(candidate_chain)
                if chain_correct and len(candidate_chain) > len(blockchain):
                    blockchain = candidate_chain
                    print(
                        f"Replaced local chain with new chain from {peer} of length {len(blockchain) - 1}"
                    )
                    for i in range(len(blockchain)):
                        blockchain[i].height = i
                else:
                    print(
                        f"Rejected new chain from {peer} (valid: {chain_correct}, longer: {len(candidate_chain) > len(blockchain)})"
                    )
                do_mine = True
                new_chain.pop(peerkey, None)
                return

        # Not yet found ancestor; request previous block (height-1) if possible
        if payload.height > 0:
            message = EntireChainRequest(
                request_id=payload.request_id + 1, height=payload.height - 1
            )
            self._safe_ez_send(peer, message)
        else:
            # Reached genesis without finding common ancestor; drop fetch
            print(f"Reached block 0 without finding common ancestor with {peer}")
            new_chain.pop(peerkey)

    def _safe_ez_send(self, peer: Peer, message) -> None:
        try:
            self.ez_send(peer, message)
        except Exception as e:
            print(f"Send to {peer} failed: {e}")

    async def _broadcast_block(self, mined_block: Block) -> None:
        """Called on the event-loop thread to broadcast a freshly mined block."""
        peers = self.get_peers()
        message = BlockAnnouncementMessage(
            height=len(blockchain) - 1,
            block=mined_block.to_bytes(),
        )
        for peer in peers:
            self._safe_ez_send(peer, message)

    def _mining_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        global difficulty
        while True:
            if not do_mine:
                time.sleep(0.1)
                continue
            tip = blockchain[-1]
            txs = sorted(mempool, key=lambda tx: tx.hash())
            candidate = Block()
            candidate.prev_hash = tip.hash()
            candidate.txs = [Transaction.from_bytes(tx.to_bytes())[0] for tx in txs]
            candidate._compute_txs_hash()
            candidate.timestamp = max(
                tip.timestamp + 1,
                max((tx.timestamp for tx in txs), default=tip.timestamp + 1),
            )
            candidate.difficulty = difficulty
            candidate.nonce = 0
            candidate.height = tip.height + 1

            mined_block = mine_block(candidate)

            if blockchain[-1].hash() != tip.hash():
                continue

            blockchain.append(mined_block)
            for tx in txs:
                mempool.discard(tx)

            print(
                f"Mined block {len(blockchain) - 1} with {len(txs)} txs and difficulty {mined_block.difficulty}"
            )

            # Schedule broadcast safely back onto the asyncio event loop
            asyncio.run_coroutine_threadsafe(self._broadcast_block(mined_block), loop)

    def validate_chain(self, chain=blockchain) -> bool:
        for i in range(1, len(chain)):
            block = chain[i]
            prev_block = chain[i - 1]
            if not validate_block(block, prev_block.hash(), do_print=True):
                return False
        return chain[0].hash() == genesis_block.hash()

    # === MENU OPTIONS ===
    async def speed_mine(self) -> None:
        global difficulty
        old_difficulty = difficulty
        difficulty = 2
        loop = asyncio.get_event_loop()
        await to_thread(lambda: [self._mine_one_block(loop) for _ in range(10)])
        difficulty = old_difficulty

    async def mine_ahead(self) -> None:
        global difficulty, blockchain
        blockchain = blockchain[:-2]
        t = Transaction()
        t.sender_key = self.my_peer.key.pub().key_to_bin()
        t.data = b"Test data!"
        t.timestamp = int(time.time())
        t.signature = t.make_signature(self.my_peer.key)

        mempool.add(t)
        old_difficulty = difficulty
        difficulty = 4
        loop = asyncio.get_event_loop()
        await to_thread(self._mine_one_block, loop)
        t.timestamp += 1
        mempool.add(t)
        await to_thread(self._mine_one_block, loop)
        difficulty = old_difficulty

    def _mine_one_block(self, loop: asyncio.AbstractEventLoop) -> None:
        global difficulty
        tip = blockchain[-1]
        txs = sorted(mempool, key=lambda tx: tx.hash())
        candidate = Block()
        candidate.prev_hash = tip.hash()
        candidate.txs = [Transaction.from_bytes(tx.to_bytes())[0] for tx in txs]
        candidate._compute_txs_hash()
        candidate.timestamp = max(
            tip.timestamp + 1,
            max((tx.timestamp for tx in txs), default=tip.timestamp + 1),
        )
        candidate.difficulty = difficulty
        candidate.nonce = 0
        candidate.height = tip.height + 1

        mined_block = mine_block(candidate)

        if blockchain[-1].hash() != tip.hash():
            return

        blockchain.append(mined_block)
        for tx in txs:
            mempool.discard(tx)

        asyncio.run_coroutine_threadsafe(self._broadcast_block(mined_block), loop)

    async def change_difficulty(self) -> None:
        global difficulty
        difficulty = int(await async_input("New difficulty: "))
        print(f"Difficulty set to {difficulty}")
        for peer in self.get_peers():
            self._safe_ez_send(
                peer, ChangedDifficultyMessage(new_difficulty=difficulty)
            )

    async def submit_transaction(self) -> None:
        t = Transaction()
        t.sender_key = self.my_peer.key.pub().key_to_bin()
        # t.data = (await async_input("Data: ")).encode()
        t.data = b"Test data!"
        t.timestamp = int(time.time())
        t.signature = t.make_signature(self.my_peer.key)

        message = SubmitTransactionRequest(
            sender_key=t.sender_key,
            data=t.data,
            timestamp=t.timestamp,
            signature=t.signature,
        )
        for peer in self.get_peers():
            self._safe_ez_send(peer, message)
        mempool.add(t)

    async def find_peers(self) -> None:
        print(
            f"=== Blockchain Community Peers: {len(self.get_peers())} === {time.ctime()} ==="
        )
        for peer in self.get_peers():
            print(
                peer,
                f"...{peer.public_key.key_to_bin().hex()[-10:]}",
                (
                    " <-- SERVER"
                    if peer.public_key.key_to_bin() == SERVER_PUBLIC_KEY
                    else ""
                ),
                (
                    " <-- Aiste"
                    if peer.public_key.key_to_bin() == AISTE_PUBLIC_KEY
                    else ""
                ),
                (
                    " <-- Aykut"
                    if peer.public_key.key_to_bin() == AYKUT_PUBLIC_KEY
                    else ""
                ),
                (
                    " <-- Yurian"
                    if peer.public_key.key_to_bin() == YURIAN_PUBLIC_KEY
                    else ""
                ),
            )

    def start_mining(self) -> None:
        loop = asyncio.get_event_loop()
        t = threading.Thread(target=self._mining_loop, args=(loop,), daemon=True)
        t.start()

    # Starting function
    async def started(self) -> None:
        pass


class DelftCommunity(Community):
    community_id = SERVER_COMMUNITY_ID

    def __init__(self, settings: CommunitySettings) -> None:
        super().__init__(settings)
        self.add_message_handler(
            RegisterBlockchainResponse, self.on_register_blockchain_response
        )

    # === RESPONSE HANDLERS ===
    @lazy_wrapper(RegisterBlockchainResponse)
    def on_register_blockchain_response(
        self, peer: Peer, payload: RegisterBlockchainResponse
    ) -> None:
        print(
            f"Register Blockchain Response:"
            f"\n\tsuccess={payload.success}"
            f"\n\tmessage={payload.message}"
        )

    # === MENU OPTIONS ===
    async def register_blockchain(self) -> None:
        message = RegisterBlockchainRequest(group_id.hex(), CHAIN_COMMUNITY_ID)
        self.ez_send(server_peer, message)

    async def get_my_key(self) -> None:
        print(self.my_peer.key.pub().key_to_bin().hex())

    async def find_peers(self) -> None:
        global server_peer
        print(
            f"=== Delft Community Peers: {len(self.get_peers())} === {time.ctime()} ==="
        )
        for peer in self.get_peers():
            print(
                peer,
                f"...{peer.public_key.key_to_bin().hex()[-10:]}",
                f"{" <-- SERVER" if peer.public_key.key_to_bin() == SERVER_PUBLIC_KEY else ''}",
                f"{" <-- Aiste" if peer.public_key.key_to_bin() == AISTE_PUBLIC_KEY else ''}",
                f"{" <-- Aykut" if peer.public_key.key_to_bin() == AYKUT_PUBLIC_KEY else ''}",
                f"{" <-- Yurian" if peer.public_key.key_to_bin() == YURIAN_PUBLIC_KEY else ''}",
            )
        print("\n")

    # Starting function
    async def started(self) -> None:
        global ME_PUBLIC_KEY
        ME_PUBLIC_KEY = self.my_peer.key.pub().key_to_bin()


async def start_client() -> None:
    global server_peer, mempool
    builder = ConfigBuilder().clear_keys().clear_overlays()
    builder.add_key("client", "curve25519", f"../{keyfile}.pem")
    builder.add_overlay(
        "DelftCommunity",
        "client",
        [WalkerDefinition(Strategy.RandomWalk, 20, {"timeout": 3.0})],
        default_bootstrap_defs,
        {},
        [("started",)],
    )
    builder.add_overlay(
        "BlockchainCommunity",
        "client",
        [WalkerDefinition(Strategy.RandomWalk, 20, {"timeout": 3.0})],
        default_bootstrap_defs,
        {},
        [("started",)],
    )
    ipv8_instance = IPv8(
        builder.finalize(),
        extra_communities={
            "DelftCommunity": DelftCommunity,
            "BlockchainCommunity": BlockchainCommunity,
        },
    )
    await ipv8_instance.start()

    # Wait for community to be initialized
    delft_community = None
    blockchain_community = None
    for overlay in ipv8_instance.overlays:
        if isinstance(overlay, DelftCommunity):
            delft_community = overlay
        if isinstance(overlay, BlockchainCommunity):
            blockchain_community = overlay

    attempts = 0
    while server_peer is None:
        attempts += 1
        await sleep(1)
        for peer in delft_community.get_peers():
            if peer.public_key.key_to_bin() == SERVER_PUBLIC_KEY:
                server_peer = peer
                print(f"Found server peer: {server_peer} after {attempts} attempts")
                break
        if server_peer is None:
            print(f"{attempts} attempts: {len(delft_community.get_peers())} peers")

    blockchain_community.start_mining()

    # Main menu loop
    while True:
        print("\n")
        print("1. Get my public key")
        print("2. Find peers")
        print("3. Register Community with Server")
        print("4. Submit Transaction")
        print("5. View Mempool")
        print("6. Change Difficulty")
        print("7. View Blockchain")
        print("8. Diverge & Mine ahead (apply longer chain rule test)")
        print("9. Pause mining (30s)")
        choice = 2
        try:
            choice = int(await async_input(""))
        except:
            pass
        print("")
        match choice:
            case 1:
                await delft_community.get_my_key()
            case 2:
                await delft_community.find_peers()
                await blockchain_community.find_peers()
            case 3:
                await delft_community.register_blockchain()
            case 4:
                await blockchain_community.submit_transaction()
            case 5:
                print(f"Mempool size: {len(mempool)}")
                for tx in mempool:
                    print(f"  - {tx}")
            case 6:
                await blockchain_community.change_difficulty()
            case 7:
                print(f"Blockchain height: {len(blockchain) - 1}")
                for block in blockchain:
                    print(
                        f"Block {block.height}: "
                        f"\n\tprev_hash={block.prev_hash.hex()}, "
                        f"\n\ttxs_hash={block.txs_hash.hex()}, "
                        f"\n\ttimestamp={block.timestamp}, "
                        f"\n\tdifficulty={block.difficulty}, "
                        f"\n\tnonce={block.nonce}, "
                        f"\n\thash={block.hash().hex()}, "
                        f"\n\ttxs=[{', '.join(str(tx) for tx in block.txs)}]"
                    )
            case 8:
                await blockchain_community.mine_ahead()
            case 9:
                global do_mine
                do_mine = False
                print("Mining paused for 30 seconds...")
                await sleep(30)
                do_mine = True
                print("Mining resumed!")
            case 10:
                await blockchain_community.speed_mine()
            case 11:
                print(do_mine)
            case 12:
                blockchain_community._mine_one_block(asyncio.get_event_loop())
            case _:
                exit(0)
        await sleep(0.1)


run(start_client())
