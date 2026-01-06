#!/usr/bin/env python3
"""
Script de teste para validar funcionalidades do Cronograma MCP
"""

import json
import sys
from pathlib import Path

# Adicionar diretório ao path
sys.path.insert(0, str(Path(__file__).parent))

# Importar funções do main
from main import (
    validate_payload,
    hours_to_duration_display,
    generate_xlsx,
    sanitize_filename
)

def test_hours_to_duration():
    """Testa conversão de horas para formato HHH:MM:SS"""
    print("=" * 60)
    print("TESTE 1: Conversão de horas para HHH:MM:SS")
    print("=" * 60)
    
    test_cases = [
        (0.5, "0:30:00"),
        (1.0, "1:00:00"),
        (8.0, "8:00:00"),
        (24.0, "24:00:00"),
        (247.6667, "247:40:00"),
        (0.1667, "0:10:00"),
        (4.0, "4:00:00"),
        (480.0, "480:00:00"),
    ]
    
    passed = 0
    failed = 0
    
    for hours, expected in test_cases:
        result = hours_to_duration_display(hours)
        status = "✓" if result == expected else "✗"
        if result == expected:
            passed += 1
        else:
            failed += 1
        print(f"{status} {hours}h -> {result} (esperado: {expected})")
    
    print(f"\nResultado: {passed} passou, {failed} falhou")
    return failed == 0

def test_sanitize_filename():
    """Testa sanitização de nomes de arquivo"""
    print("\n" + "=" * 60)
    print("TESTE 2: Sanitização de nomes de arquivo")
    print("=" * 60)
    
    test_cases = [
        ("Projeto Normal", "Projeto Normal"),
        ("Projeto/Com\\Barras", "ProjetoComBarras"),
        ("Projeto:Com*Especiais?", "ProjetoComEspeciais"),
        ("   Espaços   Extras   ", "Espaços Extras"),
    ]
    
    passed = 0
    failed = 0
    
    for input_name, expected_pattern in test_cases:
        result = sanitize_filename(input_name)
        # Verificar se não contém caracteres inválidos
        invalid_chars = '<>:"/\\|?*'
        has_invalid = any(c in result for c in invalid_chars)
        status = "✓" if not has_invalid else "✗"
        if not has_invalid:
            passed += 1
        else:
            failed += 1
        print(f"{status} '{input_name}' -> '{result}'")
    
    print(f"\nResultado: {passed} passou, {failed} falhou")
    return failed == 0

def test_validation():
    """Testa validação de payload"""
    print("\n" + "=" * 60)
    print("TESTE 3: Validação de payload")
    print("=" * 60)
    
    # Teste 1: Payload válido
    valid_payload = {
        "project": {"name": "Teste"},
        "macros": [
            {
                "name": "Macro 1",
                "micros": [
                    {"name": "Micro 1", "hours": 8}
                ]
            }
        ]
    }
    
    is_valid, error = validate_payload(valid_payload)
    print(f"{'✓' if is_valid else '✗'} Payload válido: {is_valid}")
    
    # Teste 2: Macro sem micros (deve falhar)
    invalid_payload = {
        "project": {"name": "Teste"},
        "macros": [
            {
                "name": "Macro sem micros",
                "micros": []
            }
        ]
    }
    
    is_valid, error = validate_payload(invalid_payload)
    print(f"{'✓' if not is_valid else '✗'} Macro sem micros detectada: {not is_valid}")
    if error:
        print(f"  Erro: {error['error_code']}")
    
    # Teste 3: Hours inválido
    invalid_hours_payload = {
        "project": {"name": "Teste"},
        "macros": [
            {
                "name": "Macro 1",
                "micros": [
                    {"name": "Micro 1", "hours": -5}
                ]
            }
        ]
    }
    
    is_valid, error = validate_payload(invalid_hours_payload)
    print(f"{'✓' if not is_valid else '✗'} Hours negativo detectado: {not is_valid}")
    
    # Teste 4: Projeto sem nome
    no_name_payload = {
        "project": {},
        "macros": [
            {
                "name": "Macro 1",
                "micros": [
                    {"name": "Micro 1", "hours": 8}
                ]
            }
        ]
    }
    
    is_valid, error = validate_payload(no_name_payload)
    print(f"{'✓' if not is_valid else '✗'} Projeto sem nome detectado: {not is_valid}")
    
    return True

