# Assignment 3
We have implemented a peer-to-peer blockchain client on top of py-ipv8 where we provide the functionality to register with a grading server, mine PoW blocks, propagate them across a 3-node network and converge on a single consistent chain. Each group member runs one node and together the nodes form a blockchain community where blocks are mined, transactions are signed and gossiped, and the longest-chain rule is applied to ensure consistency whenever a peer gets ahead.

When a new block arrives it is validated by checking that the PoW satisfies the declared difficulty, that `prev_hash` links cleanly to the previous block, that `txs_hash` matches the body and that the block's height is greater than or equal to the current tip before deciding to append, fork-switch or ignore. Moreover, blocks do not require transactions - empty blocks are valid and are mined continuously so the chain always grows. Any transactions that exist in the mempool are bundled in, thus the mining never stalls waiting for them. When a node mines a block it broadcasts a `BlockAnnouncementMessage` to all peers. If a peer sees an announced chain height greater than its own it pauses mining, walks backwards through the peer's chain to find the common ancestor, validates the entire candidate fork and switches to it if it is longer (this is the longest-chain rule). Transactions are gossiped separately via `SubmitTransactionRequest` and each one carries a signature so receivers can verify authenticity before adding it to their mempool.

# How to run

Install `py-ipv8`:

```bash
pip install pyipv8
```

All private key files are looked up at `../private_keys/<name>.pem`. Make sure your key is located there, then run the client by passing your name as the first argument. For example:

```bash
python main.py aykut
```

## Boot sequence

On startup the client loads the key from `../private_keys/<name>.pem` and automatically starts polling until the grading server peer is discovered. Once it is found, the mining thread is started in the background and the interactive menu appears.

## Interactive menu

| # | Option | Description |
|---|--------|-------------|
| 1 | Get my public key | Prints the local node's public key in hex. |
| 2 | Find peers | Prints all currently connected peers in Delft community and Blockchain community. |
| 3 | Register community with server | Sends a `RegisterBlockchainRequest` to the grading server with our group ID and community ID. |
| 4 | Submit transaction | Creates a signed transaction with the node's own key and gossips it to all peers. Also adds it to the local mempool so it will be included in the next mined block. |
| 5 | View mempool | Prints all transactions currently waiting to be mined. |
| 6 | Change difficulty | Sets a new global PoW difficulty and broadcasts a `ChangedDifficultyMessage` so all peers change the difficulty to the same value immediately. |
| 7 | View blockchain | Prints every block in the chain with its full header fields and hash. |
| 8 | **Diverge & mine ahead** | Rolls back the last two blocks, adds a test transaction, temporarily raises difficulty to 4 and mines two fresh blocks. This creates a fork on purpose so that when the resulting chain is longer the other nodes are forced to switch and apply the longest-chain rule. |
| 9 | **Pause mining (30 s)** | Temporarily pauses the mining thread for 30 seconds and then resumes. While paused the other two nodes get ahead, when mining resumes the node receives their `BlockAnnouncementMessage`, sees a longer chain and switches. This tests the longest-chain rule. |
| 10 | **Speed-mine 10 blocks** | Drops difficulty to 2 and mines 10 blocks in a background thread, then restores the original difficulty. The node races ahead of its peers, when it broadcasts the announcement the others walk back to the common ancestor, validate the fork and switch. This tests the longest-chain rule. |
| 11 | Show `do_mine` flag | Prints the current state of the mining flag so we can confirm whether mining is active. |
| 12 | Mine one block manually | Mines a single block outside the continuous loop, then broadcasts it to all peers. |
| 0 | Exit | Shuts down the client. |

## Run the tests

`tests.py` contains unit tests for the core blockchain primitives in `custom_types.py` and `utils.py`: block and transaction hashing, PoW mining, signature verification, serialization round-trips, and chain validation. No network or running nodes are required.

Install `pytest`:

```bash
pip install pytest
```

Then run it:

```bash
python -m pytest tests.py -v
```
