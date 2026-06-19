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

        time.sleep(0)
