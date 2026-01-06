#!/usr/bin/env python3
"""
Script para testar a tool gerar_xlsx via linha de comando
"""

import json
import sys
from pathlib import Path

# Adicionar diretório ao path
sys.path.insert(0, str(Path(__file__).parent))

from main import gerar_xlsx

def main():
    print("=" * 70)
    print("TESTE DA TOOL: cronograma.gerar_xlsx")
    print("=" * 70)
    
    # Carregar payload de exemplo
    example_path = Path(__file__).parent / "example_payload.json"
    
    if not example_path.exists():
        print(f"❌ Arquivo não encontrado: {example_path}")
        return 1
    
    print(f"\n📄 Carregando payload de: {example_path.name}")
    
    with open(example_path, 'r', encoding='utf-8') as f:
        payload = json.load(f)
    
    print(f"✓ Payload carregado")
    print(f"  - Projeto: {payload['project']['name']}")
    print(f"  - Macros: {len(payload['macros'])}")
    
    # Chamar a tool
    print(f"\n🔧 Chamando tool gerar_xlsx...")
    
    try:
        result = gerar_xlsx(payload)
        
        if result["ok"]:
            print(f"\n✅ Sucesso!")
            print(f"\n📊 Resultado:")
            print(f"  - Projeto: {result['project_name']}")
            print(f"  - Total de horas: {result['project_total_hours']:.4f}h")
            print(f"  - Duration display: {result['project_total_duration_display']}")
            print(f"  - Filename: {result['filename']}")
            print(f"  - Macros: {result['summary']['macro_count']}")
            print(f"  - Micros: {result['summary']['micro_count']}")
            print(f"\n📥 Download URL:")
            print(f"  {result['download_url']}")
            print(f"\n⏰ Expira em: {result['download_expires_at']}")
            
            # Mostrar resumo das macros
            print(f"\n📋 Resumo das macros:")
            for macro in result['summary']['macros']:
                print(f"  - {macro['name']}: {macro['duration_display']} ({macro['micro_count']} micros)")
            
            # Informação sobre base64
            base64_size = len(result['base64'])
            print(f"\n💾 Base64 gerado: {base64_size} caracteres")
            
            print(f"\n{'=' * 70}")
            print(f"✅ Teste concluído com sucesso!")
            print(f"{'=' * 70}")
            
            return 0
        else:
            print(f"\n❌ Erro ao gerar cronograma:")
            print(f"  - Código: {result['error_code']}")
            print(f"  - Mensagem: {result['message']}")
            
            if result.get('details'):
                print(f"\n📋 Detalhes dos erros:")
                for detail in result['details']:
                    print(f"  - Campo: {detail.get('field', 'N/A')}")
                    print(f"    Problema: {detail.get('issue', 'N/A')}")
            
            return 1
            
    except Exception as e:
        print(f"\n❌ Exceção ao executar tool:")
        print(f"  {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
