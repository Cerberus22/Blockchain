import time
from hashlib import sha256
from ipv8.keyvault.crypto import ECCrypto

class Transaction:
    sender_key: bytes
    data: bytes
    timestamp: int
    signature: bytes

    def __init__(self):
        self.sender_key = b""
        self.data = b""
        self.timestamp = 0
        self.signature = b""

    def hash(self):
        return sha256(
            self.sender_key
            + self.data
            + self.timestamp.to_bytes(8, "big")
            + self.signature
        ).digest()

    def make_signature(self, key: bytes) -> bytes:
        self.signature = key.signature(
            self.sender_key + self.data + self.timestamp.to_bytes(8, "big")
        )
        return self.signature

    def verify_signature(self) -> bool:
        key = ECCrypto().key_from_public_bin(self.sender_key)
        try:
            success = key.verify(
                self.signature,
                self.sender_key + self.data + self.timestamp.to_bytes(8, "big"),
            )
            if success is None: return True
            return success
        except ValueError:
            return False
        return False

    def to_bytes(self) -> bytes:
        return (
            len(self.sender_key).to_bytes(2, "big")
            + self.sender_key
            + len(self.data).to_bytes(2, "big")
            + self.data
            + self.timestamp.to_bytes(8, "big")
            + len(self.signature).to_bytes(2, "big")
            + self.signature
        )

    @staticmethod
    def from_bytes(data: bytes, offset: int = 0) -> tuple["Transaction", int]:
        """Reconstruct transaction from bytes with length prefixes.
        Returns tuple of (transaction, new_offset)."""

        # Parse sender_key
        sender_key_len = int.from_bytes(data[offset : offset + 2], "big")
        offset += 2
        sender_key = data[offset : offset + sender_key_len]
        offset += sender_key_len

        # Parse data
        data_len = int.from_bytes(data[offset : offset + 2], "big")
        offset += 2
        payload_data = data[offset : offset + data_len]
        offset += data_len

        # Parse timestamp
        timestamp = int.from_bytes(data[offset : offset + 8], "big")
        offset += 8

        # Parse signature
        signature_len = int.from_bytes(data[offset : offset + 2], "big")
        offset += 2
        signature = data[offset : offset + signature_len]
        offset += signature_len

        tx = Transaction()
        tx.sender_key = sender_key
        tx.data = payload_data
        tx.timestamp = timestamp
        tx.signature = signature
        return tx, offset

    def __str__(self) -> str:
        return (
            f"Transaction("
            f"\n\tsender_key={self.sender_key.hex()}, "
            f"\n\tdata={self.data.hex()}, "
            f"\n\ttimestamp={self.timestamp}, "
            f"\n\tsignature={self.signature.hex()}"
            f"\n)"
        )

    def __repr__(self) -> str:
        return self.__str__()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Transaction):
            return False
        return self.signature == other.signature

    def __hash__(self) -> int:
        return hash(self.signature)

class Block:
    prev_hash: bytes
    txs_hash: bytes
    timestamp: int
    difficulty: int
    nonce: int
    txs: list[Transaction]

    height: int

    def __init__(self):
        self.txs = []
        self.timestamp = int(time.time())

    def genesis(self):
        self.prev_hash = b"\0" * 32
        self.timestamp = 0
        self.difficulty = 0
        self.nonce = 0
        self.txs = []
        self._compute_txs_hash()
        self.height = 0
        return self

    def hash(self) -> bytes:
        return sha256(
            self.prev_hash.rjust(32, b"\0")
            + self.txs_hash.rjust(32, b"\0")
            + self.timestamp.to_bytes(8, "big")
            + self.difficulty.to_bytes(4, "big")
            + self.nonce.to_bytes(8, "big")
        ).digest()

    def add_tx(self, tx: Transaction) -> None:
        self.txs.append(tx)
        self._compute_txs_hash()

    def get_tx_hashes(self) -> bytes:
        return b"".join(tx.hash() for tx in self.txs)

    def _compute_txs_hash(self) -> bytes:
        self.txs_hash = sha256(self.get_tx_hashes()).digest()

    def to_bytes(self) -> bytes:
        block_bytes = (
            self.prev_hash.rjust(32, b"\0")
            + self.txs_hash.rjust(32, b"\0")
            + self.timestamp.to_bytes(8, "big")
            + self.difficulty.to_bytes(4, "big")
            + self.nonce.to_bytes(8, "big")
        )

        block_bytes += len(self.txs).to_bytes(2, "big")

        for tx in self.txs:
            block_bytes += tx.to_bytes()

        return block_bytes

    @staticmethod
    def from_bytes(data: bytes) -> "Block":
        offset = 0

        # Parse header (fixed size)
        prev_hash = data[offset : offset + 32]
        offset += 32

        txs_hash = data[offset : offset + 32]
        offset += 32

        timestamp = int.from_bytes(data[offset : offset + 8], "big")
        offset += 8

        difficulty = int.from_bytes(data[offset : offset + 4], "big")
        offset += 4

        nonce = int.from_bytes(data[offset : offset + 8], "big")
        offset += 8

        # Parse number of transactions
        tx_count = int.from_bytes(data[offset : offset + 2], "big")
        offset += 2

        # Parse each transaction
        txs = []
        for _ in range(tx_count):
            tx, offset = Transaction.from_bytes(data, offset)
            txs.append(tx)

        block = Block()
        block.prev_hash = prev_hash
        block.txs_hash = txs_hash
        block.timestamp = timestamp
        block.difficulty = difficulty
        block.nonce = nonce
        block.txs = txs
        return block

    def __str__(self) -> str:
        return (
            f"Block("
            f"\n\tprev_hash={self.prev_hash.hex()}, "
            f"\n\ttxs_hash={self.txs_hash.hex()}, "
            f"\n\ttimestamp={self.timestamp}, "
            f"\n\tdifficulty={self.difficulty}, "
            f"\n\tnonce={self.nonce}, "
            f"\n\ttxs_count={len(self.txs)}"
            f"\n)"
        )
