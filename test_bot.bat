@echo off
chcp 65001 > nul
echo ======================================================================
echo   CLARAMENTE ^| LANZADOR DE PRUEBAS MULTI-AGENTE (TEST MODE)
echo   Ejecutando: python escritor.py --test
echo ======================================================================
python escritor.py --test
echo.
echo ======================================================================
echo   Prueba completada. Presione cualquier tecla para cerrar la consola...
echo ======================================================================
pause
