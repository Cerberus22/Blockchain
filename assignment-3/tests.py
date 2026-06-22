from hashlib import sha256
from custom_types import Block, Transaction
from utils import (
    validate_block, mine_block, leading_zero_bits,
    validate_timestamp, calculate_next_difficulty, get_median_time_past,
    ADJUSTMENT_INTERVAL, TARGET_BLOCK_TIME, MAX_ADJUSTMENT_FACTOR, MAX_FUTURE_DRIFT,
)
from ipv8.keyvault.crypto import ECCrypto


def test_hashing_block_is_deterministic():
    block = Block()
    block.prev_hash = b"\x00" * 32
    block.txs_hash = b"\x00" * 32
    block.timestamp = 0
    block.difficulty = 0
    block.nonce = 0
    assert block.hash() == block.hash()


def test_empty_block_txs_hash():
    block = Block()
    block.txs = []
    block._compute_txs_hash()
    assert block.txs_hash == sha256(b"").digest()


def test_nonempty_block_txs_hash():
    key = ECCrypto().generate_key("curve25519")
    tx = Transaction()
    tx.sender_key = key.pub().key_to_bin()
    tx.data = b"hello"
    tx.timestamp = 1000
    tx.make_signature(key)

    block = Block()
    block.txs = [tx]
    block._compute_txs_hash()
    assert block.txs_hash == sha256(tx.hash()).digest()


def test_two_tx_block_txs_hash():
    key = ECCrypto().generate_key("curve25519")

    tx1 = Transaction()
    tx1.sender_key = key.pub().key_to_bin()
    tx1.data = b"first"
    tx1.timestamp = 1000
    tx1.make_signature(key)

    tx2 = Transaction()
    tx2.sender_key = key.pub().key_to_bin()
    tx2.data = b"second"
    tx2.timestamp = 1001
    tx2.make_signature(key)

    block = Block()
    block.txs = [tx1, tx2]
    block._compute_txs_hash()
    assert block.txs_hash == sha256(tx1.hash() + tx2.hash()).digest()


def test_genesis_block_structure():
    genesis = Block().genesis()
    assert genesis.prev_hash == b"\x00" * 32
    assert genesis.timestamp == 0
    assert genesis.difficulty == 0
    assert genesis.nonce == 0
    assert genesis.txs == []
    assert genesis.txs_hash == sha256(b"").digest()
    assert genesis.height == 0


def test_block_serialization_roundtrip():
    genesis = Block().genesis()
    block = Block()
    block.prev_hash = genesis.hash()
    block.txs = []
    block._compute_txs_hash()
    block.timestamp = 1
    block.difficulty = 2
    block.nonce = 0
    block.height = 1
    block = mine_block(block)

    recovered = Block.from_bytes(block.to_bytes())
    assert recovered.hash() == block.hash()
    assert recovered.prev_hash == block.prev_hash
    assert recovered.txs_hash == block.txs_hash
    assert recovered.timestamp == block.timestamp
    assert recovered.difficulty == block.difficulty
    assert recovered.nonce == block.nonce


def test_block_with_tx_serialization_roundtrip():
    key = ECCrypto().generate_key("curve25519")
    tx = Transaction()
    tx.sender_key = key.pub().key_to_bin()
    tx.data = b"roundtrip tx"
    tx.timestamp = 5000
    tx.make_signature(key)

    genesis = Block().genesis()
    block = Block()
    block.prev_hash = genesis.hash()
    block.txs = [tx]
    block._compute_txs_hash()
    block.timestamp = 1
    block.difficulty = 2
    block.nonce = 0
    block.height = 1
    block = mine_block(block)

    recovered = Block.from_bytes(block.to_bytes())
    assert recovered.hash() == block.hash()
    assert len(recovered.txs) == 1
    assert recovered.txs[0].hash() == tx.hash()


def test_transaction_hash_is_deterministic():
    key = ECCrypto().generate_key("curve25519")
    tx = Transaction()
    tx.sender_key = key.pub().key_to_bin()
    tx.data = b"test"
    tx.timestamp = 5000
    tx.make_signature(key)
    assert tx.hash() == tx.hash()


def test_transaction_signature_verifies():
    key = ECCrypto().generate_key("curve25519")
    tx = Transaction()
    tx.sender_key = key.pub().key_to_bin()
    tx.data = b"test data"
    tx.timestamp = 12345
    tx.make_signature(key)
    assert tx.verify_signature() is True


def test_tampered_data_fails_verification():
    key = ECCrypto().generate_key("curve25519")
    tx = Transaction()
    tx.sender_key = key.pub().key_to_bin()
    tx.data = b"test data"
    tx.timestamp = 12345
    tx.make_signature(key)
    tx.data = b"hacked"
    assert tx.verify_signature() is False


def test_tampered_timestamp_fails_verification():
    key = ECCrypto().generate_key("curve25519")
    tx = Transaction()
    tx.sender_key = key.pub().key_to_bin()
    tx.data = b"test data"
    tx.timestamp = 12345
    tx.make_signature(key)
    tx.timestamp = 99999
    assert tx.verify_signature() is False


