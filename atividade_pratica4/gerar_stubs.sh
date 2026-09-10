#!/bin/bash
# Run from the atividade_pratica4/ directory

echo "Generating gRPC stubs for carteira.proto..."

python -m grpc_tools.protoc \
  --proto_path=carteira \
  --python_out=carteira \
  --grpc_python_out=carteira \
  carteira/carteira.proto

echo "Stubs generated in carteira/"
