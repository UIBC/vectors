# keys/ · the four files in this directory, and why they are public

These are **test fixtures**, not credentials. Two 32-byte Ed25519 seeds and their public keys, committed on purpose.

## Why the seeds are in the repository

The `keyswap` vector is a full forgery: the attacker builds a package that is internally consistent and seals it with their own key. To rebuild that case, anyone needs the attacker's seed. If the seed were hidden, the vector would become an assertion ("trust us, we built a forgery") instead of a reproducible object. So the seeds are public, and that is the point: **a seed that anyone can read has no value as a signing key.**

Consequences, stated plainly:

- Anyone can re-seal these packages. That is intended here and disqualifying anywhere else.
- These seeds are **already compromised by publication**. They must never be used outside this repository.
- No production, release, registry, or attestation signature may use them. `tools/make_vectors.py` is the only intended consumer.

## Pinned by digest, so replacement is detectable

| File | Bytes | SHA-256 |
|---|---|---|
| `owner.key` | 72 | `87ca9915e596b2d53da73d637e1e5f0f36fbed5ace6f9d98090a759fa2cc19b7` |
| `owner.key.pub` | 64 | `e847ad8641f6fb038329767d8796e0607625ccc3fbbdea935a7d9ec807ee3be9` |
| `attacker.key` | 72 | `5385ddf38bc14cdb5162d80adc2b2fc04e1c5a77cc751aa55a02636807aebdab` |
| `attacker.key.pub` | 64 | `2a73165783d408be9df13a81e8c4956da66505bce3d4f5b6910c2183bcaa9250` |

`tools/check_key_hygiene.py` fails if any of these four files changes, disappears, or if a fifth file appears here — because "swap the fixture for a real key" is the one way this directory could turn harmful.

Public keys, for reading by eye:

```
owner.key.pub     2b9c67ad5945f6d755be5646edb51cb6ada317b89a79cfbd709af438a4fd4c55
attacker.key.pub  19e34b0feb3b39720f386874991f7c272d29e8efb69b3a4114e0cdd3bc89d9dc
```

## The rule that keeps this contained

A seed outside this directory is a defect, not a new fixture. `tools/check_key_hygiene.py` scans every tracked file outside `keys/` for `ed25519:<64 hex>` and for PEM private-key headers, and fails the build if it finds one. The grandfathering is exactly four files, by digest and by name.

If you need a *fresh* keypair for a new case, generate it at run time into a work directory and commit only the public key.
