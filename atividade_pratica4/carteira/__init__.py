"""
carteira package — gRPC Digital Wallet
Atividade Prática 4 — Distributed Systems

IMPORTANT — Package Resolution Fix:
  grpc_tools.protoc generates stub files (carteira_pb2.py, carteira_pb2_grpc.py)
  with absolute-style imports (`import carteira_pb2`). Those imports only resolve
  if the carteira/ directory itself is on sys.path.

  By injecting it here, in __init__.py, the fix applies automatically whenever
  anyone does `import carteira` or `from carteira import ...`, regardless of the
  caller's working directory (tests/, scripts/, or direct invocation).
"""

import sys
import os

# Ensure this package directory is on sys.path so protoc-generated stubs resolve
_package_dir = os.path.dirname(os.path.abspath(__file__))
if _package_dir not in sys.path:
    sys.path.insert(0, _package_dir)