def test_transaction_serialization_roundtrip():
    key = ECCrypto().generate_key("curve25519")
    tx = Transaction()
    tx.sender_key = key.pub().key_to_bin()
    tx.data = b"round trip"
    tx.timestamp = 99999
    tx.make_signature(key)

    recovered, _ = Transaction.from_bytes(tx.to_bytes())
    assert recovered.sender_key == tx.sender_key
    assert recovered.data == tx.data
    assert recovered.timestamp == tx.timestamp
    assert recovered.signature == tx.signature
    assert recovered.hash() == tx.hash()


def test_mine_block_satisfies_difficulty():
    genesis = Block().genesis()
    candidate = Block()
    candidate.prev_hash = genesis.hash()
    candidate.txs = []
    candidate._compute_txs_hash()
    candidate.timestamp = 1
    candidate.difficulty = 8
    candidate.nonce = 0
    candidate.height = 1

    mined = mine_block(candidate)
    assert leading_zero_bits(mined.hash()) >= 8


def test_validate_block_accepts_valid_block():
    genesis = Block().genesis()
    block = Block()
    block.prev_hash = genesis.hash()
    block.txs = []
    block._compute_txs_hash()
    block.timestamp = 1
    block.difficulty = 4
    block.nonce = 0
    block.height = 1
    block = mine_block(block)

    assert validate_block(block, genesis.hash()) is True


def test_validate_block_rejects_wrong_prev_hash():
    genesis = Block().genesis()
    block = Block()
    block.prev_hash = genesis.hash()
    block.txs = []
    block._compute_txs_hash()
    block.timestamp = 1
    block.difficulty = 4
    block.nonce = 0
    block.height = 1
    block = mine_block(block)

    assert validate_block(block, b"\xff" * 32) is False


def test_validate_block_rejects_wrong_txs_hash():
    genesis = Block().genesis()
    block = Block()
    block.prev_hash = genesis.hash()
    block.txs = []
    block._compute_txs_hash()
    block.timestamp = 1
    block.difficulty = 4
    block.nonce = 0
    block.height = 1
    block = mine_block(block)

    block.txs_hash = b"\xff" * 32
    assert validate_block(block, genesis.hash()) is False


def test_validate_block_rejects_insufficient_pow():
    genesis = Block().genesis()
    block = Block()
    block.prev_hash = genesis.hash()
    block.txs = []
    block._compute_txs_hash()
    block.timestamp = 1
    block.difficulty = 20
    block.nonce = 0
    block.height = 1

    assert validate_block(block, genesis.hash()) is False


def test_chain_of_three_blocks_links_correctly():
    genesis = Block().genesis()

    block1 = Block()
    block1.prev_hash = genesis.hash()
    block1.txs = []
    block1._compute_txs_hash()
    block1.timestamp = 1
    block1.difficulty = 2
    block1.nonce = 0
    block1.height = 1
    block1 = mine_block(block1)

    block2 = Block()
    block2.prev_hash = block1.hash()
    block2.txs = []
    block2._compute_txs_hash()
    block2.timestamp = 2
    block2.difficulty = 2
    block2.nonce = 0
    block2.height = 2
    block2 = mine_block(block2)

    chain = [genesis, block1, block2]
    for i in range(1, len(chain)):
        assert validate_block(chain[i], chain[i - 1].hash()) is True


def test_broken_chain_link_fails():
    genesis = Block().genesis()

    block1 = Block()
    block1.prev_hash = genesis.hash()
    block1.txs = []
    block1._compute_txs_hash()
    block1.timestamp = 1
    block1.difficulty = 2
    block1.nonce = 0
    block1.height = 1
    block1 = mine_block(block1)

    block2 = Block()
    block2.prev_hash = b"\x00" * 32  # should be block1.hash()
    block2.txs = []
    block2._compute_txs_hash()
    block2.timestamp = 2
    block2.difficulty = 2
    block2.nonce = 0
    block2.height = 2
    block2 = mine_block(block2)

    assert validate_block(block2, block1.hash()) is False


# helpertje for adaptive-difficulty tests

def _make_fake_chain(timestamps: list, difficulty: int = 20) -> list:
    """Build a list of Block objects with given timestamps (index 0 = genesis).
    Blocks are NOT proof-of-work valid — only structure and timestamps matter
    for the adaptive-difficulty tests."""
    chain = []
    prev_hash = b"\x00" * 32
    for i, ts in enumerate(timestamps):
        b = Block()
        b.height = i
        b.timestamp = ts
        b.difficulty = difficulty
        b.prev_hash = prev_hash
        b.txs = []
        b._compute_txs_hash()
        b.nonce = 0
        chain.append(b)
        prev_hash = b.hash()
    return chain


# Median Time Past