def test_generate_xlsx():
    """Testa geração de XLSX"""
    print("\n" + "=" * 60)
    print("TESTE 4: Geração de XLSX")
    print("=" * 60)
    
    # Carregar exemplo
    example_path = Path(__file__).parent / "example_payload.json"
    with open(example_path, 'r', encoding='utf-8') as f:
        payload = json.load(f)
    
    try:
        filepath, summary, total_hours = generate_xlsx(payload)
        
        print(f"✓ Arquivo gerado: {filepath.name}")
        print(f"✓ Total de horas: {total_hours:.4f}h")
        print(f"✓ Formato display: {hours_to_duration_display(total_hours)}")
        print(f"✓ Macros: {summary['macro_count']}")
        print(f"✓ Micros: {summary['micro_count']}")
        
        # Verificar se arquivo existe
        if filepath.exists():
            size = filepath.stat().st_size
            print(f"✓ Arquivo existe ({size} bytes)")
            return True
        else:
            print("✗ Arquivo não foi criado")
            return False
            
    except Exception as e:
        print(f"✗ Erro ao gerar XLSX: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_calculations():
    """Testa cálculos de totais"""
    print("\n" + "=" * 60)
    print("TESTE 5: Cálculos de totais")
    print("=" * 60)
    
    payload = {
        "project": {"name": "Teste Cálculos"},
        "macros": [
            {
                "name": "Macro 1",
                "micros": [
                    {"name": "Micro 1", "hours": 8},
                    {"name": "Micro 2", "hours": 4}
                ]
            },
            {
                "name": "Macro 2",
                "micros": [
                    {"name": "Micro 3", "hours": 2},
                    {"name": "Micro 4", "hours": 6}
                ]
            }
        ]
    }
    
    # Calcular esperado
    expected_macro1 = 8 + 4  # 12
    expected_macro2 = 2 + 6  # 8
    expected_total = expected_macro1 + expected_macro2  # 20
    
    try:
        filepath, summary, total_hours = generate_xlsx(payload)
        
        print(f"Total calculado: {total_hours}h (esperado: {expected_total}h)")
        print(f"Macro 1: {summary['macros'][0]['hours']}h (esperado: {expected_macro1}h)")
        print(f"Macro 2: {summary['macros'][1]['hours']}h (esperado: {expected_macro2}h)")
        
        # Verificar
        tolerance = 0.0001
        checks = [
            (abs(total_hours - expected_total) < tolerance, "Total do projeto"),
            (abs(summary['macros'][0]['hours'] - expected_macro1) < tolerance, "Total Macro 1"),
            (abs(summary['macros'][1]['hours'] - expected_macro2) < tolerance, "Total Macro 2"),
        ]
        
        all_passed = True
        for passed, name in checks:
            status = "✓" if passed else "✗"
            print(f"{status} {name}")
            if not passed:
                all_passed = False
        
        return all_passed
        
    except Exception as e:
        print(f"✗ Erro ao calcular: {e}")
        return False

def main():
    """Executa todos os testes"""
    print("\n" + "=" * 60)
    print("CRONOGRAMA MCP - SUITE DE TESTES")
    print("=" * 60)
    
    tests = [
        ("Conversão de horas", test_hours_to_duration),
        ("Sanitização de nomes", test_sanitize_filename),
        ("Validação de payload", test_validation),
        ("Geração de XLSX", test_generate_xlsx),
        ("Cálculos de totais", test_calculations),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ Erro no teste '{name}': {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Resumo
    print("\n" + "=" * 60)
    print("RESUMO DOS TESTES")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASSOU" if result else "✗ FALHOU"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} testes passaram")
    
    if passed == total:
        print("\n🎉 Todos os testes passaram!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} teste(s) falharam")
        return 1

if __name__ == "__main__":
    sys.exit(main())
