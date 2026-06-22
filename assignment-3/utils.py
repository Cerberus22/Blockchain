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

# Extra feature: Adaptive Difficulty
TARGET_BLOCK_TIME: int = 10 # desired seconds per block
ADJUSTMENT_INTERVAL: int = 10 # recalculate difficulty every N blocks
MAX_ADJUSTMENT_FACTOR: float = 4.0 # max multiplier / divisor per adjustment window
MTP_WINDOW: int = 11 # Median Time Past: look back at most this many blocks
MAX_FUTURE_DRIFT: int = 10 # seconds a block timestamp may exceed wall-clock time

def get_median_time_past(chain: list, tip_index: int) -> int:
    """Return the median timestamp of up to MTP_WINDOW blocks ending at tip_index."""
    start = max(0, tip_index - MTP_WINDOW + 1)
    timestamps = sorted(chain[i].timestamp for i in range(start, tip_index + 1))
    return timestamps[len(timestamps) // 2]

def validate_timestamp(candidate_ts: int, chain: list, check_future: bool = True) -> bool:
    """
    Return True only when candidate_ts satisfies both rules:
      1. Strictly greater than the Median Time Past of the chain tip.
         This prevents a miner from backdating their block.
      2. No more than MAX_FUTURE_DRIFT seconds ahead of wall-clock time.
         This prevents a miner from claiming the block was mined far in the future.
         Rule 2 is skipped when check_future=False (used when replaying old chains).
    """
    if not chain:
        return True
    mtp = get_median_time_past(chain, len(chain) - 1)
    if candidate_ts <= mtp:
        return False
    if check_future and candidate_ts > int(time.time()) + MAX_FUTURE_DRIFT:
        return False
    return True

def calculate_next_difficulty(chain: list) -> int:
    """
    Clamped proportional difficulty controller.

    At every ADJUSTMENT_INTERVAL boundary (i.e. when the *next* block height
    is a multiple of ADJUSTMENT_INTERVAL) the difficulty is scaled by:

        ratio = (TARGET_BLOCK_TIME * ADJUSTMENT_INTERVAL) / actual_window_time

    actual_window_time is measured using Median Time Past at both edges of
    the window, so one miner lying about their timestamp cannot shift the
    result by more than a few seconds.

    ratio is clamped to [1/MAX_ADJUSTMENT_FACTOR, MAX_ADJUSTMENT_FACTOR] to
    prevent the controller from overshooting and oscillating when hashpower
    changes dramatically.

    Returns 0 when the chain is only the genesis block (caller should fall
    back to a configured default difficulty in that case).
    """
    tip = chain[-1]
    next_height = tip.height + 1

    # Not enough history for a full window yet
    if next_height <= ADJUSTMENT_INTERVAL:
        return tip.difficulty

    # Between adjustment boundaries: carry the current difficulty forward
    if next_height % ADJUSTMENT_INTERVAL != 0:
        return tip.difficulty

    end_idx   = len(chain) - 1
    start_idx = end_idx - ADJUSTMENT_INTERVAL
    if start_idx < 0:               # safety guard (heights out of sync)
        return tip.difficulty

    mtp_end   = get_median_time_past(chain, end_idx)
    mtp_start = get_median_time_past(chain, start_idx)

    actual_time   = max(mtp_end - mtp_start, 1)   # guard against zero / negative
    expected_time = TARGET_BLOCK_TIME * ADJUSTMENT_INTERVAL

    ratio = expected_time / actual_time
    ratio = max(1.0 / MAX_ADJUSTMENT_FACTOR, min(MAX_ADJUSTMENT_FACTOR, ratio))

    return max(1, round(tip.difficulty * ratio))