def test_mtp_returns_median_of_full_window():
    # 12 blocks, tip at index 11; MTP_WINDOW=11 -> indices 1..11
    # timestamps 1..11 sorted -> median at index 5 = 6
    chain = _make_fake_chain(list(range(12)))
    assert get_median_time_past(chain, 11) == 6


def test_mtp_short_chain_uses_all_available_blocks():
    # Only 3 blocks; all three are used
    chain = _make_fake_chain([0, 5, 10])
    # sorted [0, 5, 10], median index 1 = 5
    assert get_median_time_past(chain, 2) == 5


def test_mtp_single_block():
    chain = _make_fake_chain([42])
    assert get_median_time_past(chain, 0) == 42


# validate_timestamp

def test_validate_timestamp_accepts_value_above_mtp():
    # MTP of [0,10,20,30,40,50,60,70,80,90,100] = median of all 11 = 50
    chain = _make_fake_chain(list(range(0, 110, 10)))
    mtp = get_median_time_past(chain, len(chain) - 1)
    assert validate_timestamp(mtp + 1, chain, check_future=False) is True


def test_validate_timestamp_rejects_value_equal_to_mtp():
    chain = _make_fake_chain(list(range(0, 110, 10)))
    mtp = get_median_time_past(chain, len(chain) - 1)
    assert validate_timestamp(mtp, chain, check_future=False) is False


def test_validate_timestamp_rejects_value_below_mtp():
    chain = _make_fake_chain(list(range(0, 110, 10)))
    mtp = get_median_time_past(chain, len(chain) - 1)
    assert validate_timestamp(mtp - 5, chain, check_future=False) is False


def test_validate_timestamp_rejects_far_future():
    import time
    chain = _make_fake_chain([0, 1, 2])
    far_future = int(time.time()) + MAX_FUTURE_DRIFT + 100
    assert validate_timestamp(far_future, chain, check_future=True) is False


def test_validate_timestamp_accepts_near_future():
    import time
    chain = _make_fake_chain([0, 1, 2])
    # MAX_FUTURE_DRIFT - 1 seconds from now is within the allowed window
    near_future = int(time.time()) + MAX_FUTURE_DRIFT - 1
    assert validate_timestamp(near_future, chain, check_future=True) is True


def test_validate_timestamp_empty_chain_always_passes():
    assert validate_timestamp(12345, [], check_future=False) is True


# calculate_next_difficulty

def test_difficulty_unchanged_before_first_interval():
    # Only genesis + 1 block -> not enough history
    chain = _make_fake_chain([0, 10], difficulty=20)
    assert calculate_next_difficulty(chain) == 20


def test_difficulty_unchanged_between_boundaries():
    # 12 blocks (heights 0-11), next_height=12, 12 % 10 = 2 -> no adjustment yet
    chain = _make_fake_chain(list(range(0, 120, 10)), difficulty=20)
    assert calculate_next_difficulty(chain) == 20


def test_difficulty_increases_when_blocks_are_too_fast():
    # 20 blocks, 1 s apart (target is 10 s) -> blocks too fast -> raise difficulty
    # next_height = 20, 20 % 10 = 0, len=20 > 10 -> adjustment fires
    chain = _make_fake_chain(list(range(20)), difficulty=20)
    assert calculate_next_difficulty(chain) > 20


def test_difficulty_decreases_when_blocks_are_too_slow():
    # 20 blocks, 1000 s apart (target is 10 s) -> blocks too slow -> lower difficulty
    chain = _make_fake_chain(list(range(0, 20000, 1000)), difficulty=20)
    assert calculate_next_difficulty(chain) < 20


def test_difficulty_unchanged_at_target_rate():
    # 20 blocks exactly TARGET_BLOCK_TIME apart.
    # MTP measures time between the *medians* of two overlapping windows, so the
    # apparent window duration is slightly shorter than the real one even when
    # blocks are perfectly on-time (by approx 10 %).  Allow up to +-3 difficulty units.
    step = TARGET_BLOCK_TIME
    chain = _make_fake_chain(list(range(0, 20 * step, step)), difficulty=20)
    result = calculate_next_difficulty(chain)
    assert abs(result - 20) <= 3


def test_difficulty_clamped_at_max_when_blocks_extremely_fast():
    # 1 s blocks -> raw ratio ≈ 10 -> clamped to MAX_ADJUSTMENT_FACTOR
    chain = _make_fake_chain(list(range(20)), difficulty=20)
    result = calculate_next_difficulty(chain)
    assert result <= round(20 * MAX_ADJUSTMENT_FACTOR)


def test_difficulty_clamped_at_min_when_blocks_extremely_slow():
    # 1000 s blocks -> raw ratio approx 0.01 -> clamped to 1/MAX_ADJUSTMENT_FACTOR
    chain = _make_fake_chain(list(range(0, 20000, 1000)), difficulty=20)
    result = calculate_next_difficulty(chain)
    assert result >= round(20 / MAX_ADJUSTMENT_FACTOR)
