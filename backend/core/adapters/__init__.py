"""Concrete implementations of Core interfaces.

Each adapter only depends on the Protocol it implements + its external SDK.
Business modules never import these directly — they receive the Protocol.
"""