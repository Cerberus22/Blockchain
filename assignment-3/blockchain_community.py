import time
import asyncio
import threading

import state
from messages import (
    SubmitTransactionRequest,
    SubmitTransactionResponse,
    GetBlockRequest,
    GetBlockResponse,
    GetChainHeigthRequest,
    GetChainHeigthResponse,
    BlockAnnouncementMessage,
    ChangedDifficultyMessage,
    EntireChainRequest,
    EntireChainResponse,
)
from custom_types import Block, Transaction
from constants import (
    SERVER_PUBLIC_KEY,
    AISTE_PUBLIC_KEY,
    AYKUT_PUBLIC_KEY,
    YURIAN_PUBLIC_KEY,
    CHAIN_COMMUNITY_ID,
)
from utils import validate_block, mine_block, async_input

from ipv8.peer import Peer
from ipv8.community import Community, CommunitySettings
from ipv8.lazy_community import lazy_wrapper
from asyncio import to_thread


class BlockchainCommunity(Community):
    community_id = CHAIN_COMMUNITY_ID

    def __init__(self, settings: CommunitySettings) -> None:
        super().__init__(settings)
        self.add_message_handler(SubmitTransactionRequest, self.on_submit_transaction_request)
        self.add_message_handler(SubmitTransactionResponse, self.on_submit_transaction_response)
        self.add_message_handler(GetBlockResponse, self.on_get_block_response)
        self.add_message_handler(GetChainHeigthResponse, self.on_get_chain_height_response)
        self.add_message_handler(BlockAnnouncementMessage, self.on_block_announcement)
        self.add_message_handler(ChangedDifficultyMessage, self.on_changed_difficulty)
        self.add_message_handler(GetChainHeigthRequest, self.on_get_chain_height_request)
        self.add_message_handler(GetBlockRequest, self.on_get_block_request)
        self.add_message_handler(EntireChainRequest, self.on_entire_chain_request)
        self.add_message_handler(EntireChainResponse, self.on_entire_chain_response)

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
        while len(state.blockchain) <= payload.height:
            state.blockchain.append(None)
        state.blockchain[payload.height] = block

    @lazy_wrapper(GetBlockRequest)
    def on_get_block_request(self, peer: Peer, payload: GetBlockRequest) -> None:
        print(f"Returning block {payload.height}")
        if payload.height < 0 or payload.height >= len(state.blockchain):
            return
        block = state.blockchain[payload.height]
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
    def on_get_chain_height_response(self, peer: Peer, payload: GetChainHeigthResponse) -> None:
        print(
            f"Get Chain Height Response from {peer}:"
            f"\n\trequest_id={payload.request_id}"
            f"\n\theight={payload.height}"
            f"\n\ttip_hash={payload.tip_hash.hex()}"
        )

    @lazy_wrapper(GetChainHeigthRequest)
    def on_get_chain_height_request(self, peer: Peer, payload: GetChainHeigthRequest) -> None:
        tip = state.blockchain[-1]
        self._safe_ez_send(
            peer,
            GetChainHeigthResponse(
                request_id=payload.request_id,
                height=len(state.blockchain) - 1,
                tip_hash=tip.hash(),
            ),
        )

    @lazy_wrapper(SubmitTransactionResponse)
    def on_submit_transaction_response(self, peer: Peer, payload: SubmitTransactionResponse) -> None:
        print(
            f"Submit Transaction Response from {peer}:"
            f"\n\tsuccess={payload.success}"
            f"\n\ttx_hash={payload.tx_hash.hex()}"
            f"\n\tmessage={payload.message}"
        )

    @lazy_wrapper(SubmitTransactionRequest)
    def on_submit_transaction_request(self, peer: Peer, payload: SubmitTransactionRequest):
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

        if t in state.mempool:
            print("Duplicate transaction from", peer)
            success = False
            message = "Duplicate transaction (not re-added)"

        if success:
            state.mempool.add(t)
            print(f"Added transaction from {peer} to mempool. Mempool size: {len(state.mempool)}")

        self._safe_ez_send(peer, SubmitTransactionResponse(success=success, tx_hash=t.hash(), message=message))

    @lazy_wrapper(ChangedDifficultyMessage)
    def on_changed_difficulty(self, peer: Peer, payload: ChangedDifficultyMessage) -> None:
        state.difficulty = payload.new_difficulty
        print(f"Difficulty changed to {state.difficulty}")

    @lazy_wrapper(BlockAnnouncementMessage)
    async def on_block_announcement(self, peer: Peer, payload: BlockAnnouncementMessage) -> None:
        # Our chain is longer — inform the peer
        if payload.height < len(state.blockchain) - 1:
            print(
                f"Ignored block announcement from {peer} with height {payload.height} "
                f"(expected {len(state.blockchain)})"
            )
            self._safe_ez_send(
                peer,
                BlockAnnouncementMessage(height=len(state.blockchain) - 1, block=state.blockchain[-1].to_bytes()),
            )
            return

        # Peer has a longer chain — start catch-up
        if payload.height > len(state.blockchain):
            print(f"{peer} has longer chain of {payload.height}")
            peerkey = peer.public_key.key_to_bin().hex()

            if peerkey in state.new_chain:
                age = time.time() - state.new_chain[peerkey].get("ts", 0)
                if age < state.FETCH_TIMEOUT:
                    print(f"Already catching up from {peer}; ignoring new announcement for {payload.height}")
                    return
                else:
                    print(f"Fetch from {peer} stale (age={int(age)}s); restarting catch-up")
                    state.new_chain.pop(peerkey)

            state.new_chain[peerkey] = {
                "remote_tip_height": payload.height,
                "blocks": [],
                "common_ancestor_found": False,
                "ts": time.time(),
            }
            state.do_mine = False
            self._safe_ez_send(peer, EntireChainRequest(request_id=0, height=payload.height))
            print(f"Requested block {payload.height} from {peer} (working backwards)")
            return

        # Peer is at the same height +1 — try to accept
        block = Block.from_bytes(payload.block)
        block.height = payload.height

        if not validate_block(block, state.blockchain[-1].hash()):
            print(f"Ignored invalid block announcement from {peer} with height {payload.height}")
            return

        state.blockchain.append(block)
        for tx in block.txs:
            state.mempool.discard(tx)
        print(f"Accepted block {payload.height} from {peer}. Chain height is now {len(state.blockchain) - 1}")

    @lazy_wrapper(EntireChainRequest)
    def on_entire_chain_request(self, peer: Peer, payload: EntireChainRequest) -> None:
        print(f"Request received for height {payload.height}")
        if payload.height < 0 or payload.height >= len(state.blockchain):
            self.ez_send(peer, EntireChainResponse(request_id=payload.request_id, total_height=0, height=0, block=b""))
            return
        self._safe_ez_send(
            peer,
            EntireChainResponse(
                request_id=payload.request_id,
                total_height=len(state.blockchain) - 1,
                height=payload.height,
                block=state.blockchain[payload.height].to_bytes(),
            ),
        )

    @lazy_wrapper(EntireChainResponse)
    def on_entire_chain_response(self, peer: Peer, payload: EntireChainResponse) -> None:
        if payload.total_height == 0:
            state.do_mine = True
            return

        peerkey = peer.public_key.key_to_bin().hex()
        if peerkey not in state.new_chain:
            return

        try:
            block = Block.from_bytes(payload.block)
            block.height = payload.height
            state.new_chain[peerkey]["blocks"].append(block)
            state.new_chain[peerkey]["ts"] = time.time()
        except Exception as e:
            import traceback
            print(f"ERROR deserializing block {payload.height}: {e}")
            traceback.print_exc()
            state.do_mine = True
            state.new_chain.pop(peerkey, None)
            return

        # Check for a common ancestor
        if payload.height < len(state.blockchain):
            if block.hash() == state.blockchain[payload.height].hash():
                all_rev = list(reversed(state.new_chain[peerkey]["blocks"]))
                fetched_blocks = [b for b in all_rev if b.height > payload.height]
                for i, b in enumerate(fetched_blocks):
                    b.height = payload.height + 1 + i

                candidate_chain = state.blockchain[: payload.height + 1] + fetched_blocks
                chain_correct = self.validate_chain(candidate_chain)
                if chain_correct and len(candidate_chain) > len(state.blockchain):
                    state.blockchain = candidate_chain
                    print(f"Replaced local chain with new chain from {peer} of length {len(state.blockchain) - 1}")
                    for i in range(len(state.blockchain)):
                        state.blockchain[i].height = i
                else:
                    print(
                        f"Rejected new chain from {peer} "
                        f"(valid: {chain_correct}, longer: {len(candidate_chain) > len(state.blockchain)})"
                    )
                state.do_mine = True
                state.new_chain.pop(peerkey, None)
                return

        if payload.height > 0:
            self._safe_ez_send(peer, EntireChainRequest(request_id=payload.request_id + 1, height=payload.height - 1))
        else:
            print(f"Reached block 0 without finding common ancestor with {peer}")
            state.new_chain.pop(peerkey)

    def _mining_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        while True:
            if not state.do_mine:
                time.sleep(0.1)
                continue
            tip = state.blockchain[-1]
            txs = sorted(state.mempool, key=lambda tx: tx.hash())
            candidate = Block()
            candidate.prev_hash = tip.hash()
            candidate.txs = [Transaction.from_bytes(tx.to_bytes())[0] for tx in txs]
            candidate._compute_txs_hash()
            candidate.timestamp = max(
                tip.timestamp + 1,
                max((tx.timestamp for tx in txs), default=tip.timestamp + 1),
            )
            candidate.difficulty = state.difficulty
            candidate.nonce = 0
            candidate.height = tip.height + 1

            mined_block = mine_block(candidate)

            if state.blockchain[-1].hash() != tip.hash():
                continue  # chain changed while we were mining; discard

            state.blockchain.append(mined_block)
            for tx in txs:
                state.mempool.discard(tx)

            print(f"Mined block {len(state.blockchain) - 1} with {len(txs)} txs and difficulty {mined_block.difficulty}")
            asyncio.run_coroutine_threadsafe(self._broadcast_block(mined_block), loop)

    def _mine_one_block(self, loop: asyncio.AbstractEventLoop) -> None:
        tip = state.blockchain[-1]
        txs = sorted(state.mempool, key=lambda tx: tx.hash())
        candidate = Block()
        candidate.prev_hash = tip.hash()
        candidate.txs = [Transaction.from_bytes(tx.to_bytes())[0] for tx in txs]
        candidate._compute_txs_hash()
        candidate.timestamp = max(
            tip.timestamp + 1,
            max((tx.timestamp for tx in txs), default=tip.timestamp + 1),
        )
        candidate.difficulty = state.difficulty
        candidate.nonce = 0
        candidate.height = tip.height + 1

        mined_block = mine_block(candidate)

        if state.blockchain[-1].hash() != tip.hash():
            return

        state.blockchain.append(mined_block)
        for tx in txs:
            state.mempool.discard(tx)

        asyncio.run_coroutine_threadsafe(self._broadcast_block(mined_block), loop)

    async def _broadcast_block(self, mined_block: Block) -> None:
        peers = self.get_peers()
        message = BlockAnnouncementMessage(
            height=len(state.blockchain) - 1,
            block=mined_block.to_bytes(),
        )
        for peer in peers:
            self._safe_ez_send(peer, message)

    def start_mining(self) -> None:
        loop = asyncio.get_event_loop()
        t = threading.Thread(target=self._mining_loop, args=(loop,), daemon=True)
        t.start()

    async def find_peers(self) -> None:
        print(f"=== Blockchain Community Peers: {len(self.get_peers())} === {time.ctime()} ===")
        for peer in self.get_peers():
            print(
                peer,
                f"...{peer.public_key.key_to_bin().hex()[-10:]}",
                " <-- SERVER" if peer.public_key.key_to_bin() == SERVER_PUBLIC_KEY else "",
                " <-- Aiste" if peer.public_key.key_to_bin() == AISTE_PUBLIC_KEY else "",
                " <-- Aykut" if peer.public_key.key_to_bin() == AYKUT_PUBLIC_KEY else "",
                " <-- Yurian" if peer.public_key.key_to_bin() == YURIAN_PUBLIC_KEY else "",
            )

    async def submit_transaction(self) -> None:
        t = Transaction()
        t.sender_key = self.my_peer.key.pub().key_to_bin()
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
        state.mempool.add(t)

    async def change_difficulty(self) -> None:
        state.difficulty = int(await async_input("New difficulty: "))
        print(f"Difficulty set to {state.difficulty}")
        for peer in self.get_peers():
            self._safe_ez_send(peer, ChangedDifficultyMessage(new_difficulty=state.difficulty))

    async def speed_mine(self) -> None:
        old_difficulty = state.difficulty
        state.difficulty = 2
        loop = asyncio.get_event_loop()
        await to_thread(lambda: [self._mine_one_block(loop) for _ in range(10)])
        state.difficulty = old_difficulty

    async def mine_ahead(self) -> None:
        """Remove last 2 blocks and mine 2 fresh ones to test the longer-chain rule."""
        state.blockchain = state.blockchain[:-2]
        t = Transaction()
        t.sender_key = self.my_peer.key.pub().key_to_bin()
        t.data = b"Test data!"
        t.timestamp = int(time.time())
        t.signature = t.make_signature(self.my_peer.key)

        state.mempool.add(t)
        old_difficulty = state.difficulty
        state.difficulty = 4
        loop = asyncio.get_event_loop()
        await to_thread(self._mine_one_block, loop)
        t.timestamp += 1
        state.mempool.add(t)
        await to_thread(self._mine_one_block, loop)
        state.difficulty = old_difficulty

    def validate_chain(self, chain=None) -> bool:
        if chain is None:
            chain = state.blockchain
        for i in range(1, len(chain)):
            if not validate_block(chain[i], chain[i - 1].hash(), do_print=True):
                return False
        return chain[0].hash() == state.genesis_block.hash()

    def _safe_ez_send(self, peer: Peer, message) -> None:
        try:
            self.ez_send(peer, message)
        except Exception as e:
            print(f"Send to {peer} failed: {e}")

    async def started(self) -> None:
        pass
