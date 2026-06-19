"""
Entry point for the blockchain client.

Usage:
    python main.py <keyfile>

Where <keyfile> is one of: aiste, aykut, yurian  (without the .pem extension).
The corresponding key file must exist at ../private_keys/<keyfile>.pem
"""

import sys
import asyncio
from asyncio import run, sleep

import state
from constants import SERVER_PUBLIC_KEY
from utils import async_input
from blockchain_community import BlockchainCommunity
from delft_community import DelftCommunity

from ipv8_service import IPv8
from ipv8.configuration import ConfigBuilder, Strategy, WalkerDefinition, default_bootstrap_defs


keyfile = f"../private_keys/{sys.argv[1]}" if len(sys.argv) > 1 else "../private_keys/yurian"

async def start_client() -> None:
    builder = ConfigBuilder().clear_keys().clear_overlays()
    builder.add_key("client", "curve25519", f"{keyfile}.pem")
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

    # Resolve overlay references
    delft_community = None
    blockchain_community = None
    for overlay in ipv8_instance.overlays:
        if isinstance(overlay, DelftCommunity):
            delft_community = overlay
        if isinstance(overlay, BlockchainCommunity):
            blockchain_community = overlay

    # Wait until the server peer is discovered
    attempts = 0
    while state.server_peer is None:
        attempts += 1
        await sleep(1)
        for peer in delft_community.get_peers():
            if peer.public_key.key_to_bin() == SERVER_PUBLIC_KEY:
                state.server_peer = peer
                print(f"Found server peer: {state.server_peer} after {attempts} attempts")
                break
        if state.server_peer is None:
            print(f"{attempts} attempts: {len(delft_community.get_peers())} peers")

    blockchain_community.start_mining()

    while True:
        print("\n")
        print("1.  Get my public key")
        print("2.  Find peers")
        print("3.  Register community with server")
        print("4.  Submit transaction")
        print("5.  View mempool")
        print("6.  Change difficulty")
        print("7.  View blockchain")
        print("8.  Diverge & mine ahead (longer-chain rule test)")
        print("9.  Pause mining (30 s)")
        print("10. Speed-mine 10 blocks (difficulty 2)")
        print("11. Show do_mine flag")
        print("12. Mine one block manually")
        print("0.  Exit")

        choice = 2
        try:
            choice = int(await async_input(""))
        except Exception:
            pass

        print()
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
                print(f"Mempool size: {len(state.mempool)}")
                for tx in state.mempool:
                    print(f"  - {tx}")
            case 6:
                await blockchain_community.change_difficulty()
            case 7:
                print(f"Blockchain height: {len(state.blockchain) - 1}")
                for block in state.blockchain:
                    print(
                        f"Block {block.height}:"
                        f"\n\tprev_hash={block.prev_hash.hex()}"
                        f"\n\ttxs_hash={block.txs_hash.hex()}"
                        f"\n\ttimestamp={block.timestamp}"
                        f"\n\tdifficulty={block.difficulty}"
                        f"\n\tnonce={block.nonce}"
                        f"\n\thash={block.hash().hex()}"
                        f"\n\ttxs=[{', '.join(str(tx) for tx in block.txs)}]"
                    )
            case 8:
                await blockchain_community.mine_ahead()
            case 9:
                state.do_mine = False
                print("Mining paused for 30 seconds...")
                await sleep(30)
                state.do_mine = True
                print("Mining resumed!")
            case 10:
                await blockchain_community.speed_mine()
            case 11:
                print(state.do_mine)
            case 12:
                blockchain_community._mine_one_block(asyncio.get_event_loop())
            case _:
                sys.exit(0)

        await sleep(0.1)


run(start_client())
