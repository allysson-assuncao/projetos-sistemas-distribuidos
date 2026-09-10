# Generates gRPC stubs from carteira.proto
# Run from the atividade_pratica4/ directory
# Pre-requisite: pip install -r requirements.txt

Write-Host "Generating gRPC stubs for carteira.proto..." -ForegroundColor Cyan

python -m grpc_tools.protoc `
  --proto_path=carteira `
  --python_out=carteira `
  --grpc_python_out=carteira `
  carteira/carteira.proto

if ($LASTEXITCODE -eq 0) {
    Write-Host "Stubs generated successfully in carteira/!" -ForegroundColor Green
    Write-Host "  - carteira/carteira_pb2.py"      -ForegroundColor Green
    Write-Host "  - carteira/carteira_pb2_grpc.py" -ForegroundColor Green
} else {
    Write-Host "Error generating stubs. Check .proto and dependencies." -ForegroundColor Red
}
