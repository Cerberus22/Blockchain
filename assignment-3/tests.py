from hashlib import sha256
from custom_types import Block, Transaction
from utils import validate_block, mine_block, leading_zero_bits
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
