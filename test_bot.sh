#!/usr/bin/env bash
set -e

echo "======================================================================"
echo "  CLARAMENTE | LANZADOR DE PRUEBAS MULTI-AGENTE (TEST MODE)"
echo "  Ejecutando: python escritor.py --test"
echo "======================================================================"

if command -v python3 &>/dev/null; then
    python3 escritor.py --test
else
    python escritor.py --test
fi
